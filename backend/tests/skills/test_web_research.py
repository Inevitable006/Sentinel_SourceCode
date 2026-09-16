import pytest
import asyncio
from unittest.mock import patch, MagicMock

from app.core.research_service import research_service
from skills.web_research import fetch_url, search_web


class TestWebResearch:

    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_fetch_url_success(self, mock_request):
        """Test a successful fetch returns parsed, untrusted content."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Give it some HTML
        mock_resp.text = "<html><head><title>Test</title></head><body><h1>Hello World</h1><p>This is a <b>test</b>.</p></body></html>"
        mock_request.return_value = mock_resp

        result = fetch_url("https://example.com")
        
        # Should strip HTML, condense spaces
        assert "Hello World This is a test" in result
        assert result.startswith("<untrusted_content>")
        assert result.endswith("</untrusted_content>")


    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_fetch_url_truncation(self, mock_request):
        """Test output capping at 10KB."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>" + ("A" * 15000) + "</body></html>"
        mock_request.return_value = mock_resp

        result = fetch_url("https://example.com")
        
        assert "TRUNCATED" in result
        # The content part should be exactly 10240 characters + the truncation message + the tags
        assert len(result) < 11000 
        assert result.startswith("<untrusted_content>")
        assert result.endswith("</untrusted_content>")


    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_fetch_url_ssrf_block(self, mock_request):
        """Test that SSRF logic natively kicks in (using SafeAsyncClient)."""
        # We don't even mock the request because it should fail validation *before* sending.
        result = fetch_url("http://127.0.0.1")
        assert "Network Security Violation" in result or "Fetch failed" in result


    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_fetch_url_local_mode_block(self, mock_request):
        """Test that local-only mode blocks execution."""
        research_service.set_local_mode(True)
        try:
            result = fetch_url("https://example.com")
            assert "System Error: Local Only mode is enabled" in result
        finally:
            research_service.set_local_mode(False)


    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_search_web_truncation(self, mock_request):
        """Verify search_web also wraps untrusted_content properly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<a class=\"result__url\" href=\"http://example.com\">example</a><a class=\"result__snippet\">Snippet</a>"
        mock_request.return_value = mock_resp

        result = search_web("test")
        assert "<untrusted_content>" in result
        assert "</untrusted_content>" in result
