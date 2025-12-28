import asyncio
import json
import sys
from pathlib import Path
import logging
import subprocess
from typing import Dict, Any, List
import warnings

# Suppress Windows ProactorEventLoop pipe warnings
warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed.*<_ProactorBasePipeTransport.*")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


class MCPClient:
    """Manual MCP client that works reliably on Windows"""
    
    def __init__(self, server_path: Path):
        self.server_path = server_path
        self.process = None
        self.request_id = 0
        self.initialized = False

    async def start(self):
        """Start the MCP server process"""
        logger.info("Starting MCP server: %s", self.server_path.name)
        
        if not self.server_path.exists():
            raise FileNotFoundError(f"Server file not found: {self.server_path}")
        
        # Use PYTHONUNBUFFERED to disable output buffering
        env = {**subprocess.os.environ, "PYTHONUNBUFFERED": "1"}
        
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",  # Unbuffered
            str(self.server_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        logger.info("Server started with PID: %s", self.process.pid)
        
        # Give server a moment to initialize
        await asyncio.sleep(0.1)
        
        # Initialize the MCP connection
        await self._initialize()
        
    async def _send_request(self, method: str, params: dict = None) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        request_str = json.dumps(request) + "\n"
        logger.debug("→ %s", request_str.strip())
        
        self.process.stdin.write(request_str.encode('utf-8'))
        await self.process.stdin.drain()
        
        # Read response, skipping empty lines
        max_attempts = 10
        for attempt in range(max_attempts):
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=10.0
            )
            
            response_text = response_line.decode('utf-8').strip()
            
            if not response_text:
                if attempt < max_attempts - 1:
                    continue
                raise Exception("No response from server")
            
            logger.debug("← %s", response_text[:200] + "..." if len(response_text) > 200 else response_text)
            
            response = json.loads(response_text)
            
            if "error" in response:
                raise Exception(f"JSON-RPC error: {response['error']}")
            
            return response.get("result")
        
        raise Exception("Failed to get valid response")
    
    async def _send_notification(self, method: str, params: dict = None):
        """Send a JSON-RPC notification (no response expected)"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        notification_str = json.dumps(notification) + "\n"
        logger.debug("→ [notification] %s", notification_str.strip())
        
        self.process.stdin.write(notification_str.encode('utf-8'))
        await self.process.stdin.drain()
    
    async def _initialize(self):
        """Initialize the MCP connection"""
        logger.info("Initializing MCP session...")
        
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "finsense-coordinator",
                "version": "1.0.0"
            }
        })
        
        logger.info("Connected to: %s v%s", 
                   result["serverInfo"]["name"],
                   result["serverInfo"]["version"])
        
        # Send initialized notification
        await self._send_notification("notifications/initialized")
        
        self.initialized = True
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        result = await self._send_request("tools/list")
        return result.get("tools", [])
    
    async def call_tool(self, name: str, arguments: dict) -> Dict[str, Any]:
        """Call a tool"""
        logger.info("Calling tool: %s", name)
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        return result
    
    async def close(self):
        """Close the connection gracefully"""
        if self.process and self.process.returncode is None:
            try:
                # Close stdin first to signal the server to shut down
                if self.process.stdin and not self.process.stdin.is_closing():
                    self.process.stdin.close()
                    await asyncio.sleep(0.1)
                
                # Give the process time to exit gracefully
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    # If it doesn't exit, terminate it
                    self.process.terminate()
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        # Last resort: kill it
                        self.process.kill()
                        await self.process.wait()
                
                logger.info("Server stopped")
            except Exception as e:
                logger.debug("Error during cleanup: %s", e)


class FinsenseCoordinator:
    """Coordinates multiple MCP servers for financial analysis"""
    
    def __init__(self):
        self.news_client: MCPClient | None = None
        self.risk_client: MCPClient | None = None
        self.market_client: MCPClient | None = None

    async def initialize(self):
        """Initialize all MCP server connections"""
        logger.info("Initializing Finsense Coordinator...")
        
        # Connect to news server
        news_server_path = BASE_DIR / "mcp_news" / "finsense_news.py"
        self.news_client = MCPClient(news_server_path)
        await self.news_client.start()
        
        # Connect to risk server
        risk_server_path = BASE_DIR / "mcp_risk" / "finsense_risk.py"
        self.risk_client = MCPClient(risk_server_path)
        await self.risk_client.start()
        
        # Connect to market server
        market_server_path = BASE_DIR / "mcp_market" / "finsense_market.py"
        self.market_client = MCPClient(market_server_path)
        await self.market_client.start()
        
        # List available tools from all servers
        news_tools = await self.news_client.list_tools()
        risk_tools = await self.risk_client.list_tools()
        market_tools = await self.market_client.list_tools()
        
        logger.info("News tools: %s", [t["name"] for t in news_tools])
        logger.info("Risk tools: %s", [t["name"] for t in risk_tools])
        logger.info("Market tools: %s", [t["name"] for t in market_tools])

    #news tools
    async def fetch_headlines(self, sector: str, timeframe: str) -> List[str]:
        """Fetch news headlines for a sector"""
        result = await self.news_client.call_tool("fetch_headlines", {
            "sector": sector,
            "timeframe": timeframe
        })
        
        content = result["content"][0]["text"]
        import ast
        headlines = ast.literal_eval(content)
        return headlines
    
    async def extract_risk_themes(self, headlines: List[str]) -> List[str]:
        """Extract risk themes from headlines"""
        result = await self.news_client.call_tool("extract_risk_themes", {
            "headlines": headlines
        })
        
        content = result["content"][0]["text"]
        import ast
        themes = ast.literal_eval(content)
        return themes

    #market tools
    async def get_market_indices(self) -> Dict[str, Any]:
        """Get current market indices"""
        result = await self.market_client.call_tool("get_market_indices", {})
        content = result["content"][0]["text"]
        import json
        indices = json.loads(content)
        return indices

    async def get_stock_price(self, ticker: str) -> Dict[str, Any]:
        """Get stock price for a ticker"""
        result = await self.market_client.call_tool("get_stock_price", {
            "ticker": ticker
        })
        content = result["content"][0]["text"]
        import json
        stock_data = json.loads(content)
        return stock_data

    async def get_sector_summary(self, sector: str) -> Dict[str, Any]:
        """Get sector summary"""
        result = await self.market_client.call_tool("get_sector_summary", {
            "sector": sector
        })
        content = result["content"][0]["text"]
        import json
        summary = json.loads(content)
        return summary

    #risk tools
    async def compute_sector_volatility(self, sector: str, timeframe: str) -> Dict[str, Any]:
        """Compute volatility for a sector"""
        result = await self.risk_client.call_tool("compute_sector_volatility", {
            "sector": sector,
            "timeframe": timeframe
        })
        content = result["content"][0]["text"]
        import ast
        volatility = ast.literal_eval(content)
        return volatility

    async def compare_sectors(self, sector1: str, sector2: str, timeframe: str) -> Dict[str, Any]:
        """Compare risk metrics between two sectors"""
        result = await self.risk_client.call_tool("compare_sectors", {
            "sector1": sector1,
            "sector2": sector2,
            "timeframe": timeframe
        })
        content = result["content"][0]["text"]
        import ast
        comparison = ast.literal_eval(content)
        return comparison

    async def compute_sector_correlations(self, sectors: List[str], timeframe: str) -> Dict[str, Any]:
        """Compute correlations between sectors"""
        result = await self.risk_client.call_tool("compute_sector_correlations", {
            "sectors": sectors,
            "timeframe": timeframe
        })
        content = result["content"][0]["text"]
        import ast
        correlations = ast.literal_eval(content)
        return correlations

    async def calculate_var(self, portfolio: Dict[str, Any], confidence_level: float, timeframe: str) -> Dict[str, Any]:
        """Calculate Value at Risk (VaR) for a portfolio"""
        result = await self.risk_client.call_tool("calculate_var", {
            "portfolio": portfolio,
            "confidence_level": confidence_level,
            "timeframe": timeframe
        })
        content = result["content"][0]["text"]
        import ast
        var_data = ast.literal_eval(content)
        return var_data

    async def stress_test(self, sector: str, scenario: str) -> Dict[str, Any]:
        """Perform stress testing on a sector or portfolio"""
        result = await self.risk_client.call_tool("stress_test", {
            "sector": sector,
            "scenario": scenario
        })
        content = result["content"][0]["text"]
        import ast
        stress_results = ast.literal_eval(content)
        return stress_results

    async def cleanup(self):
        """Clean up all connections"""
        logger.info("Shutting down...")
        
        # Close all clients concurrently
        close_tasks = []
        if self.news_client:
            close_tasks.append(self.news_client.close())
        if self.risk_client:
            close_tasks.append(self.risk_client.close())
        if self.market_client:
            close_tasks.append(self.market_client.close())
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # Give event loop time to clean up
        await asyncio.sleep(0.1)


async def main():
    """Example usage demonstrating market data tools"""
    coordinator = FinsenseCoordinator()
    
    try:
        await coordinator.initialize()
        
        # Get market indices
        print("\n" + "="*60)
        print("Fetching Major Market Indices...")
        print("="*60)
        indices = await coordinator.get_market_indices()
        for index_name, data in indices.items():
            print(f"{index_name}: {data['value']} ({data['change']})")
        
        # Get stock prices for multiple tickers
        print("\n" + "="*60)
        print("Fetching Individual Stock Prices...")
        print("="*60)
        tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
        for ticker in tickers:
            stock_data = await coordinator.get_stock_price(ticker)
            print(f"\n{stock_data['ticker']}:")
            print(f"  Price: ${stock_data['price']}")
            print(f"  Change: {stock_data['change']} ({stock_data['change_percent']})")
            print(f"  Volume: {stock_data['volume']}")
            print(f"  Market Cap: ${stock_data['market_cap']}")
            print(f"  P/E Ratio: {stock_data['pe_ratio']}")
        
        # Get sector summaries
        print("\n" + "="*60)
        print("Fetching Sector Summaries...")
        print("="*60)
        sectors = ["technology", "healthcare", "financial-services"]
        for sector in sectors:
            summary = await coordinator.get_sector_summary(sector)
            print(f"\n{summary['sector']} Sector:")
            print(f"  1-Day Performance: {summary['performance_1d']}")
            print(f"  1-Week Performance: {summary['performance_1w']}")
            print(f"  1-Month Performance: {summary['performance_1m']}")
            print(f"  Market Weight: {summary.get('market_weight', 'N/A')}")
            print(f"  Top Performers:")
            for performer in summary.get('top_performers', [])[:3]:
                print(f"       - {performer['ticker']}")
        
        print("\n" + "="*60)
        print("✓ Market analysis complete")
        print("="*60 + "\n")
        
    except Exception as e:
        logger.exception("Error: %s", e)
    finally:
        await coordinator.cleanup()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())