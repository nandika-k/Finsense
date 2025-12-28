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
        '''
        testing finsense_market.py

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
        '''

        '''
        testing finsense_risk.py
        
        # Test sector volatility calculations
        print("\n" + "="*60)
        print("Computing Sector Volatility...")
        print("="*60)
        test_sectors = ["technology", "healthcare", "energy"]
        for sector in test_sectors:
            try:
                volatility = await coordinator.compute_sector_volatility(sector, "1y")
                print(f"\n{sector.upper()} Sector Volatility (1 year):")
                print(f"  Ticker: {volatility.get('ticker', 'N/A')}")
                print(f"  Annualized Volatility: {volatility.get('annualized_volatility', 'N/A')}")
                print(f"  Realized Volatility: {volatility.get('realized_volatility', 'N/A')}")
                print(f"  Rolling 30d Volatility: {volatility.get('rolling_30d_volatility', 'N/A')}")
                print(f"  Historical Average: {volatility.get('historical_average', 'N/A')}")
                print(f"  Max Drawdown: {volatility.get('max_drawdown', 'N/A')}")
                print(f"  Trend: {volatility.get('trend', 'N/A')}")
                print(f"  Percentile: {volatility.get('percentile', 'N/A')}")
                if 'market_volatility' in volatility:
                    print(f"  Market Volatility (SPY): {volatility.get('market_volatility', 'N/A')}")
                    print(f"  Relative to Market: {volatility.get('relative_to_market', 'N/A')}")
            except Exception as e:
                print(f"\nError computing volatility for {sector}: {e}")
        
        # Test sector comparison
        print("\n" + "="*60)
        print("Comparing Sectors...")
        print("="*60)
        try:
            comparison = await coordinator.compare_sectors("technology", "healthcare", "1y")
            print(f"\n{comparison.get('sector1', '').upper()} vs {comparison.get('sector2', '').upper()}:")
            print(f"  Timeframe: {comparison.get('timeframe', 'N/A')}")
            
            vol_comp = comparison.get('volatility_comparison', {})
            print(f"\n  Volatility:")
            print(f"    {comparison.get('sector1', '')}: {vol_comp.get(comparison.get('sector1', ''), 'N/A')}")
            print(f"    {comparison.get('sector2', '')}: {vol_comp.get(comparison.get('sector2', ''), 'N/A')}")
            print(f"    Difference: {vol_comp.get('difference', 'N/A')}")
            print(f"    Lower volatility: {vol_comp.get('lower_volatility', 'N/A')}")
            
            drawdown = comparison.get('max_drawdown', {})
            print(f"\n  Max Drawdown:")
            print(f"    {comparison.get('sector1', '')}: {drawdown.get(comparison.get('sector1', ''), 'N/A')}")
            print(f"    {comparison.get('sector2', '')}: {drawdown.get(comparison.get('sector2', ''), 'N/A')}")
            print(f"    Lower drawdown: {drawdown.get('lower_drawdown', 'N/A')}")
            
            returns = comparison.get('total_return', {})
            print(f"\n  Total Return:")
            print(f"    {comparison.get('sector1', '')}: {returns.get(comparison.get('sector1', ''), 'N/A')}")
            print(f"    {comparison.get('sector2', '')}: {returns.get(comparison.get('sector2', ''), 'N/A')}")
            print(f"    Higher return: {returns.get('higher_return', 'N/A')}")
            
            sharpe = comparison.get('sharpe_ratio', {})
            print(f"\n  Sharpe Ratio (Risk-Adjusted):")
            print(f"    {comparison.get('sector1', '')}: {sharpe.get(comparison.get('sector1', ''), 'N/A')}")
            print(f"    {comparison.get('sector2', '')}: {sharpe.get(comparison.get('sector2', ''), 'N/A')}")
            print(f"    Higher Sharpe: {sharpe.get('higher_sharpe', 'N/A')}")
            
            beta = comparison.get('beta', {})
            print(f"\n  Beta (Market Sensitivity):")
            print(f"    {comparison.get('sector1', '')}: {beta.get(comparison.get('sector1', ''), 'N/A')}")
            print(f"    {comparison.get('sector2', '')}: {beta.get(comparison.get('sector2', ''), 'N/A')}")
            
            print(f"\n  Recommendation: {comparison.get('recommendation', 'N/A')}")
        except Exception as e:
            print(f"\nError comparing sectors: {e}")
        
        # Test sector correlations
        print("\n" + "="*60)
        print("Computing Sector Correlations...")
        print("="*60)
        try:
            test_sectors = ["technology", "healthcare", "energy", "financial-services"]
            correlations = await coordinator.compute_sector_correlations(test_sectors, "1y")
            
            print(f"\nSector Correlation Analysis ({correlations.get('timeframe', 'N/A')}):")
            print(f"  Sectors analyzed: {', '.join(correlations.get('sectors_analyzed', []))}")
            print(f"  Data points: {correlations.get('data_points', 'N/A')}")
            print(f"  Average correlation: {correlations.get('average_correlation', 'N/A')}")
            
            print(f"\n  Diversification Score: {correlations.get('diversification_score', 'N/A')}")
            print(f"  {correlations.get('diversification_interpretation', 'N/A')}")
            
            highest = correlations.get('highest_correlation', {})
            print(f"\n  Highest Correlation:")
            print(f"    {highest.get('pair', 'N/A')}")
            print(f"    {highest.get('interpretation', 'N/A')}")
            
            lowest = correlations.get('lowest_correlation', {})
            print(f"\n  Lowest Correlation (Best Diversification):")
            print(f"    {lowest.get('pair', 'N/A')}")
            print(f"    {lowest.get('interpretation', 'N/A')}")
            
            insights = correlations.get('insights', {})
            print(f"\n  Sectors Moving Together (correlation > 0.6):")
            moving_together = insights.get('sectors_moving_together', [])
            if moving_together and moving_together[0] != "None identified (all correlations < 0.6)":
                for pair in moving_together:
                    print(f"    - {pair}")
            else:
                print(f"    - {moving_together[0] if moving_together else 'None identified'}")
                print(f"    (Note: Check correlation matrix below for actual values)")
            
            print(f"\n  Best Diversification Opportunities (correlation < 0.4):")
            diversification = insights.get('best_diversification_opportunities', [])
            if diversification and diversification[0] != "None identified (all correlations > 0.4)":
                for pair in diversification:
                    print(f"    - {pair}")
            else:
                print(f"    - {diversification[0] if diversification else 'None identified'}")
                print(f"    (Note: Check correlation matrix below for actual values)")
            
            print(f"\n  Correlation Matrix:")
            corr_matrix = correlations.get('correlation_matrix', {})
            for pair, value in list(corr_matrix.items())[:6]:  # Show first 6 pairs
                print(f"    {pair}: {value:.3f}")
            if len(corr_matrix) > 6:
                print(f"    ... and {len(corr_matrix) - 6} more pairs")
                
        except Exception as e:
            print(f"\nError computing sector correlations: {e}")
        
        # Test VaR calculation
        print("\n" + "="*60)
        print("Calculating Value at Risk (VaR)...")
        print("="*60)
        try:
            # Test portfolio with sector allocations
            test_portfolio = {
                "technology": 0.4,
                "healthcare": 0.3,
                "energy": 0.3
            }
            portfolio_value = 1000000  # $1M portfolio
            
            var_result = await coordinator.calculate_var(
                test_portfolio, 
                confidence_level=0.95, 
                timeframe="1y",
                portfolio_value=portfolio_value
            )
            
            print(f"\nPortfolio VaR Analysis:")
            print(f"  Confidence Level: {var_result.get('confidence_level', 'N/A')}")
            print(f"  Method: {var_result.get('method', 'N/A')}")
            print(f"  Data Points: {var_result.get('data_points', 'N/A')}")
            
            print(f"\n  Portfolio Holdings:")
            holdings = var_result.get('portfolio_holdings', {})
            for holding, info in holdings.items():
                print(f"    {holding}: {info.get('weight', 'N/A')} ({info.get('ticker', 'N/A')})")
            
            var_pct = var_result.get('var_percentage', {})
            print(f"\n  VaR (Percentage):")
            print(f"    1 Day: {var_pct.get('1_day', 'N/A')}")
            print(f"    1 Week: {var_pct.get('1_week', 'N/A')}")
            print(f"    1 Month: {var_pct.get('1_month', 'N/A')}")
            
            if 'var_absolute' in var_result:
                var_abs = var_result.get('var_absolute', {})
                print(f"\n  VaR (Absolute - ${portfolio_value:,} portfolio):")
                print(f"    1 Day: {var_abs.get('1_day', 'N/A')}")
                print(f"    1 Week: {var_abs.get('1_week', 'N/A')}")
                print(f"    1 Month: {var_abs.get('1_month', 'N/A')}")
            
            stats = var_result.get('portfolio_statistics', {})
            print(f"\n  Portfolio Statistics:")
            print(f"    Mean Daily Return: {stats.get('mean_daily_return', 'N/A')}")
            print(f"    Volatility: {stats.get('volatility', 'N/A')}")
            print(f"    Worst Day: {stats.get('worst_day', 'N/A')}")
            print(f"    Best Day: {stats.get('best_day', 'N/A')}")
            
            print(f"\n  Expected Shortfall (Conditional VaR): {var_result.get('expected_shortfall', 'N/A')}")
            print(f"\n  Interpretation: {var_result.get('interpretation', 'N/A')}")
            
        except Exception as e:
            print(f"\nError calculating VaR: {e}")
        
        print("\n" + "="*60)
        print("✓ Market analysis complete")
        print("="*60 + "\n")
        '''
        
        # Test news tools
        print("\n" + "="*60)
        print("Testing News Tools...")
        print("="*60)
        
        # Test fetch_headlines
        print("\n" + "="*60)
        print("Fetching Headlines...")
        print("="*60)
        try:
            headlines_data = await coordinator.fetch_headlines("technology", "1w")
            print(f"\nSector: {headlines_data.get('sector', 'N/A')}")
            print(f"Timeframe: {headlines_data.get('timeframe', 'N/A')}")
            print(f"Headlines Found: {headlines_data.get('headline_count', 0)}")
            
            headlines = headlines_data.get('headlines', [])
            if headlines:
                print(f"\nSample Headlines:")
                for i, headline in enumerate(headlines[:5], 1):
                    print(f"\n  {i}. {headline.get('title', 'N/A')}")
                    print(f"     Source: {headline.get('source', 'N/A')}")
                    if headline.get('date'):
                        print(f"     Date: {headline.get('date', 'N/A')}")
            else:
                print("\n  No headlines found (this is normal if RSS feeds are unavailable)")
        except Exception as e:
            print(f"\nError fetching headlines: {e}")
        
        # Test extract_risk_themes (RAG-style: fetches real articles and extracts risks)
        print("\n" + "="*60)
        print("Extracting Risk Themes from Real Articles (RAG-style)...")
        print("="*60)
        try:
            # Tool now fetches real articles internally and extracts risks
            themes_data = await coordinator.extract_risk_themes("technology", "1w")
            
            print(f"\nRAG-Style Risk Extraction Results:")
            print(f"  Sector: {themes_data.get('sector', 'N/A')}")
            print(f"  Timeframe: {themes_data.get('timeframe', 'N/A')}")
            print(f"  Articles Fetched: {themes_data.get('articles_fetched', 0)}")
            print(f"  Total Risks Identified: {themes_data.get('total_risks_identified', 0)}")
            print(f"  Total Articles Analyzed: {themes_data.get('total_articles_analyzed', 0)}")
            print(f"  Summary: {themes_data.get('summary', 'N/A')}")
            
            risk_categories = themes_data.get('risk_categories', {})
            if risk_categories:
                print(f"\n  Risk Categories Summary:")
                for category, info in risk_categories.items():
                    print(f"    {category}: {info.get('risk_count', 0)} risks, {info.get('article_count', 0)} article mentions")
            
            identified_risks = themes_data.get('identified_risks', [])
            if identified_risks:
                print(f"\n  Specific Risks with Real Article Citations:")
                for i, risk_item in enumerate(identified_risks[:5], 1):
                    print(f"\n    {i}. Risk: {risk_item.get('risk', 'N/A')}")
                    print(f"       Category: {risk_item.get('category', 'N/A')}")
                    print(f"       Mentioned in {risk_item.get('article_count', 0)} article(s):")
                    
                    articles = risk_item.get('articles', [])
                    for j, article in enumerate(articles[:3], 1):
                        print(f"\n         Article {j}:")
                        print(f"           Title: {article.get('title', 'N/A')}")
                        if article.get('url'):
                            print(f"           URL: {article.get('url', 'N/A')}")
                        if article.get('date'):
                            print(f"           Date: {article.get('date', 'N/A')}")
                        if article.get('source'):
                            print(f"           Source: {article.get('source', 'N/A')}")
                        print(f"           Relevance: {article.get('relevance', 'N/A')}")
            else:
                print("\n  No risks identified (may indicate no relevant articles found or no risk matches)")
        except Exception as e:
            print(f"\nError extracting risk themes: {e}")
        
        # Test identify_sector_risks
        print("\n" + "="*60)
        print("Identifying Sector Risks...")
        print("="*60)
        try:
            risks_data = await coordinator.identify_sector_risks("consumer-discretionary")
            
            print(f"\nSector: {risks_data.get('sector', 'N/A')}")
            print(f"Risk Type: {risks_data.get('risk_type', 'N/A')}")
            print(f"Description: {risks_data.get('description', 'N/A')}")
            print(f"Total Risk Count: {risks_data.get('total_risk_count', 0)}")
            print(f"Summary: {risks_data.get('summary', 'N/A')}")
            
            risk_categories = risks_data.get('risk_categories', [])
            if risk_categories:
                print(f"\n  Risk Categories:")
                for category_info in risk_categories[:3]:
                    category = category_info.get('category', 'N/A')
                    count = category_info.get('count', 0)
                    print(f"\n    {category} ({count} risks):")
                    risks = category_info.get('risks', [])
                    for risk in risks[:2]:
                        print(f"      - {risk}")
        except Exception as e:
            print(f"\nError identifying sector risks: {e}")
        
        print("\n" + "="*60)
        print("✓ News tools test complete")
        print("="*60 + "\n")
    except Exception as e:
        logger.exception("Error: %s", e)
    finally:
        await coordinator.cleanup()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())