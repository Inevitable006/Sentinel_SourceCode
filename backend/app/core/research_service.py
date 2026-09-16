import json
import time
import asyncio
import re
from app.core.paths import SENTINEL_DATA_DIR
from app.core.request_context import request_context
from app.core.network_utils import SafeAsyncClient

HISTORY_FILE = SENTINEL_DATA_DIR / "research_history.json"

class ResearchService:
    def __init__(self):
        self.local_mode = False
        self._load_history()

    def _load_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        else:
            self.history = []

    def _save_history(self):
        with open(HISTORY_FILE, "w") as f:
            json.dump(self.history, f, indent=4)

    def set_local_mode(self, enabled: bool):
        self.local_mode = enabled

    def clear_history(self):
        self.history = []
        self._save_history()

    def get_history(self):
        return self.history

    async def _async_search(self, query: str) -> str:
        """Asynchronous DDG search execution using SafeAsyncClient."""
        # DuckDuckGo endpoint is fixed and trusted.
        # This function only queries the fixed trusted search endpoint and returns metadata/snippets.
        
        try:
            url = f"https://html.duckduckgo.com/html/?q={query}"
            async with SafeAsyncClient() as client:
                response = await client.safe_request("GET", url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=5.0)
            
            if response.status_code != 200:
                return f"Search failed with status: {response.status_code}"
                
            html = response.text
            
            # Simple regex to extract search results from HTML
            results = []
            pattern = r'<a class="result__url" href="([^"]+)">(.*?)</a>.*?<a class="result__snippet[^>]*>(.*?)</a>'
            for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
                if len(results) >= 2:
                    break
                url_raw = match.group(1).strip()
                title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                snippet = re.sub(r'<[^>]+>', '', match.group(3)).strip()
                
                # duckduckgo redirects via /l/?uddg=...
                if "uddg=" in url_raw:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url_raw).query)
                    if "uddg" in parsed:
                        url_raw = parsed["uddg"][0]
                
                results.append({"href": url_raw, "title": title, "body": snippet})

            if not results:
                return "No results found."
            
            output = f"Search Results for '{query}' (Retrieved at {time.strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
            
            for r in results:
                url = r.get("href")
                title = r.get("title")
                snippet = r.get("body")
                
                self.history.append({"query": query, "url": url, "title": title, "timestamp": time.time()})
                
                output += f"Source: [{title}]({url})\n"
                output += f"Snippet: {snippet}\n\n"
                
            self._save_history()
            return output
        except Exception as e:
            return f"Web search failed: {e}"

    def search(self, query: str, request_id: str = None) -> str:
        """
        Executes a web search.
        If request_id is provided, it binds the async task to the request context
        for genuine cancellation.
        """
        if self.local_mode:
            return "System Error: Local Only mode is enabled. Web research is disabled."

        # We must run the async search within a new event loop or the current one
        # since this is called from a synchronous thread executor.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        task = loop.create_task(self._async_search(query))
        
        if request_id:
            request_context.register_task(request_id, task)
            
        try:
            result = loop.run_until_complete(task)
            return result
        except asyncio.CancelledError:
            return "Error: Web research task was cancelled by the user."
        except Exception as e:
            return f"Web search failed: {e}"
        finally:
            if request_id:
                request_context.unregister_task(request_id)
            loop.close()

    async def _async_fetch(self, url: str) -> str:
        """Asynchronous safe fetch of a URL."""
        try:
            async with SafeAsyncClient() as client:
                # 1MB payload limit is handled natively by httpx streaming if we use it,
                # but for simplicity, we'll fetch and enforce the limit manually.
                response = await client.safe_request("GET", url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=5.0)
            
            if response.status_code != 200:
                return f"Fetch failed with status: {response.status_code}"
                
            html = response.text
            
            # Simple regex to strip HTML tags and scripts
            html = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', html).strip()
            
            # Condense multiple spaces and newlines
            text = re.sub(r'\s+', ' ', text)
            
            if len(text) > 10240:
                text = text[:10240] + "\n... [TRUNCATED: Output exceeded 10KB limit]"
                
            return text
        except Exception as e:
            return f"Fetch failed: {e}"

    def fetch_url(self, url: str, request_id: str = None) -> str:
        """
        Executes a safe URL fetch.
        """
        if self.local_mode:
            return "System Error: Local Only mode is enabled. Web research is disabled."

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        task = loop.create_task(self._async_fetch(url))
        
        if request_id:
            request_context.register_task(request_id, task)
            
        try:
            result = loop.run_until_complete(task)
            return result
        except asyncio.CancelledError:
            return "Error: Web research task was cancelled by the user."
        except Exception as e:
            return f"Fetch failed: {e}"
        finally:
            if request_id:
                request_context.unregister_task(request_id)
            loop.close()

research_service = ResearchService()
