import pytest
from unittest.mock import patch, MagicMock
from skills.finance_analysis import get_market_data

class TestFinanceAnalysis:
    
    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_get_market_data_success(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "chart": {
                "result": [{
                    "meta": {
                        "currency": "USD",
                        "regularMarketPrice": 150.0,
                        "previousClose": 149.0
                    }
                }]
            }
        }
        mock_request.return_value = mock_resp
        
        result = get_market_data("AAPL")
        
        assert "<untrusted_content>" in result
        assert "AAPL" in result
        assert "150.0" in result
        assert "149.0" in result
        assert "USD" in result
        
    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_get_market_data_not_found(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_request.return_value = mock_resp
        
        result = get_market_data("INVALID_SYMBOL")
        
        assert "Error: API returned status code 404" in result
        assert "<untrusted_content>" in result
        
    @patch("app.core.network_utils.httpx.AsyncClient.request")
    def test_get_market_data_malformed(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "bad structure"}
        mock_request.return_value = mock_resp
        
        result = get_market_data("AAPL")
        
        assert "Error: No data found for symbol AAPL" in result
        assert "<untrusted_content>" in result
