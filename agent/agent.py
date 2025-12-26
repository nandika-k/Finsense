"""
Finsense Coordinator Agent - Skeleton Implementation
A minimal agent that coordinates across News, Market, and Risk MCP servers.
"""

import asyncio
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NEWS_SERVER = BASE_DIR / "mcp_news" / "finsense_news.py"

news_params = StdioServerParameters(
    command="python",
    args=[str(NEWS_SERVER)]
)


class FinsenseCoordinator:
    """
    Coordinator agent that orchestrates tools from multiple MCP servers.
    """
    
    def __init__(self):
        self.news_session = None
        self.market_session = None
        self.risk_session = None
        self.news_tools = []
        self.market_tools = []
        self.risk_tools = []
        self.exit_stack = None
    
    async def connect_servers(self):
        """
        Connect to all MCP servers and list their available tools.
        """
        # Create single exit stack for all connections
        self.exit_stack = AsyncExitStack()
        
        # Connect to News MCP server
        news_params = StdioServerParameters(
            command="python",
            args=["mcp_news/finsense_news.py"]
        )
        self.news_session = await self._connect_server(news_params, self.exit_stack)
        self.news_tools = await self._list_tools(self.news_session)
        
        # Connect to Market MCP server
        market_params = StdioServerParameters(
            command="python",
            args=["mcp_market/finsense_market.py"]
        )
        self.market_session = await self._connect_server(market_params, self.exit_stack)
        self.market_tools = await self._list_tools(self.market_session)
        
        # Connect to Risk MCP server
        risk_params = StdioServerParameters(
            command="python",
            args=["mcp_risk/finsense_risk.py"]
        )
        self.risk_session = await self._connect_server(risk_params, self.exit_stack)
        self.risk_tools = await self._list_tools(self.risk_session)
    
    async def _connect_server(self, params, exit_stack):
        """
        Helper to connect to an MCP server using AsyncExitStack.
        """
        read_stream, write_stream = await exit_stack.enter_async_context(stdio_client(params))
        session = ClientSession(read_stream, write_stream)
        await session.initialize()
        return session
    
    async def _list_tools(self, session):
        """
        Helper to list tools from a connected session.
        """
        result = await session.list_tools()
        return result.tools
    
    async def call_news_tool(self, tool_name, arguments):
        """
        Call a tool from the News MCP server.
        """
        result = await self.news_session.call_tool(tool_name, arguments)
        return result.content[0].text
    
    async def call_market_tool(self, tool_name, arguments):
        """
        Call a tool from the Market MCP server.
        """
        result = await self.market_session.call_tool(tool_name, arguments)
        return result.content[0].text
    
    async def call_risk_tool(self, tool_name, arguments):
        """
        Call a tool from the Risk MCP server.
        """
        result = await self.risk_session.call_tool(tool_name, arguments)
        return result.content[0].text
    
    async def analyze_sector_risk(self, sector, timeframe):
        """
        Example workflow: Analyze risk for a given sector by coordinating across servers.
        """
        print(f"Analyzing risk for sector: {sector} over {timeframe}")
        
        # Step 1: Fetch news headlines
        print("Fetching news headlines...")
        headlines = await self.call_news_tool(
            "fetch_headlines",
            {"sector": sector, "timeframe": timeframe}
        )
        print(f"Headlines: {headlines}")
        
        # Step 2: Get market data
        print("Getting sector summary...")
        sector_summary = await self.call_market_tool(
            "get_sector_summary",
            {"sector": sector}
        )
        print(f"Sector Summary: {sector_summary}")
        
        # Step 3: Compute volatility
        print("Computing sector volatility...")
        volatility = await self.call_risk_tool(
            "compute_sector_volatility",
            {"sector": sector, "timeframe": timeframe}
        )
        print(f"Volatility: {volatility}")
        
        # Step 4: Extract risk themes from headlines
        print("Extracting risk themes...")
        risk_themes = await self.call_news_tool(
            "extract_risk_themes",
            {"headlines": eval(headlines)}
        )
        print(f"Risk Themes: {risk_themes}")
        
        return {
            "sector": sector,
            "headlines": headlines,
            "sector_summary": sector_summary,
            "volatility": volatility,
            "risk_themes": risk_themes
        }
    
    async def compare_sectors_workflow(self, sector1, sector2, timeframe):
        """
        Example workflow: Compare two sectors across risk dimensions.
        """
        print(f"Comparing sectors: {sector1} vs {sector2} over {timeframe}")
        
        # Get comparison from risk server
        comparison = await self.call_risk_tool(
            "compare_sectors",
            {"sector1": sector1, "sector2": sector2, "timeframe": timeframe}
        )
        print(f"Sector Comparison: {comparison}")
        
        # Get correlation data
        correlations = await self.call_risk_tool(
            "compute_sector_correlations",
            {"sectors": [sector1, sector2], "timeframe": timeframe}
        )
        print(f"Correlations: {correlations}")
        
        return {
            "comparison": comparison,
            "correlations": correlations
        }
    
    async def cleanup(self):
        """
        Close all server connections.
        """
        if self.exit_stack:
            await self.exit_stack.aclose()


async def main():
    """
    Main entry point for the coordinator agent.
    """
    coordinator = FinsenseCoordinator()
    
    try:
        # Connect to all MCP servers
        print("Connecting to MCP servers...")
        await coordinator.connect_servers()
        
        print(f"News tools: {[t.name for t in coordinator.news_tools]}")
        print(f"Market tools: {[t.name for t in coordinator.market_tools]}")
        print(f"Risk tools: {[t.name for t in coordinator.risk_tools]}")
        
        # Run example workflow
        print("\n--- Running Sector Risk Analysis ---")
        result = await coordinator.analyze_sector_risk("technology", "30d")
        
        print("\n--- Running Sector Comparison ---")
        comparison = await coordinator.compare_sectors_workflow("technology", "healthcare", "3m")
    
    finally:
        # Cleanup
        await coordinator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())