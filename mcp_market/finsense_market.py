import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import sys
import os

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
        # Mock data - replace with real API calls
        summary = {
            "sector": sector,
            "performance_1d": "+1.2%",
            "performance_1w": "+3.4%",
            "performance_1m": "+5.6%",
            "top_performers": [
                {"ticker": "ABC", "change": "+5.2%"},
                {"ticker": "XYZ", "change": "+4.1%"}
            ],
            "market_cap": "$2.5T",
            "volume": "125M shares"
        }
        return [TextContent(type="text", text=str(summary))]
    
    elif name == "get_stock_price":
        ticker = arguments.get("ticker", "")
        # Mock data - replace with real API calls
        stock_data = {
            "ticker": ticker.upper(),
            "price": 150.25,
            "change": "+2.50",
            "change_percent": "+1.69%",
            "volume": "45.2M",
            "market_cap": "$2.5T",
            "pe_ratio": 28.5
        }
        return [TextContent(type="text", text=str(stock_data))]
    
    elif name == "get_market_indices":
        # Mock data - replace with real API calls
        indices = {
            "SPX": {"value": 4750.50, "change": "+0.8%"},
            "DJI": {"value": 37500.25, "change": "+0.6%"},
            "IXIC": {"value": 15200.75, "change": "+1.2%"},
            "RUT": {"value": 2050.30, "change": "+0.4%"}
        }
        return [TextContent(type="text", text=str(indices))]
    
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