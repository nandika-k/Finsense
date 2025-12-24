"""
Finsense Market MCP Server - Skeleton Implementation
A minimal MCP server exposing four placeholder tools for market data research.
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
            name="get_returns",
            description="Get historical returns for a stock ticker over a timeframe",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., 'AAPL', 'MSFT')"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time period for returns (e.g., '1d', '1w', '1m', '1y')"
                    }
                },
                "required": ["ticker", "timeframe"]
            }
        ),
        Tool(
            name="get_stock_metrics",
            description="Get key metrics for a stock ticker over a timeframe",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., 'AAPL', 'MSFT')"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time period for metrics (e.g., '1d', '1w', '1m', '1y')"
                    }
                },
                "required": ["ticker", "timeframe"]
            }
        ),
        Tool(
            name="get_sector_metrics",
            description="Get aggregated metrics for a financial sector over a timeframe",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Financial sector (e.g., 'technology', 'healthcare', 'energy')"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time period for metrics (e.g., '1d', '1w', '1m', '1y')"
                    }
                },
                "required": ["sector", "timeframe"]
            }
        ),
        Tool(
            name="compare_sectors",
            description="Compare metrics across multiple sectors over a timeframe",
            inputSchema={
                "type": "object",
                "properties": {
                    "sectors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of sectors to compare (e.g., ['technology', 'healthcare'])"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time period for comparison (e.g., '1d', '1w', '1m', '1y')"
                    }
                },
                "required": ["sectors", "timeframe"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Handle tool execution requests.
    Returns hardcoded placeholder data for each tool.
    """
    
    if name == "get_returns":
        # Return placeholder returns data
        ticker = arguments.get("ticker", "UNKNOWN")
        timeframe = arguments.get("timeframe", "unknown")
        
        placeholder_returns = {
            "ticker": ticker,
            "timeframe": timeframe,
            "total_return": 12.5,
            "daily_returns": [0.5, -0.3, 1.2, 0.8, -0.1],
            "cumulative_return": 12.5
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_returns)
        )]
    
    elif name == "get_stock_metrics":
        # Return placeholder stock metrics
        ticker = arguments.get("ticker", "UNKNOWN")
        timeframe = arguments.get("timeframe", "unknown")
        
        placeholder_metrics = {
            "ticker": ticker,
            "timeframe": timeframe,
            "volatility": 18.3,
            "sharpe_ratio": 1.45,
            "max_drawdown": -8.2,
            "beta": 1.12,
            "avg_volume": 45000000
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_metrics)
        )]
    
    elif name == "get_sector_metrics":
        # Return placeholder sector metrics
        sector = arguments.get("sector", "unknown")
        timeframe = arguments.get("timeframe", "unknown")
        
        placeholder_metrics = {
            "sector": sector,
            "timeframe": timeframe,
            "avg_return": 8.7,
            "avg_volatility": 15.2,
            "top_performers": ["STOCK1", "STOCK2", "STOCK3"],
            "worst_performers": ["STOCK4", "STOCK5"],
            "sector_beta": 1.05
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_metrics)
        )]
    
    elif name == "compare_sectors":
        # Return placeholder sector comparison
        sectors = arguments.get("sectors", [])
        timeframe = arguments.get("timeframe", "unknown")
        
        placeholder_comparison = {
            "timeframe": timeframe,
            "sectors": {
                sector: {
                    "return": 10.0 + (i * 2.5),
                    "volatility": 15.0 + (i * 1.5),
                    "sharpe_ratio": 1.2 + (i * 0.1)
                }
                for i, sector in enumerate(sectors)
            },
            "best_sector": sectors[0] if sectors else "unknown",
            "worst_sector": sectors[-1] if sectors else "unknown"
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_comparison)
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