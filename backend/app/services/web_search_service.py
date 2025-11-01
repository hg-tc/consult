"""
互联网搜索服务
集成 SearXNG 和 Google 搜索、网页内容抓取和缓存
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
from yarl import URL

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
    
    def __init__(self, cache_dir: str = "web_search_cache", log_level: Optional[str] = None, verbose: Optional[bool] = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.session = None
        self.timeout = 30  # 搜索超时时间
        # 兼容未设置时的默认端点，并强制使用 nginx 暴露的 8088 端口
        self.searxng_endpoint = os.getenv("SEARXNG_ENDPOINT") or "http://127.0.0.1:8088"
        self.searxng_endpoint = self._normalize_searxng_endpoint(self.searxng_endpoint)
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY")
        # 日志级别与详细模式
        try:
            from app.core.config import settings
            effective_level = (log_level or settings.WEB_SEARCH_LOG_LEVEL or settings.LOG_LEVEL or "INFO").upper()
            self.verbose = bool(settings.WEB_SEARCH_VERBOSE if verbose is None else verbose)
        except Exception:
            effective_level = (log_level or os.getenv("WEB_SEARCH_LOG_LEVEL") or os.getenv("LOG_LEVEL", "INFO")).upper()
            self.verbose = bool(verbose) if verbose is not None else os.getenv("WEB_SEARCH_VERBOSE", "false").lower() in {"1", "true", "yes", "on"}
        logger.setLevel(getattr(logging, effective_level, logging.INFO))

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
        timeout_obj = aiohttp.ClientTimeout(total=self.timeout)
        kwargs = {
            "timeout": timeout_obj,
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
    
    async def _ensure_session(self):
        """确保 session 已初始化（懒加载，支持直接调用 search_web 而不使用 async with）"""
        import asyncio
        
        # 检查 session 是否需要重新创建
        needs_new_session = (
            self.session is None or 
            self.session.closed
        )
        
        # 检查 event loop 状态（关键：asyncio.run() 会创建新 loop，旧 session 无法使用）
        try:
            current_loop = asyncio.get_running_loop()
            # 如果有 session，检查它是否绑定到当前 loop
            if self.session is not None and not self.session.closed:
                try:
                    connector_loop = None
                    if hasattr(self.session, '_connector') and self.session._connector:
                        if hasattr(self.session._connector, '_loop'):
                            connector_loop = self.session._connector._loop
                        elif hasattr(self.session._connector, 'loop'):
                            connector_loop = self.session._connector.loop
                    
                    if connector_loop is not None and connector_loop is not current_loop:
                        needs_new_session = True
                        logger.debug(f"_ensure_session: 检测到 event loop 切换，需要重新创建 session")
                except Exception as e:
                    # 检查失败时，保守起见也重新创建
                    logger.debug(f"_ensure_session: 检查 session loop 时出错: {e}，重新创建")
                    needs_new_session = True
        except RuntimeError:
            # 没有运行中的 loop，这种情况不应该发生（因为我们在 async 函数中）
            pass
        
        if needs_new_session:
            # 如果已有 session，先尝试清理（但要捕获可能的异常）
            if self.session is not None:
                try:
                    if not self.session.closed:
                        await self.session.close()
                except Exception as e:
                    logger.debug(f"关闭旧 session 时出错（可忽略）: {e}")
                self.session = None
            
            # 创建 timeout 对象（不设置为上下文管理器，避免 "Timeout context manager should be used inside a task" 警告）
            timeout_obj = aiohttp.ClientTimeout(total=self.timeout)
            kwargs = {
                "timeout": timeout_obj,
                "headers": {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            }
            # SSL 兼容性设置
            self.ssl_ctx = ssl.create_default_context()
            try:
                self.ssl_ctx.options |= getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0)
            except Exception:
                pass
            connector = aiohttp.TCPConnector(ssl=self.ssl_ctx, enable_cleanup_closed=True)
            if self.http_proxy or self.https_proxy:
                kwargs["trust_env"] = True
            try:
                self.session = aiohttp.ClientSession(
                    connector=connector,
                    **kwargs
                )
                logger.debug("WebSearchService session 已自动初始化（懒加载）")
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    logger.warning("无法创建 session：event loop 已关闭")
                    self.session = None
                else:
                    raise
    
    def _is_event_loop_closed(self) -> bool:
        """检查当前 event loop 是否已关闭"""
        try:
            loop = asyncio.get_running_loop()
            return loop.is_closed()
        except RuntimeError:
            # 没有运行中的 event loop
            try:
                # 尝试获取当前 event loop（可能是已关闭的）
                loop = asyncio.get_event_loop()
                return loop.is_closed()
            except RuntimeError:
                # 无法获取 event loop，可能已关闭
                return True
    
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
            
            # 强制重新初始化 session（确保在当前 event loop 中）
            # 对于 asyncio.run() 场景：每次调用都创建新的 loop，所以每次都强制创建新 session
            import asyncio
            try:
                current_loop = asyncio.get_running_loop()
                
                # 如果已有 session，直接设置为 None（不等待关闭，避免 loop 问题）
                # 旧的 session 会被垃圾回收器处理
                if self.session is not None:
                    old_session = self.session
                    self.session = None
                    # 尝试在后台关闭旧 session（不等待完成）
                    try:
                        if not old_session.closed:
                            # 创建任务来关闭，但不等待
                            task = current_loop.create_task(old_session.close())
                            # 添加回调来忽略结果（避免警告传播）
                            task.add_done_callback(lambda t: None)
                    except Exception as e:
                        # 如果无法关闭，忽略（session 会在下次调用时重新创建）
                        logger.debug(f"关闭旧 session 时出错（可忽略）: {e}")
                
                # 强制创建新 session（绑定到当前 loop）
                await self._ensure_session()
                
            except RuntimeError as e:
                # 没有运行中的 loop（不应该发生，但保守处理）
                logger.debug(f"无法获取运行中的 loop: {e}，尝试创建 session")
                self.session = None
                await self._ensure_session()
            
            if not self.session or self.session.closed:
                logger.warning("session 初始化失败，跳过网络搜索")
                return []
            
            results: List[SearchResult] = []
            # 优先 SearXNG
            if self.searxng_endpoint:
                sx = await self._searxng_search(query, num_results)
                results.extend(sx)
            
            # 如果 SearXNG 无结果，尝试Google搜索
            if not results:
                logger.info("SearXNG无结果，尝试Google搜索")
                results = await self._google_search(query, num_results)
            
            # 抓取网页内容
            if results:
                await self._fetch_contents(results)
                
                # 保存到缓存
                self._save_to_cache(query, results)
            
            logger.info(f"搜索完成，获得 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"网络搜索失败: {e}", exc_info=True)
            return []
        finally:
            # 在 asyncio.run() 场景中，event loop 会在方法返回后关闭
            # 我们不在这里关闭 session，因为：
            # 1. 可能还有请求在进行
            # 2. loop 可能正在关闭，导致关闭操作失败
            # 3. session 会在下次 search_web 调用时被检测并重新创建
            # 注意：这会导致 "Unclosed client session" 警告，但不影响功能
            pass

    async def _searxng_search(self, query: str, num_results: int) -> List[SearchResult]:
        """调用 SearXNG 实例进行搜索，返回标准化结果"""
        # 检查 endpoint
        if not self.searxng_endpoint:
            logger.warning(f"SearXNG 搜索跳过：endpoint 未配置")
            return []
        
        # 强制确保 session 在当前 event loop 中（关键：每次使用前都检查）
        import asyncio
        try:
            current_loop = asyncio.get_running_loop()
            
            # 如果 session 不存在或已关闭，重新创建
            if not self.session or self.session.closed:
                await self._ensure_session()
            else:
                # 即使 session 存在，也检查它是否绑定到当前 loop
                try:
                    connector_loop = None
                    if hasattr(self.session, '_connector') and self.session._connector:
                        if hasattr(self.session._connector, '_loop'):
                            connector_loop = self.session._connector._loop
                        elif hasattr(self.session._connector, 'loop'):
                            connector_loop = self.session._connector.loop
                    
                    # 如果 loop 不匹配，强制重新创建
                    if connector_loop is not None and connector_loop is not current_loop:
                        logger.debug("_searxng_search: 检测到 loop 不匹配，重新创建 session")
                        # 直接设置为 None，不等待关闭（避免 loop 问题）
                        old_session = self.session
                        self.session = None
                        # 尝试后台关闭旧 session
                        try:
                            if not old_session.closed:
                                task = current_loop.create_task(old_session.close())
                                task.add_done_callback(lambda t: None)
                        except Exception:
                            pass
                        await self._ensure_session()
                except Exception as e:
                    # 检查失败时，保守起见重新创建
                    logger.debug(f"_searxng_search: 检查 session 时出错: {e}，重新创建")
                    old_session = self.session
                    self.session = None
                    try:
                        if old_session and not old_session.closed:
                            task = current_loop.create_task(old_session.close())
                            task.add_done_callback(lambda t: None)
                    except Exception:
                        pass
                    await self._ensure_session()
        except RuntimeError:
            # 没有运行中的 loop
            await self._ensure_session()
        
        if not self.session or self.session.closed:
            logger.warning(f"SearXNG 搜索跳过：session 初始化失败")
            return []
        
        logger.info(f"SearXNG 开始搜索: {query}, endpoint: {self.searxng_endpoint}")
        
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
        if self.verbose:
            logger.debug(f"SearXNG 请求 URL: {url} params: {params}")
        # 为避免部分实例的反爬/校验导致 403，这里附带常见请求头
        req_headers = {
            'Accept': 'application/json',
            # 'Referer': self.searxng_endpoint.rstrip('/') + '/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36',
            'X-Forwarded-For': '127.0.0.1',
            'X-Real-IP': '127.0.0.1'
        }
        
        # 最多重试一次（处理 event loop 关闭的情况）
        max_retries = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 如果重试，重新初始化 session（可能 event loop 已关闭）
                if attempt > 0:
                    logger.debug(f"SearXNG 重试 ({attempt}/{max_retries-1})，重新初始化 session")
                    if self.session and not self.session.closed:
                        try:
                            await self.session.close()
                        except Exception:
                            pass
                    self.session = None
                    await self._ensure_session()
                    if not self.session or self.session.closed:
                        logger.warning("重试时 session 初始化失败")
                        break
                
                async with self.session.get(url, params=params, headers=req_headers) as resp:
                    if resp.status != 200:
                        logger.error(f"SearXNG 请求失败: HTTP {resp.status}, 查询: {query}, URL: {url}")
                        try:
                            error_text = await resp.text()
                            logger.debug(f"SearXNG 错误响应内容: {error_text[:500]}")
                        except Exception:
                            pass
                        return []
                    
                    logger.info(f"SearXNG 请求成功: HTTP {resp.status}, 查询: {query}")
                    data = await resp.json()
                    results: List[SearchResult] = []
                    raw_results = data.get('results', [])
                    
                    if not raw_results:
                        logger.warning(f"SearXNG 返回空结果，查询: {query}, 原始响应结果数: 0")
                    else:
                        logger.info(f"SearXNG 获取到 {len(raw_results)} 个原始结果，查询: {query}")
                    
                    for i, r in enumerate(raw_results[:num_results]):
                        results.append(SearchResult(
                            title=r.get('title') or r.get('url') or '搜索结果',
                            url=r.get('url', ''),
                            snippet=r.get('content') or r.get('pretty_url') or '',
                            relevance_score=1.0 - (i * 0.05),
                            source_type='web'
                        ))
                    
                    logger.info(f"SearXNG 搜索成功: 查询 '{query}', 返回 {len(results)} 个结果")
                    return results
                    
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    last_error = e
                    logger.warning(f"SearXNG 请求失败（Event loop 已关闭），尝试: {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        continue  # 重试
                    else:
                        logger.error(f"SearXNG 搜索失败: Event loop 已关闭，无法重试, 查询: {query}, endpoint: {self.searxng_endpoint}")
                        return []
                else:
                    raise
            except aiohttp.ClientError as e:
                logger.error(f"SearXNG 网络请求异常: {e}, 查询: {query}, endpoint: {self.searxng_endpoint}", exc_info=True)
                return []
            except Exception as e:
                logger.error(f"SearXNG 搜索失败: {type(e).__name__}: {e}, 查询: {query}, endpoint: {self.searxng_endpoint}", exc_info=True)
                return []
        
        # 所有重试都失败
        if last_error:
            logger.error(f"SearXNG 搜索失败: 重试 {max_retries} 次后仍然失败, 查询: {query}, endpoint: {self.searxng_endpoint}")
        return []
    
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
        # 确保 session 已初始化
        if not self.session or self.session.closed:
            await self._ensure_session()
        
        if not self.session or self.session.closed:
            logger.warning("无法抓取网页内容：session 初始化失败")
            return
        
        # 过滤出有 URL 的结果
        results_with_url = [r for r in results if r.url]
        if not results_with_url:
            return
        
        # 并发抓取，但限制并发数
        semaphore = asyncio.Semaphore(3)
        async def fetch_with_semaphore(result):
            async with semaphore:
                return await self._fetch_single_content(result)
        
        # 使用 fetch_with_semaphore 包装，确保所有协程都被 await
        await asyncio.gather(*[fetch_with_semaphore(result) for result in results_with_url], return_exceptions=True)
    
    async def _fetch_single_content(self, result: SearchResult):
        """抓取单个网页内容（带请求头、重试与编码探测），精简异常结构避免语法问题"""
        if not result.url:
            return
        
        # 确保 session 可用
        if not self.session or self.session.closed:
            await self._ensure_session()
        
        if not self.session or self.session.closed:
            return

        # 规范化 URL，处理未编码的中文、空白、缺失 scheme 等情况
        def sanitize_url(raw_url: str) -> str:
            try:
                cleaned = raw_url.strip()
                # yarl 可对未编码部分自动编码
                y = URL(cleaned, encoded=False)
                # 若无 scheme，默认补 http
                if not y.scheme:
                    y = URL.build(scheme="http", host=str(y))
                return str(y)
            except Exception:
                return raw_url

        safe_url = sanitize_url(result.url)
        parsed = urlparse(safe_url)
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
                if resp.status != 200:
                    raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
                raw = await resp.read()
                if detect_charset:
                    try:
                        best = detect_charset(raw).best()
                        enc = (best.encoding if best else None) or 'utf-8'
                        return raw.decode(enc, errors='replace')
                    except Exception:
                        return raw.decode('gb18030', errors='replace')
                try:
                    return raw.decode('utf-8')
                except Exception:
                    return raw.decode('gb18030', errors='replace')

        tries = 0
        max_tries = 2
        url_to_fetch = safe_url

        while tries < max_tries:
            html = None
            # 首选默认 SSL 上下文
            try:
                html = await fetch_once(url_to_fetch, self.ssl_ctx)
            except aiohttp.ClientResponseError as cre:
                if cre.status == 403 and 'zhihu.com' in parsed.netloc and 'm.zhihu.com' not in parsed.netloc:
                    url_to_fetch = safe_url.replace('://www.zhihu.com', '://m.zhihu.com')
                    tries += 1
                    await asyncio.sleep(0.6 * tries)
                    continue
                logger.warning(f"HTTP错误 {cre.status}: {url_to_fetch}")
                return
            except ssl.SSLError:
                # SSL 兜底：TLS1.2 → 关闭校验
                for alt_ctx in (self._tls12_ctx() , False):
                    if alt_ctx is None:
                        continue
                    try:
                        html = await fetch_once(url_to_fetch, alt_ctx)
                        break
                    except Exception:
                        continue
            except Exception as e:
                tries += 1
                if tries >= max_tries:
                    logger.warning(f"抓取内容失败 {url_to_fetch}: {e}")
                    return
                await asyncio.sleep(0.6 * tries)
                continue

            if html is None:
                tries += 1
                await asyncio.sleep(0.6 * tries)
                continue

            content = self._extract_text_from_html(html)
            if len(content) > 2000:
                content = content[:2000] + "..."
            result.content = content
            logger.debug(f"成功抓取内容: {url_to_fetch}")
            return

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
