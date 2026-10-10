import socket
import ipaddress
import urllib.parse
import httpx
import httpcore
from typing import Optional

from app.core.egress import egress_guard

def resolve_and_validate_url(url: str) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Robust SSRF validation.
    Returns (is_safe, pinned_ip, error_message)
    """
    try:
        parsed = urllib.parse.urlparse(url)
        
        # Scheme validation
        if parsed.scheme != "https":
            return False, None, "Only HTTPS scheme is allowed."
            
        # Credential validation
        if parsed.username or parsed.password:
            return False, None, "Credentials in URL are not allowed."
            
        # Port validation
        if parsed.port and parsed.port != 443:
            return False, None, "Only port 443 is allowed."
            
        hostname = parsed.hostname
        if not hostname:
            return False, None, "Invalid hostname."

        # Resolve hostname (all address families)
        try:
            addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return False, None, "Hostname resolution failed."

        pinned_ip = None

        for ai in addr_info:
            ip_str = ai[4][0]
            
            # Handle IPv4-mapped IPv6
            if ip_str.startswith("::ffff:"):
                ip_str = ip_str[7:]
                
            ip_obj = ipaddress.ip_address(ip_str)
            
            # Strict validation
            if (ip_obj.is_private or ip_obj.is_loopback or 
                ip_obj.is_link_local or ip_obj.is_multicast or 
                ip_obj.is_reserved or ip_obj.is_unspecified):
                return False, None, f"IP {ip_str} is in a restricted range."
                
            if pinned_ip is None:
                pinned_ip = ip_str

        if not pinned_ip:
            return False, None, "No IP addresses resolved."

        return True, pinned_ip, None
    except Exception as e:
        return False, None, str(e)


# Largest response body a tool may download. Bodies are read in chunks and the download is
# aborted once this is exceeded; nothing larger is ever held in memory.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ResponseTooLarge(ValueError):
    pass


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    """Opens TCP connections only to the address that was validated for each hostname.
    The URL keeps the real hostname, so TLS SNI and certificate checks still use it;
    only the TCP destination is fixed. A second (possibly rebinding) DNS lookup never happens."""

    def __init__(self):
        self.pins: dict[str, str] = {}
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        ip = self.pins.get(host.lower() if isinstance(host, str) else host)
        if ip is None:
            raise httpcore.ConnectError(f"No validated address for {host}; connection refused.")
        return await self._inner.connect_tcp(ip, port, timeout=timeout, local_address=local_address,
                                             socket_options=socket_options)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("Unix sockets are not allowed.")

    async def sleep(self, seconds):
        await self._inner.sleep(seconds)


class _LimitedStream(httpx.AsyncByteStream):
    """Counts bytes as they arrive and aborts the download once the budget is exceeded."""

    def __init__(self, inner, max_bytes: int):
        self._inner, self._max = inner, max_bytes

    async def __aiter__(self):
        seen = 0
        async for chunk in self._inner:
            seen += len(chunk)
            if seen > self._max:
                raise ResponseTooLarge(f"Response exceeded the {self._max // 1024} KB limit and was stopped.")
            yield chunk

    async def aclose(self):
        await self._inner.aclose()


class _LimitedTransport(httpx.AsyncBaseTransport):
    """Wraps the real transport so every response body is size-limited while it is read."""

    def __init__(self, inner: httpx.AsyncBaseTransport):
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        limit = request.extensions.get("sentinel_max_bytes", MAX_RESPONSE_BYTES)
        return httpx.Response(response.status_code, headers=response.headers,
                              stream=_LimitedStream(response.stream, limit), extensions=response.extensions)

    async def aclose(self):
        await self._inner.aclose()


class SafeAsyncClient(httpx.AsyncClient):
    """
    An async client that enforces the egress guard (app.core.egress) and strict SSRF protections.
    Every hop is validated, the connection goes to the validated IP (no DNS rebinding window),
    TLS is verified against the original hostname, and response bodies are size-limited
    while they download (uncompressed responses are requested, so the limit is the real size).
    """
    def __init__(self, *args, **kwargs):
        kwargs["trust_env"] = False
        # Disable redirects at the client level to handle them manually with re-validation
        kwargs["follow_redirects"] = False
        self._pinned_backend = _PinnedBackend()
        transport = kwargs.get("transport")
        if transport is None:   # tests pass an in-memory MockTransport; real use never does
            transport = httpx.AsyncHTTPTransport()
            pool = getattr(transport, "_pool", None)
            if pool is None or not hasattr(pool, "_network_backend"):
                raise RuntimeError("HTTP transport does not support address pinning; refusing to make requests.")
            pool._network_backend = self._pinned_backend
        kwargs["transport"] = _LimitedTransport(transport)
        super().__init__(*args, **kwargs)

    async def safe_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Executes a request with DNS pinning, a response size budget and manual redirect traversal.
        """
        max_redirects = kwargs.pop("max_redirects", 3)
        max_bytes = kwargs.pop("max_bytes", MAX_RESPONSE_BYTES)
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Accept-Encoding"] = "identity"   # no compression: the byte limit is the real size
        kwargs["headers"] = headers
        extensions = dict(kwargs.pop("extensions", None) or {})
        extensions["sentinel_max_bytes"] = max_bytes
        kwargs["extensions"] = extensions
        current_url = url

        for attempt in range(max_redirects + 1):
            # Egress guard first: a blocked host is never even resolved. Raises EgressBlocked.
            rec = egress_guard.check(method, urllib.parse.urlparse(current_url).hostname)
            is_safe, pinned_ip, error = resolve_and_validate_url(current_url)
            if not is_safe:
                egress_guard.record_result(rec, blocked_reason=f"SSRF protection: {error}")
                raise ValueError(f"SSRF blocked: {error}")

            hostname = urllib.parse.urlparse(current_url).hostname.lower()
            self._pinned_backend.pins[hostname] = pinned_ip

            try:
                response = await self.request(method, current_url, **kwargs)
            except BaseException as e:   # includes cancellation and oversized bodies
                egress_guard.record_result(rec, error=type(e).__name__)
                raise
            egress_guard.record_result(rec, status=response.status_code, bytes_in=len(response.content))

            if response.status_code in (301, 302, 303, 307, 308):
                if attempt == max_redirects:
                    raise ValueError("Too many redirects")
                location = response.headers.get("Location")
                if not location:
                    return response
                # Resolve relative redirects
                current_url = urllib.parse.urljoin(current_url, location)
                continue

            return response

        raise ValueError("Unexpected redirect loop termination")
