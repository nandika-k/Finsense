import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Initialize MCP server
app = Server("finsense-news")

# Register list_tools handler
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="fetch_headlines",
            description="Fetch news headlines",
            inputSchema={"type": "object", "properties": {"sector": {"type": "string"}, "timeframe": {"type": "string"}}, "required": ["sector", "timeframe"]}
        ),
        Tool(
            name="extract_risk_themes",
            description="Extract risk themes from headlines",
            inputSchema={"type": "object", "properties": {"headlines": {"type": "array", "items": {"type": "string"}}}, "required": ["headlines"]}
        )
    ]

# Register call_tool handler
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "fetch_headlines":
        sector = arguments.get("sector", "")
        timeframe = arguments.get("timeframe", "")
        headlines = [
            f"Headline1 for {sector} {timeframe}",
            f"Headline2 for {sector} {timeframe}"
        ]
        return [TextContent(type="text", text=str(headlines))]
    elif name == "extract_risk_themes":
        headlines = arguments.get("headlines", [])
        themes = [f"Theme for {h}" for h in headlines]
        return [TextContent(type="text", text=str(themes))]
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    print("ready", flush=True)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
