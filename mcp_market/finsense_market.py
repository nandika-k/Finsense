"""
Finsense Market MCP Server - Skeleton Implementation
A minimal MCP server exposing three placeholder tools for market data research.
"""

import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Initialize MCP server
app = Server("finsense-market")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    Register available tools with the MCP server.
    """
    return [
        Tool(
            name="get_stock_price",
            description="Get current/latest price for a given stock ticker",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'GOOGL')"
                    }
                },
                "required": ["ticker"]
            }
        ),
        Tool(
            name="get_returns",
            description="Get historical daily/weekly returns over a specified timeframe",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time period for returns (e.g., '1m', '3m', '1y')"
                    }
                },
                "required": ["ticker", "timeframe"]
            }
        ),
        Tool(
            name="get_sector_summary",
            description="Get aggregated sector-level summary including performance metrics",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Financial sector name (e.g., 'technology', 'healthcare', 'energy')"
                    }
                },
                "required": ["sector"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Handle tool execution requests.
    Returns hardcoded placeholder data for each tool.
    """
    
    if name == "get_stock_price":
        # Return placeholder stock price
        ticker = arguments.get("ticker", "UNKNOWN")
        
        placeholder_price = {
            "ticker": ticker,
            "price": 152.34,
            "currency": "USD",
            "timestamp": "2025-01-15T16:00:00Z",
            "change": 2.45,
            "change_percent": 1.63
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_price)
        )]
    
    elif name == "get_returns":
        # Return placeholder historical returns
        ticker = arguments.get("ticker", "UNKNOWN")
        timeframe = arguments.get("timeframe", "unknown")
        
        placeholder_returns = {
            "ticker": ticker,
            "timeframe": timeframe,
            "returns": [0.012, -0.008, 0.015, 0.003, -0.011, 0.019, 0.007],
            "period": "daily",
            "start_date": "2024-12-15",
            "end_date": "2025-01-15"
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_returns)
        )]
    
    elif name == "get_sector_summary":
        # Return placeholder sector summary
        sector = arguments.get("sector", "unknown")
        
        placeholder_summary = {
            "sector": sector,
            "avg_return": 0.045,
            "volatility": 0.18,
            "top_performers": ["AAPL", "MSFT", "NVDA"],
            "bottom_performers": ["IBM", "INTC"],
            "market_cap_total": "12.5T",
            "num_stocks": 45,
            "sector_beta": 1.12
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_summary)
        )]
    
    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


async def main():
    """
    Run the MCP server using stdio transport.
    """
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())