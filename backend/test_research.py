import sys
import os
from app.core.research_service import research_service

def test_ssrf():
    print("Testing SSRF protection...")
    urls_to_block = [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.1.1/"
    ]
    for url in urls_to_block:
        res = research_service.fetch_url(url)
        assert "SSRF blocked" in res or "invalid" in res.lower()
        print(f"PASS: Blocked {url}")

def test_https():
    print("\nTesting HTTPS enforcement...")
    res = research_service.fetch_url("http://example.com")
    assert "SSRF blocked" in res or "invalid" in res.lower()
    print("PASS: Blocked non-HTTPS")

def test_valid_search():
    print("\nTesting valid web search...")
    res = research_service.search("Apple stock price today")
    if "Search Results for" not in res or "Source:" not in res or "Content:" not in res:
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
        test_https()
        test_valid_search()
        test_local_mode()
        print("\nAll tests passed successfully.")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
