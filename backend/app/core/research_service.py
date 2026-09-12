import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from urllib.parse import urlparse
import socket
import ipaddress
import json
import time
from app.core.paths import SENTINEL_DATA_DIR

HISTORY_FILE = SENTINEL_DATA_DIR / "research_history.json"

class ResearchService:
    def __init__(self):
        self.max_redirects = 3
        self.timeout = 5.0
        self.max_size = 250 * 1024 # 250 KB
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

    def is_safe_url(self, url: str) -> bool:
        """SSRF protection: checks if the URL points to a private/local IP."""
        try:
            parsed = urlparse(url)
            if parsed.scheme != "https":
                return False
                
            hostname = parsed.hostname
            if not hostname:
                return False

            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast:
                return False
            return True
        except Exception:
            return False

    def fetch_url(self, url: str) -> str:
        if not self.is_safe_url(url):
            return "Error: URL is invalid, non-HTTPS, or points to a restricted local network address (SSRF blocked)."

        try:
            with httpx.Client(follow_redirects=True, max_redirects=self.max_redirects, timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                
                # Check size
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self.max_size:
                    return f"Error: Page too large ({content_length} bytes)."
                    
                content = response.content
                if len(content) > self.max_size:
                    return "Error: Page content exceeds size limit."
                    
                soup = BeautifulSoup(content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.extract()
                    
                text = soup.get_text(separator=' ', strip=True)
                # Truncate text to a reasonable length for the LLM
                return text[:5000]
        except Exception as e:
            return f"Error fetching {url}: {e}"

    def search(self, query: str) -> str:
        if self.local_mode:
            return "System Error: Local Only mode is enabled. Web research is disabled."

        # NOTE: ResourceGovernor state checks are handled centrally by the
        # PolicyEngine before the executor is called. No redundant check here.

        try:
            results = DDGS().text(query, max_results=2)
            if not results:
                return "No results found."
            
            output = f"Search Results for '{query}' (Retrieved at {time.strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
            
            for r in results:
                url = r.get("href")
                title = r.get("title")
                snippet = r.get("body")
                
                self.history.append({"query": query, "url": url, "title": title, "timestamp": time.time()})
                self._save_history()
                
                page_text = self.fetch_url(url)
                
                output += f"Source: [{title}]({url})\n"
                output += f"Snippet: {snippet}\n"
                if not page_text.startswith("Error"):
                    output += f"Content: {page_text[:1500]}...\n\n"
                else:
                    output += f"Content: {page_text}\n\n"
                    
            return output
        except Exception as e:
            return f"Web search failed: {e}"

research_service = ResearchService()
