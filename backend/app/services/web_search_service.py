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
import ssl
try:
    from charset_normalizer import from_bytes as detect_charset
except Exception:
    detect_charset = None
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
        # 兼容未设置时的默认端点，并强制使用 nginx 暴露的 8088 端口
        self.searxng_endpoint = os.getenv("SEARXNG_ENDPOINT") or "http://127.0.0.1:8088"
        self.searxng_endpoint = self._normalize_searxng_endpoint(self.searxng_endpoint)
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY")

    def _normalize_searxng_endpoint(self, endpoint: str) -> str:
        """规范化 SearXNG 端点到 http://<host>:8088 形式，并去除多余路径/斜杠"""
        try:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(endpoint)
            scheme = p.scheme or "http"
            host = p.hostname or "127.0.0.1"
            # nginx 端口固定 8088
            netloc = f"{host}:8088"
            normalized = urlunparse((scheme, netloc, '', '', '', ''))
            return normalized.rstrip('/')
        except Exception:
            # 回退为默认
            return "http://127.0.0.1:8088"
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        kwargs = {
            "timeout": timeout,
            "headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        }
        # SSL 兼容性设置，处理部分站点的握手问题（如 BAD_ECPOINT）
        self.ssl_ctx = ssl.create_default_context()
        try:
            # OpenSSL 3 兼容旧站点（如果可用）
            self.ssl_ctx.options |= getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0)
        except Exception:
            pass
        connector = aiohttp.TCPConnector(ssl=self.ssl_ctx, enable_cleanup_closed=True)
        if self.http_proxy or self.https_proxy:
            kwargs["trust_env"] = True  # 让 aiohttp 读取环境代理
        self.session = aiohttp.ClientSession(
            connector=connector,
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
                "safesearch": "1",
                "categories": "general",
                # 固定使用 bing 引擎
                "engines": "bing",
            }
            url = urljoin(self.searxng_endpoint.rstrip('/') + '/', 'search')
            print("DEBUG URL:", url, "params:", params)
            # 为避免部分实例的反爬/校验导致 403，这里附带常见请求头
            req_headers = {
                'Accept': 'application/json',
                # 'Referer': self.searxng_endpoint.rstrip('/') + '/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36',
                'X-Forwarded-For': '127.0.0.1',
                'X-Real-IP': '127.0.0.1'
            }
            async with self.session.get(url, params=params, headers=req_headers) as resp:
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
        """抓取单个网页内容（带请求头、重试与编码探测）"""
        try:
            if not self.session or not result.url:
                return

            parsed = urlparse(result.url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
            common_headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/117.0 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': referer,
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            }

            async def fetch_once(url: str, ssl_ctx=None):
                async with self.session.get(url, headers=common_headers, allow_redirects=True, ssl=ssl_ctx) as resp:
                    status = resp.status
                    if status != 200:
                        raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=status)
                    raw = await resp.read()
                    # 编码探测
                    if detect_charset:
                        try:
                            best = detect_charset(raw).best()
                            enc = (best.encoding if best else None) or 'utf-8'
                            html_text = raw.decode(enc, errors='replace')
                        except Exception:
                            html_text = raw.decode('gb18030', errors='replace')
                    else:
                        try:
                            html_text = raw.decode('utf-8')
                        except Exception:
                            html_text = raw.decode('gb18030', errors='replace')
                    return html_text

            tries = 0
            max_tries = 2
            url_to_fetch = result.url
            while tries < max_tries:
                try:
                    html = await fetch_once(url_to_fetch, self.ssl_ctx)
                    content = self._extract_text_from_html(html)
                    if len(content) > 2000:
                        content = content[:2000] + "..."
                    result.content = content
                    logger.debug(f"成功抓取内容: {url_to_fetch}")
                    return
                except aiohttp.ClientResponseError as cre:
                    # 403 尝试切换移动端域名（常见如知乎）
                    if cre.status == 403 and 'zhihu.com' in parsed.netloc and 'm.zhihu.com' not in parsed.netloc:
                        url_to_fetch = result.url.replace('://www.zhihu.com', '://m.zhihu.com')
                        tries += 1
                        await asyncio.sleep(0.6 * tries)
                        continue
                    logger.warning(f"HTTP错误 {cre.status}: {url_to_fetch}")
                    return
                except ssl.SSLError as ssle:
                    # SSL 失败：依次尝试 TLS1.2 / 关闭校验 兜底
                    tries += 1
                    tls_attempts = []
                    try:
                        tls12_ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
                        tls12_ctx.check_hostname = True
                        tls12_ctx.verify_mode = ssl.CERT_REQUIRED
                        tls12_ctx.load_default_certs()
                        tls_attempts.append(tls12_ctx)
                    except Exception:
                        pass
                    tls_attempts.append(False)
                    for alt_ctx in tls_attempts:
                        try:
                            html = await fetch_once(url_to_fetch, alt_ctx)
                            content = self._extract_text_from_html(html)
                            if len(content) > 2000:
                                content = content[:2000] + "..."
                            result.content = content
                            mode = 'TLS1.2' if alt_ctx and isinstance(alt_ctx, ssl.SSLContext) else 'ssl=False'
                            logger.debug(f"成功抓取内容({mode}): {url_to_fetch}")
                            return
                        except Exception:
                            continue
                    if tries >= max_tries:
                        logger.warning(f"抓取内容失败(SSL): {url_to_fetch}: {ssle}")
                        return
                    await asyncio.sleep(0.6 * tries)
                except Exception as e:
                    tries += 1
                    if tries >= max_tries:
                        logger.warning(f"抓取内容失败 {url_to_fetch}: {e}")
                        return
                    await asyncio.sleep(0.6 * tries)
    
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
