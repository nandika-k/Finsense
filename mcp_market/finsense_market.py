import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import sys
import os
import json
import yfinance as yf
from datetime import datetime, timedelta

# Ensure stdout is unbuffered
sys.stdout.reconfigure(line_buffering=True)

# Only log to file if DEBUG environment variable is set
if os.getenv("MCP_DEBUG"):
    import logging
    from pathlib import Path
    LOG_FILE = Path(__file__).parent / "finsense_market.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, mode='w')]
    )
    logger = logging.getLogger(__name__)
    
    def log(msg):
        logger.debug(msg)
else:
    def log(msg):
        pass

# --- MCP Server Initialization ---
app = Server("finsense-market")

# --- list_tools Handler ---
@app.list_tools()
async def list_tools() -> list[Tool]:
    log("list_tools called")
    return [
        Tool(
            name="get_sector_summary",
            description="Get market summary for a sector",
            inputSchema={
                "type": "object",
                "properties": {"sector": {"type": "string"}},
                "required": ["sector"]
            }
        ),
        Tool(
            name="get_stock_price",
            description="Get current stock price for a ticker symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL, MSFT)"}
                },
                "required": ["ticker"]
            }
        ),
        Tool(
            name="get_market_indices",
            description="Get current values of major market indices",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

# --- call_tool Handler ---
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"call_tool: {name}")
    
    if name == "get_sector_summary":
        sector = arguments.get("sector", "")
        # Map sectors to representative ETFs
        sector_map = {
            "technology": "XLK",
            "healthcare": "XLV",
            "financial-services": "XLF",
            "energy": "XLE",
            "consumer": "XLY",
            "industrials": "XLI",
            "materials": "XLB",
            "real-estate": "XLRE",
            "utilities": "XLU",
            "communications": "XLC"
        }
        ticker_symbol = sector_map.get(sector.lower(), "SPY")
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="1mo")
            
            if len(hist) > 0:
                current_price = hist['Close'].iloc[-1]
                price_1w_ago = hist['Close'].iloc[-5] if len(hist) >= 5 else hist['Close'].iloc[0]
                price_1m_ago = hist['Close'].iloc[0]
                
                perf_1d = ((current_price - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) > 1 else 0
                perf_1w = ((current_price - price_1w_ago) / price_1w_ago * 100) if price_1w_ago > 0 else 0
                perf_1m = ((current_price - price_1m_ago) / price_1m_ago * 100) if price_1m_ago > 0 else 0
                
                summary = {
                    "sector": sector,
                    "performance_1d": f"{perf_1d:+.2f}%",
                    "performance_1w": f"{perf_1w:+.2f}%",
                    "performance_1m": f"{perf_1m:+.2f}%",
                    "current_price": round(current_price, 2),
                    "market_cap": ticker.info.get("marketCap", "N/A"),
                    "volume": ticker.info.get("volume", "N/A")
                }
            else:
                summary = {"sector": sector, "error": "No data available"}
        except Exception as e:
            log(f"Error fetching sector summary: {e}")
            summary = {"sector": sector, "error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(summary, default=str))]
    
    elif name == "get_stock_price":
        ticker = arguments.get("ticker", "").upper()
        try:
            tick = yf.Ticker(ticker)
            info = tick.info
            hist = tick.history(period="1d")
            
            if len(hist) > 0:
                current_price = hist['Close'].iloc[-1]
                if len(hist) > 1:
                    previous_price = hist['Close'].iloc[-2]
                    change = current_price - previous_price
                    change_percent = (change / previous_price * 100) if previous_price > 0 else 0
                else:
                    change = 0
                    change_percent = 0
                
                stock_data = {
                    "ticker": ticker,
                    "price": round(current_price, 2),
                    "change": f"{change:+.2f}",
                    "change_percent": f"{change_percent:+.2f}%",
                    "volume": info.get("volume", "N/A"),
                    "market_cap": info.get("marketCap", "N/A"),
                    "pe_ratio": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A"
                }
            else:
                stock_data = {"ticker": ticker, "error": "No price data available"}
        except Exception as e:
            log(f"Error fetching stock price: {e}")
            stock_data = {"ticker": ticker, "error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(stock_data, default=str))]
    
    elif name == "get_market_indices":
        indices_map = {
            "SPX": "^GSPC",
            "DJI": "^DJI",
            "IXIC": "^IXIC",
            "RUT": "^RUT"
        }
        indices = {}
        
        try:
            for name_key, symbol in indices_map.items():
                tick = yf.Ticker(symbol)
                hist = tick.history(period="1d")
                
                if len(hist) > 0:
                    current_price = hist['Close'].iloc[-1]
                    if len(hist) > 1:
                        previous_price = hist['Close'].iloc[-2]
                        change_percent = ((current_price - previous_price) / previous_price * 100) if previous_price > 0 else 0
                    else:
                        change_percent = 0
                    
                    indices[name_key] = {
                        "value": round(current_price, 2),
                        "change": f"{change_percent:+.2f}%"
                    }
        except Exception as e:
            log(f"Error fetching market indices: {e}")
        
        return [TextContent(type="text", text=json.dumps(indices, default=str))]
    
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

# --- Main Entrypoint ---
async def main():
    log("Server starting")
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            log("stdio_server initialized, starting message loop")
            init_options = app.create_initialization_options()
            await app.run(
                read_stream, 
                write_stream, 
                init_options
            )
            log("Server run completed normally")
    except Exception as e:
        log(f"Server error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        sys.exit(1)