"""
Finsense News MCP Server - Skeleton Implementation
A minimal MCP server exposing three placeholder tools for financial news research.
"""

import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Initialize MCP server
app = Server("finsense-news")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    Register available tools with the MCP server.
    """
    return [
        Tool(
            name="fetch_headlines",
            description="Fetch news headlines for a given sector and timeframe",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "The financial sector (e.g., 'technology', 'healthcare', 'energy')"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time period for headlines (e.g., '24h', '7d', '30d')"
                    }
                },
                "required": ["sector", "timeframe"]
            }
        ),
        Tool(
            name="extract_risk_themes",
            description="Extract risk themes from a list of headlines",
            inputSchema={
                "type": "object",
                "properties": {
                    "headlines": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of news headlines to analyze"
                    }
                },
                "required": ["headlines"]
            }
        ),
        Tool(
            name="map_themes_to_sectors",
            description="Map identified risk themes to affected financial sectors",
            inputSchema={
                "type": "object",
                "properties": {
                    "themes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of risk themes to map"
                    }
                },
                "required": ["themes"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Handle tool execution requests.
    Returns hardcoded placeholder data for each tool.
    """
    
    if name == "fetch_headlines":
        # Return placeholder headlines
        sector = arguments.get("sector", "unknown")
        timeframe = arguments.get("timeframe", "unknown")
        
        placeholder_headlines = [
            f"Major {sector} company announces Q4 earnings beat",
            f"Regulatory concerns emerge in {sector} sector",
            f"{sector.capitalize()} stocks volatile amid market uncertainty",
            f"Analysts upgrade {sector} outlook for {timeframe}"
        ]
        
        return [TextContent(
            type="text",
            text=str(placeholder_headlines)
        )]
    
    elif name == "extract_risk_themes":
        # Return placeholder risk themes
        placeholder_themes = [
            "Regulatory Risk",
            "Market Volatility",
            "Earnings Uncertainty",
            "Geopolitical Tension"
        ]
        
        return [TextContent(
            type="text",
            text=str(placeholder_themes)
        )]
    
    elif name == "map_themes_to_sectors":
        # Return placeholder sector mapping
        placeholder_mapping = {
            "Regulatory Risk": ["healthcare", "technology", "finance"],
            "Market Volatility": ["technology", "energy", "retail"],
            "Earnings Uncertainty": ["retail", "manufacturing"],
            "Geopolitical Tension": ["energy", "defense", "materials"]
        }
        
        return [TextContent(
            type="text",
            text=str(placeholder_mapping)
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