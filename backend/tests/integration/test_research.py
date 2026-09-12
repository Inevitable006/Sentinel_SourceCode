import sys
import os
import asyncio
import httpx
import time
from app.core.research_service import research_service
from app.core.network_utils import resolve_and_validate_url, SafeAsyncClient
from app.core.request_context import request_context
import unittest.mock

def test_ssrf():
    print("Testing SSRF protection (resolve_and_validate_url)...")
    
    # Test strict scheme/credentials
    is_safe, _, err = resolve_and_validate_url("http://example.com")
    assert not is_safe and "HTTPS" in err, f"Failed: {err}"
    
    is_safe, _, err = resolve_and_validate_url("https://user:pass@example.com")
    assert not is_safe and "Credentials" in err, f"Failed: {err}"
    
    is_safe, _, err = resolve_and_validate_url("https://example.com:8443")
    assert not is_safe and "port 443" in err, f"Failed: {err}"
    
    # Test restricted IP ranges (simulated via direct IP URLs to avoid DNS dependence in tests)
    urls_to_block = [
        "https://127.0.0.1/",
        "https://localhost/",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.1/",
        "https://192.168.1.1/",
        "https://[::1]/",
        "https://[::ffff:127.0.0.1]/"
    ]
    for url in urls_to_block:
        is_safe, _, err = resolve_and_validate_url(url)
        assert not is_safe, f"Failed to block {url}"
    print("PASS: SSRF validations correctly blocked restricted ranges, schemes, and credentials.")

def test_network_cancellation():
    print("\nTesting Network Cancellation (SafeAsyncClient)...")
    
    # We use a mocked AsyncTransport that hangs forever to verify cancellation
    class HangingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            await asyncio.sleep(100.0) # Hang
            return httpx.Response(200, content=b"OK")
            
    async def run_cancellation_test():
        client = SafeAsyncClient(transport=HangingTransport())
        request_id = "test-req-id-123"
        
        # Wrapping in a task to cancel it
        async def do_fetch():
            # Mocking resolve_and_validate_url since the hanging transport intercepts everything anyway
            with unittest.mock.patch('app.core.network_utils.resolve_and_validate_url', return_value=(True, '1.1.1.1', None)):
                return await client.safe_request("GET", "https://example.com")
                
        task = asyncio.create_task(do_fetch())
        request_context.register_task(request_id, task)
        
        start_time = time.time()
        
        # Schedule cancellation after 0.5 seconds
        async def cancel_it():
            await asyncio.sleep(0.5)
            request_context.cancel_request(request_id)
            
        asyncio.create_task(cancel_it())
        
        try:
            await task
            assert False, "Task completed instead of being cancelled"
        except asyncio.CancelledError:
            duration = time.time() - start_time
            # Stable cancellation deadline test (< 2.0s)
            assert duration < 2.0, f"Cancellation took too long: {duration}s"
            print(f"PASS: Network request successfully cancelled in {duration:.2f}s")
        finally:
            request_context.unregister_task(request_id)
            await client.aclose()
            
    asyncio.run(run_cancellation_test())

def test_valid_search():
    print("\nTesting valid web search (DDGS)...")
    res = research_service.search("Apple stock price today")
    if "Search Results for" not in res or "Source:" not in res or "Snippet:" not in res:
        print(f"FAILED Response: {res}")
        assert False, "Missing expected text in response"
    print("PASS: Valid search returned content")
    print(f"Length of response: {len(res)} characters")

def test_local_mode():
    print("\nTesting Local-Only Mode...")
    research_service.set_local_mode(True)
    res = research_service.search("Microsoft stock")
    assert "Local Only mode is enabled" in res
    print("PASS: Search blocked in local mode")
    research_service.set_local_mode(False)

if __name__ == "__main__":
    try:
        test_ssrf()
        test_network_cancellation()
        test_valid_search()
        test_local_mode()
        print("\nAll tests passed successfully.")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
