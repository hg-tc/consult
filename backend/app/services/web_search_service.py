"""
互联网搜索服务
集成DuckDuckGo搜索、网页内容抓取和缓存
"""

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup
import json
from pathlib import Path
import os

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    snippet: str
    content: Optional[str] = None
    relevance_score: float = 0.0
    source_type: str = "web"  # web, academic, news

class WebSearchService:
    """互联网搜索服务"""
    
    def __init__(self, cache_dir: str = "web_search_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.session = None
        self.timeout = 30  # 搜索超时时间
        self.searxng_endpoint = os.getenv("SEARXNG_ENDPOINT")
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY")
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        kwargs = {
            "timeout": timeout,
            "headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        }
        if self.http_proxy or self.https_proxy:
            kwargs["trust_env"] = True  # 让 aiohttp 读取环境代理
        self.session = aiohttp.ClientSession(
            **kwargs
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    def _get_cache_key(self, query: str) -> str:
        """生成缓存键"""
        import hashlib
        return hashlib.md5(query.encode()).hexdigest()
    
    def _load_from_cache(self, query: str) -> Optional[List[SearchResult]]:
        """从缓存加载搜索结果"""
        try:
            cache_file = self.cache_dir / f"{self._get_cache_key(query)}.json"
            if cache_file.exists():
                # 检查缓存是否过期（24小时）
                if time.time() - cache_file.stat().st_mtime < 86400:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return [SearchResult(**item) for item in data]
        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
        return None
    
    def _save_to_cache(self, query: str, results: List[SearchResult]):
        """保存搜索结果到缓存"""
        try:
            cache_file = self.cache_dir / f"{self._get_cache_key(query)}.json"
            data = [result.__dict__ for result in results]
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
    
    async def search_web(self, query: str, num_results: int = 5) -> List[SearchResult]:
        """
        搜索网页
        
        Args:
            query: 搜索查询
            num_results: 结果数量
            
        Returns:
            搜索结果列表
        """
        try:
            # 检查缓存
            cached_results = self._load_from_cache(query)
            if cached_results:
                logger.info(f"使用缓存搜索结果: {query}")
                return cached_results[:num_results]
            
            logger.info(f"开始网络搜索: {query}")
            
            results: List[SearchResult] = []
            # 优先 SearXNG
            if self.searxng_endpoint:
                sx = await self._searxng_search(query, num_results)
                results.extend(sx)
            # 若 SearXNG 无结果，退回 DuckDuckGo
            if not results:
                results = await self._duckduckgo_search(query, num_results)
            
            # 如果没有结果，尝试Google搜索
            if not results:
                logger.info("DuckDuckGo无结果，尝试Google搜索")
                results = await self._google_search(query, num_results)
            
            # 抓取网页内容
            if results:
                await self._fetch_contents(results)
                
                # 保存到缓存
                self._save_to_cache(query, results)
            
            logger.info(f"搜索完成，获得 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return []

    async def _searxng_search(self, query: str, num_results: int) -> List[SearchResult]:
        """调用 SearXNG 实例进行搜索，返回标准化结果"""
        if not self.searxng_endpoint or not self.session:
            return []
        try:
            # SearXNG 支持 format=json
            params = {
                "q": query,
                "format": "json",
                "language": "zh-CN",
                "safesearch": 1,
                "categories": "general",
            }
            url = urljoin(self.searxng_endpoint.rstrip('/') + '/', 'search')
            async with self.session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"SearXNG 请求失败: {resp.status}")
                    return []
                data = await resp.json()
                results: List[SearchResult] = []
                for i, r in enumerate(data.get('results', [])[:num_results]):
                    results.append(SearchResult(
                        title=r.get('title') or r.get('url') or '搜索结果',
                        url=r.get('url', ''),
                        snippet=r.get('content') or r.get('pretty_url') or '',
                        relevance_score=1.0 - (i * 0.05),
                        source_type='web'
                    ))
                return results
        except Exception as e:
            logger.error(f"SearXNG 搜索失败: {e}")
            return []
    
    async def _duckduckgo_search(self, query: str, num_results: int) -> List[SearchResult]:
        """使用DuckDuckGo搜索"""
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                search_results = ddgs.text(query, max_results=num_results)
                
                for i, result in enumerate(search_results):
                    search_result = SearchResult(
                        title=result.get('title', ''),
                        url=result.get('href', ''),
                        snippet=result.get('body', ''),
                        relevance_score=1.0 - (i * 0.1)  # 简单相关性评分
                    )
                    results.append(search_result)
            
            return results
            
        except ImportError:
            logger.warning("DuckDuckGo搜索库未安装，使用模拟搜索")
            return self._mock_web_search(query, num_results)
        except Exception as e:
            logger.error(f"DuckDuckGo搜索失败: {e}")
            return self._mock_web_search(query, num_results)
    
    async def _google_search(self, query: str, num_results: int) -> List[SearchResult]:
        """使用Google搜索（备用方案）"""
        try:
            from googlesearch import search
            
            results = []
            search_results = list(search(query, num_results=num_results))
            
            for i, url in enumerate(search_results):
                search_result = SearchResult(
                    title=f"搜索结果 {i+1}",
                    url=url,
                    snippet="",
                    relevance_score=1.0 - (i * 0.1)
                )
                results.append(search_result)
            
            return results
            
        except Exception as e:
            logger.error(f"Google搜索失败: {e}")
            return []
    
    async def _fetch_contents(self, results: List[SearchResult]):
        """抓取网页内容"""
        if not self.session:
            return
        
        tasks = []
        for result in results:
            if result.url:
                tasks.append(self._fetch_single_content(result))
        
        # 并发抓取，但限制并发数
        semaphore = asyncio.Semaphore(3)
        async def fetch_with_semaphore(result):
            async with semaphore:
                return await self._fetch_single_content(result)
        
        await asyncio.gather(*[fetch_with_semaphore(result) for result in results], return_exceptions=True)
    
    async def _fetch_single_content(self, result: SearchResult):
        """抓取单个网页内容"""
        try:
            if not self.session or not result.url:
                return
            
            async with self.session.get(result.url) as response:
                if response.status == 200:
                    html = await response.text()
                    content = self._extract_text_from_html(html)
                    
                    # 限制内容长度
                    if len(content) > 2000:
                        content = content[:2000] + "..."
                    
                    result.content = content
                    logger.debug(f"成功抓取内容: {result.url}")
                else:
                    logger.warning(f"HTTP错误 {response.status}: {result.url}")
                    
        except Exception as e:
            logger.warning(f"抓取内容失败 {result.url}: {e}")
    
    def _extract_text_from_html(self, html: str) -> str:
        """从HTML提取文本内容"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 移除脚本和样式标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 提取文本
            text = soup.get_text()
            
            # 清理文本
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
            
        except Exception as e:
            logger.error(f"HTML解析失败: {e}")
            return ""
    
    async def search_and_extract(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        搜索并提取内容，返回LangChain Document格式
        
        Args:
            query: 搜索查询
            num_results: 结果数量
            
        Returns:
            Document格式的搜索结果
        """
        async with self:
            results = await self.search_web(query, num_results)
            
            documents = []
            for result in results:
                if result.content:
                    doc = {
                        'page_content': result.content,
                        'metadata': {
                            'title': result.title,
                            'url': result.url,
                            'snippet': result.snippet,
                            'relevance_score': result.relevance_score,
                            'source_type': result.source_type
                        }
                    }
                    documents.append(doc)
            
            return documents
    
    async def search_academic(self, query: str, num_results: int = 3) -> List[SearchResult]:
        """学术搜索（简化版，实际可集成arXiv等）"""
        try:
            # 添加学术关键词
            academic_query = f"{query} site:arxiv.org OR site:scholar.google.com"
            return await self.search_web(academic_query, num_results)
        except Exception as e:
            logger.error(f"学术搜索失败: {e}")
            return []
    
    async def search_news(self, query: str, num_results: int = 3) -> List[SearchResult]:
        """新闻搜索"""
        try:
            # 添加新闻关键词
            news_query = f"{query} news"
            return await self.search_web(news_query, num_results)
        except Exception as e:
            logger.error(f"新闻搜索失败: {e}")
            return []
    
    def _mock_web_search(self, query: str, num_results: int) -> List[SearchResult]:
        """模拟网络搜索（当真实搜索不可用时）"""
        logger.info(f"使用模拟搜索: {query}")
        
        mock_results = [
            SearchResult(
                title=f"关于 {query} 的搜索结果 1",
                url=f"https://example.com/search1",
                snippet=f"这是关于 {query} 的模拟搜索结果，包含相关信息和分析。",
                relevance_score=0.9
            ),
            SearchResult(
                title=f"关于 {query} 的搜索结果 2", 
                url=f"https://example.com/search2",
                snippet=f"另一个关于 {query} 的模拟结果，提供了不同的观点和见解。",
                relevance_score=0.8
            ),
            SearchResult(
                title=f"关于 {query} 的搜索结果 3",
                url=f"https://example.com/search3", 
                snippet=f"第三个关于 {query} 的模拟结果，包含详细的技术信息。",
                relevance_score=0.7
            )
        ]
        
        return mock_results[:num_results]


# 全局实例
_web_search_service = None

def get_web_search_service() -> WebSearchService:
    """获取全局WebSearchService实例"""
    global _web_search_service
    if _web_search_service is None:
        _web_search_service = WebSearchService()
    return _web_search_service
