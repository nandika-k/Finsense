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
    async def fetch_headlines(self, sector: str, timeframe: str) -> Dict[str, Any]:
        """Fetch news headlines for a sector"""
        result = await self.news_client.call_tool("fetch_headlines", {
            "sector": sector,
            "timeframe": timeframe
        })
        
        content = result["content"][0]["text"]
        headlines_data = json.loads(content)
        return headlines_data
    
    async def extract_risk_themes(self, sector: str, timeframe: str) -> Dict[str, Any]:
        """Extract risk themes from real news articles (RAG-style: fetches articles and extracts risks with citations)"""
        result = await self.news_client.call_tool("extract_risk_themes", {
            "sector": sector,
            "timeframe": timeframe
        })
        
        content = result["content"][0]["text"]
        themes_data = json.loads(content)
        return themes_data
    
    async def identify_sector_risks(self, sector_or_ticker: str) -> Dict[str, Any]:
        """Identify structural/inherent risks for a sector or stock"""
        result = await self.news_client.call_tool("identify_sector_risks", {
            "sector_or_ticker": sector_or_ticker
        })
        content = result["content"][0]["text"]
        risks_data = json.loads(content)
        return risks_data

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
        volatility = json.loads(content)
        return volatility

    async def compare_sectors(self, sector1: str, sector2: str, timeframe: str) -> Dict[str, Any]:
        """Compare risk metrics between two sectors"""
        result = await self.risk_client.call_tool("compare_sectors", {
            "sector1": sector1,
            "sector2": sector2,
            "timeframe": timeframe
        })
        content = result["content"][0]["text"]
        comparison = json.loads(content)
        return comparison

    async def compute_sector_correlations(self, sectors: List[str], timeframe: str) -> Dict[str, Any]:
        """Compute correlations between sectors"""
        result = await self.risk_client.call_tool("compute_sector_correlations", {
            "sectors": sectors,
            "timeframe": timeframe
        })
        content = result["content"][0]["text"]
        correlations = json.loads(content)
        return correlations

    async def calculate_var(self, portfolio: Dict[str, Any], confidence_level: float, timeframe: str, portfolio_value: float = None) -> Dict[str, Any]:
        """Calculate Value at Risk (VaR) for a portfolio"""
        params = {
            "portfolio": portfolio,
            "confidence_level": confidence_level,
            "timeframe": timeframe
        }
        if portfolio_value:
            params["portfolio_value"] = portfolio_value
        
        result = await self.risk_client.call_tool("calculate_var", params)
        content = result["content"][0]["text"]
        var_data = json.loads(content)
        return var_data

    async def conduct_research(self, sectors: List[str], risk_tolerance: str = "medium") -> Dict[str, Any]:
        """
        Coordinates the research process by aggregating data from all MCP servers.
        
        Flow:
        1. Fetch broad market context (Market Server)
        2. For each sector:
           - Get performance summary (Market Server)
           - Analyze volatility and risk metrics (Risk Server)
           - Extract risk themes from news (News Server)
        3. Analyze cross-sector correlations (Risk Server)
        """
        logger.info("Beginning coordinated research on sectors: %s", sectors)
        
        research_data = {
            "parameters": {
                "sectors": sectors,
                "risk_tolerance": risk_tolerance
            },
            "market_context": {},
            "sector_deep_dives": {},
            "portfolio_implications": {}
        }

        # 1. Broad Market Context
        try:
            research_data["market_context"] = await self.get_market_indices()
        except Exception as e:
            logger.error("Failed to fetch market indices: %s", e)
            research_data["market_context"] = {"error": str(e)}

        # 2. Deep Dive per Sector
        for sector in sectors:
            logger.info("Analyzing sector: %s", sector)
            
            # Run independent analysis tasks in parallel across different servers
            tasks = [
                self.get_sector_summary(sector),
                self.compute_sector_volatility(sector, "1y"),
                self.extract_risk_themes(sector, "1m")
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            sector_data = {
                "market_performance": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
                "risk_profile": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
                "news_analysis": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])}
            }
            
            research_data["sector_deep_dives"][sector] = sector_data

        # 3. Cross-Sector Analysis
        if len(sectors) > 1:
            try:
                correlations = await self.compute_sector_correlations(sectors, "1y")
                research_data["portfolio_implications"]["correlations"] = correlations
            except Exception as e:
                logger.error("Failed to compute correlations: %s", e)

        return research_data

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
    """
    Main entry point for the Finsense Agent.
    Simulates a user interaction session.
    """
    coordinator = FinsenseCoordinator()
    
    try:
        await coordinator.initialize()
        
        # Example User Scenario:
        # "A user with low-risk tolerance wants to invest in an environmentally conscious manner."
        
        print("\n" + "="*80)
        print("FINSENSE AGENT - RESEARCH SESSION")
        print("="*80)
        print("User Profile: Low Risk Tolerance")
        print("Interests: Environmentally Conscious Investing")
        print("-" * 80)
        
        # Analyze all major sectors to find best matches for user tolerance
        target_sectors = [
            "technology", "healthcare", "financial-services", "energy", 
            "consumer-discretionary", "consumer-staples", "utilities", 
            "real-estate", "industrials", "materials", "communication-services"
        ]
        
        print(f"Identified Target Sectors: {', '.join(target_sectors)}")
        print("Starting coordinated analysis...")
        
        research_results = await coordinator.conduct_research(target_sectors, risk_tolerance="low")
        
        # Display Results
        print("\n" + "="*80)
        print("RESEARCH FINDINGS")
        print("="*80)
        
        # Market Context
        indices = research_results.get("market_context", {})
        print(f"\n[Market Context]")
        for name, data in indices.items():
            if isinstance(data, dict):
                print(f"  {name}: {data.get('value')} ({data.get('change')})")
        
        # Sector Findings
        print(f"\n[Sector Analysis]")
        for sector, data in research_results.get("sector_deep_dives", {}).items():
            print(f"\n>> {sector.upper()}")
            
            # Performance
            perf = data.get("market_performance", {})
            print(f"  Performance (1M): {perf.get('performance_1m', 'N/A')}")
            
            # Risk
            risk = data.get("risk_profile", {})
            vol = risk.get("annualized_volatility", "N/A")
            print(f"  Volatility (1Y): {vol}")
            
            # News/Themes
            news = data.get("news_analysis", {})
            risks = news.get("identified_risks", [])
            print(f"  Key Risks Identified: {len(risks)}")
            for r in risks[:2]: # Show top 2
                print(f"    - {r.get('risk', 'N/A')} ({r.get('category', 'N/A')})")
                
        # Suggestions based on User Profile
        print("\n" + "="*80)
        print("SUGGESTED RESEARCH PATH")
        print("="*80)
        
        # Filter for Low Risk (Low Volatility)
        sector_metrics = []
        for sector, data in research_results.get("sector_deep_dives", {}).items():
            risk_profile = data.get("risk_profile", {})
            vol_raw = risk_profile.get("annualized_volatility", "N/A")
            
            # Simple parsing for sorting (assuming string "XX.X%" or float)
            try:
                if isinstance(vol_raw, str) and "%" in vol_raw:
                    vol_val = float(vol_raw.strip("%"))
                else:
                    vol_val = float(vol_raw)
            except (ValueError, TypeError):
                vol_val = 100.0  # High default if unknown
                
            sector_metrics.append((sector, vol_val, vol_raw))
            
        # Sort by volatility ascending
        sector_metrics.sort(key=lambda x: x[1])
        
        print("Based on your 'Low Risk' tolerance, consider researching these stable sectors first:")
        for sector, val, display in sector_metrics[:4]:
            print(f"  • {sector.upper()} (Volatility: {display})")
            
        print("\nRegarding 'Environmentally Conscious' preference:")
        print("  • Cross-reference the low-volatility sectors above with ESG ratings.")
        print("  • Note: Sectors like Utilities may have mixed environmental impacts depending on the specific companies.")

        # Correlations
        print(f"\n[Portfolio Implications]")
        correlations = research_results.get("portfolio_implications", {}).get("correlations", {})
        if correlations:
            print(f"  Diversification Score: {correlations.get('diversification_score', 'N/A')}")
            insights = correlations.get("insights", {}).get("best_diversification_opportunities", [])
            if insights:
                print(f"  Diversification Opportunities: {', '.join(insights)}")

        print("\n" + "="*80)
        print("Analysis Complete.")
        print("="*80)

    except Exception as e:
        logger.exception("Error: %s", e)
    finally:
        await coordinator.cleanup()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())