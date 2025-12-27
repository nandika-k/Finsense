"""
Finsense Coordinator Agent - Windows-safe Implementation
Launches MCP servers, waits for readiness, and connects via stdio_client.
"""

import asyncio
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from pathlib import Path
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

class FinsenseCoordinator:
    def __init__(self):
        self.news_session: ClientSession | None = None
        self.market_session: ClientSession | None = None
        self.risk_session: ClientSession | None = None
        self.news_tools = []
        self.market_tools = []
        self.risk_tools = []
        self.exit_stack: AsyncExitStack | None = None
        self.processes = []

    async def connect_servers(self):
        logger.info("connect_servers called")
        self.exit_stack = AsyncExitStack()

        # --- News MCP Server ---
        news_params = StdioServerParameters(
            command="python",
            args=[str(BASE_DIR / "mcp_news/finsense_news.py")]
        )
        self.news_session = await self._connect_server(news_params)
        self.news_tools = await self._list_tools(self.news_session)

        # --- Market MCP Server ---
        market_params = StdioServerParameters(
            command="python",
            args=[str(BASE_DIR / "mcp_market/finsense_market.py")]
        )
        self.market_session = await self._connect_server(market_params)
        self.market_tools = await self._list_tools(self.market_session)

        # --- Risk MCP Server ---
        risk_params = StdioServerParameters(
            command="python",
            args=[str(BASE_DIR / "mcp_risk/finsense_risk.py")]
        )
        self.risk_session = await self._connect_server(risk_params)
        self.risk_tools = await self._list_tools(self.risk_session)

    async def _connect_server(self, server_params: StdioServerParameters):
        logger.info("Connecting to server with params: %s", server_params)
        if not self.exit_stack:
            raise RuntimeError("Exit stack not initialized")

        # Launch server subprocess
        proc = subprocess.Popen(
            [server_params.command, *server_params.args],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        self.processes.append(proc)

        # Wait for "ready" line
        logger.info("Waiting for server to be ready...")
        while True:
            line = proc.stdout.readline()
            if line == "":
                if proc.poll() is not None:
                    raise RuntimeError(f"Server {server_params.args} exited prematurely")
                await asyncio.sleep(0.1)
                continue
            line = line.strip()
            logger.debug("Server output: %s", line)
            if line.lower() == "ready":
                break

        # Connect via stdio_client
        read_stream, write_stream = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        session = ClientSession(read_stream, write_stream)
        await session.initialize()
        logger.info("Session initialized for: %s", server_params)
        return session

    async def _list_tools(self, session: ClientSession):
        logger.info("Listing tools from session")
        result = await session.list_tools()
        logger.debug("Tools returned: %s", [t.name for t in result.tools])
        return result.tools

    # --- Tool call helpers ---
    async def call_news_tool(self, tool_name, arguments):
        result = await self.news_session.call_tool(tool_name, arguments)
        return result.content[0].text

    async def call_market_tool(self, tool_name, arguments):
        result = await self.market_session.call_tool(tool_name, arguments)
        return result.content[0].text

    async def call_risk_tool(self, tool_name, arguments):
        result = await self.risk_session.call_tool(tool_name, arguments)
        return result.content[0].text

    # --- Workflow methods ---
    async def analyze_sector_risk(self, sector, timeframe):
        logger.info("analyze_sector_risk: sector=%s timeframe=%s", sector, timeframe)

        headlines = await self.call_news_tool("fetch_headlines", {"sector": sector, "timeframe": timeframe})
        sector_summary = await self.call_market_tool("get_sector_summary", {"sector": sector})
        volatility = await self.call_risk_tool("compute_sector_volatility", {"sector": sector, "timeframe": timeframe})
        risk_themes = await self.call_news_tool("extract_risk_themes", {"headlines": eval(headlines)})

        print(f"Sector: {sector}")
        print(f"Headlines: {headlines}")
        print(f"Sector Summary: {sector_summary}")
        print(f"Volatility: {volatility}")
        print(f"Risk Themes: {risk_themes}")

        return {
            "sector": sector,
            "headlines": headlines,
            "sector_summary": sector_summary,
            "volatility": volatility,
            "risk_themes": risk_themes
        }

    async def compare_sectors_workflow(self, sector1, sector2, timeframe):
        comparison = await self.call_risk_tool("compare_sectors", {"sector1": sector1, "sector2": sector2, "timeframe": timeframe})
        correlations = await self.call_risk_tool("compute_sector_correlations", {"sectors": [sector1, sector2], "timeframe": timeframe})

        print(f"Comparing sectors: {sector1} vs {sector2} over {timeframe}")
        print(f"Sector Comparison: {comparison}")
        print(f"Correlations: {correlations}")

        return {
            "comparison": comparison,
            "correlations": correlations
        }

    async def cleanup(self):
        if self.exit_stack:
            await self.exit_stack.aclose()
            logger.info("All MCP server connections closed")

        # Terminate subprocesses
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        logger.info("All MCP server subprocesses terminated")

async def main():
    logger.info("Starting FinsenseCoordinator agent")
    coordinator = FinsenseCoordinator()

    try:
        print("Connecting to MCP servers...")
        await coordinator.connect_servers()

        print(f"News tools: {[t.name for t in coordinator.news_tools]}")
        print(f"Market tools: {[t.name for t in coordinator.market_tools]}")
        print(f"Risk tools: {[t.name for t in coordinator.risk_tools]}")

        print("\n--- Running Sector Risk Analysis ---")
        await coordinator.analyze_sector_risk("technology", "30d")

        print("\n--- Running Sector Comparison ---")
        await coordinator.compare_sectors_workflow("technology", "healthcare", "3m")

    finally:
        await coordinator.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
