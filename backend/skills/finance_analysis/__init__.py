"""
Skill: finance_analysis
Fetches read-only market data for analysis. Autonomous trading is strictly prohibited.
Risk Tier: 2 (requires user confirmation for network privacy)
Capabilities: NETWORK_ACCESS
"""
import asyncio
import json
from app.core.network_utils import SafeAsyncClient
from app.core.request_context import request_context

async def _async_get_market_data(symbol: str) -> str:
    """Asynchronously fetch Yahoo Finance chart data using SafeAsyncClient."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        async with SafeAsyncClient() as client:
            response = await client.safe_request("GET", url, headers=headers, timeout=5.0)
            
        if response.status_code != 200:
            return f"<untrusted_content>Error: API returned status code {response.status_code} for symbol {symbol}</untrusted_content>"
            
        data = response.json()
        
        # Yahoo finance chart API parsing
        if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
            result = data["chart"]["result"][0]
            meta = result.get("meta", {})
            currency = meta.get("currency", "USD")
            regularMarketPrice = meta.get("regularMarketPrice", "Unknown")
            previousClose = meta.get("previousClose", "Unknown")
            
            output = {
                "symbol": symbol,
                "currency": currency,
                "regularMarketPrice": regularMarketPrice,
                "previousClose": previousClose
            }
            
            raw_result = json.dumps(output, indent=2)
            return f"<untrusted_content>{raw_result}</untrusted_content>"
        else:
            return f"<untrusted_content>Error: No data found for symbol {symbol}</untrusted_content>"
            
    except Exception as e:
        return f"<untrusted_content>Network Error fetching data for {symbol}: {str(e)}</untrusted_content>"

def get_market_data(symbol: str, request_id: str = None) -> str:
    """
    Fetches real-time or historical stock/crypto price data for analysis.
    Output is wrapped in <untrusted_content> tags.
    """
    # Create an event loop for synchronous invocation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    task = loop.create_task(_async_get_market_data(symbol))
    
    if request_id:
        request_context.register_task(request_id, task)
        
    try:
        result = loop.run_until_complete(task)
        # Cap at 10KB just in case
        if len(result) > 10240:
            result = result[:10240] + "\n... [TRUNCATED]</untrusted_content>"
        return result
    except asyncio.CancelledError:
        return "Error: Finance research task was cancelled by the user."
    except Exception as e:
        return f"<untrusted_content>System Error: {e}</untrusted_content>"
    finally:
        if request_id:
            request_context.unregister_task(request_id)
        loop.close()
