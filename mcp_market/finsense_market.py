import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

app = Server("finsense-market")

# List available tools
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_sector_summary",
            description="Get market summary for a sector",
            inputSchema={"type": "object", "properties": {"sector": {"type": "string"}}, "required": ["sector"]}
        ),
        Tool(
            name="get_stock_price",
            description="Get latest stock price for a ticker",
            inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}
        )
    ]

# Handle tool calls
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_sector_summary":
        sector = arguments.get("sector", "")
        summary = f"Summary of {sector} sector: Market is stable."
        return [TextContent(type="text", text=summary)]
    elif name == "get_stock_price":
        ticker = arguments.get("ticker", "")
        price = f"Price for {ticker}: $123.45"
        return [TextContent(type="text", text=price)]
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    print("ready", flush=True)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
