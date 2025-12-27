import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

app = Server("finsense-risk")

# List available tools
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="compute_sector_volatility",
            description="Compute volatility for a sector",
            inputSchema={"type": "object", "properties": {"sector": {"type": "string"}, "timeframe": {"type": "string"}}, "required": ["sector", "timeframe"]}
        ),
        Tool(
            name="compare_sectors",
            description="Compare two sectors",
            inputSchema={"type": "object", "properties": {"sector1": {"type": "string"}, "sector2": {"type": "string"}, "timeframe": {"type": "string"}}, "required": ["sector1", "sector2", "timeframe"]}
        ),
        Tool(
            name="compute_sector_correlations",
            description="Compute correlation between sectors",
            inputSchema={"type": "object", "properties": {"sectors": {"type": "array", "items": {"type": "string"}}, "timeframe": {"type": "string"}}, "required": ["sectors", "timeframe"]}
        )
    ]

# Handle tool calls
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "compute_sector_volatility":
        sector = arguments.get("sector", "")
        timeframe = arguments.get("timeframe", "")
        volatility = f"Volatility for {sector} over {timeframe}: 1.23%"
        return [TextContent(type="text", text=volatility)]
    elif name == "compare_sectors":
        s1 = arguments.get("sector1", "")
        s2 = arguments.get("sector2", "")
        timeframe = arguments.get("timeframe", "")
        comparison = f"Comparison of {s1} vs {s2} over {timeframe}: {s1} outperforms {s2}."
        return [TextContent(type="text", text=comparison)]
    elif name == "compute_sector_correlations":
        sectors = arguments.get("sectors", [])
        timeframe = arguments.get("timeframe", "")
        correlation = f"Correlation between {', '.join(sectors)} over {timeframe}: 0.85"
        return [TextContent(type="text", text=correlation)]
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    print("ready", flush=True)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
