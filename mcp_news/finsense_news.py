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
    LOG_FILE = Path(__file__).parent / "finsense_news.log"
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
app = Server("finsense-news")

# --- list_tools Handler ---
@app.list_tools()
async def list_tools() -> list[Tool]:
    log("list_tools called")
    return [
        Tool(
            name="fetch_headlines",
            description="Fetch news headlines",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {"type": "string"},
                    "timeframe": {"type": "string"}
                },
                "required": ["sector", "timeframe"]
            }
        ),
        Tool(
            name="extract_risk_themes",
            description="Extract risk themes from headlines",
            inputSchema={
                "type": "object",
                "properties": {
                    "headlines": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["headlines"]
            }
        )
    ]

# --- call_tool Handler ---
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"call_tool: {name}")
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