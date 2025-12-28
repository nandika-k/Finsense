import asyncio
import json
import sys
from pathlib import Path
import logging
import subprocess
from typing import Dict, Any, List
import warnings

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
        self.stderr_task = None

    async def start(self):
        """Start the MCP server process"""
        logger.info("Starting MCP server: %s", self.server_path.name)
        
        if not self.server_path.exists():
            raise FileNotFoundError(f"Server file not found: {self.server_path}")
        
        env = {**subprocess.os.environ, "PYTHONUNBUFFERED": "1"}
        
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            str(self.server_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        logger.info("Server started with PID: %s", self.process.pid)
        
        # Start reading stderr in background
        self.stderr_task = asyncio.create_task(self._read_stderr())
        
        await asyncio.sleep(0.1)
        await self._initialize()
    
    async def _read_stderr(self):
        """Read and display stderr from server process"""
        try:
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    break
                stderr_msg = line.decode('utf-8').strip()
                if stderr_msg:
                    # Print server logs with a prefix
                    print(f"[SERVER] {stderr_msg}", file=sys.stderr)
        except Exception as e:
            logger.debug(f"stderr reader stopped: {e}")
        
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
        
        max_attempts = 10
        for attempt in range(max_attempts):
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=30.0  # Increased timeout for slow RSS feeds
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
        
        await self._send_notification("notifications/initialized")
        self.initialized = True
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        result = await self._send_request("tools/list")
        return result.get("tools", [])
    
    async def call_tool(self, name: str, arguments: dict) -> Dict[str, Any]:
        """Call a tool"""
        logger.info("Calling tool: %s with args: %s", name, arguments)
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        return result
    
    async def close(self):
        """Close the connection gracefully"""
        if self.stderr_task:
            self.stderr_task.cancel()
            try:
                await self.stderr_task
            except asyncio.CancelledError:
                pass
        
        if self.process and self.process.returncode is None:
            try:
                if self.process.stdin and not self.process.stdin.is_closing():
                    self.process.stdin.close()
                    await asyncio.sleep(0.1)
                
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    self.process.terminate()
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        self.process.kill()
                        await self.process.wait()
                
                logger.info("Server stopped")
            except Exception as e:
                logger.debug("Error during cleanup: %s", e)


class FinsenseCoordinator:
    """Coordinates multiple MCP servers for financial analysis"""
    
    def __init__(self):
        self.news_client: MCPClient | None = None

    async def initialize(self):
        """Initialize news server connection"""
        logger.info("Initializing Finsense Coordinator (News Module)...")
        
        news_server_path = BASE_DIR / "mcp_news" / "finsense_news.py"
        self.news_client = MCPClient(news_server_path)
        await self.news_client.start()
        
        news_tools = await self.news_client.list_tools()
        logger.info("News tools available: %s", [t["name"] for t in news_tools])

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
        """Extract risk themes from real news articles"""
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

    async def cleanup(self):
        """Clean up connections"""
        logger.info("Shutting down...")
        if self.news_client:
            await self.news_client.close()
        await asyncio.sleep(0.1)


async def main():
    """Test news fetching with detailed diagnostics"""
    coordinator = FinsenseCoordinator()
    
    try:
        print("\n" + "="*80)
        print("FINSENSE NEWS MODULE TEST - DETAILED DIAGNOSTICS")
        print("="*80)
        print("\nInitializing MCP server...")
        print("(Server logs will appear with [SERVER] prefix below)")
        print("-"*80 + "\n")
        
        await coordinator.initialize()
        
        # Test 1: Fetch Headlines
        print("\n" + "="*80)
        print("TEST 1: Fetching Headlines for Technology Sector (1 week)")
        print("="*80)
        print("\nThis will fetch from multiple RSS feeds and may take 10-20 seconds...")
        print("Watch [SERVER] logs below for feed-by-feed progress.\n")
        
        try:
            headlines_data = await coordinator.fetch_headlines("technology", "1w")
            
            print("\n" + "-"*80)
            print("RESULTS:")
            print("-"*80)
            print(f"✓ Fetch completed successfully")
            print(f"  Sector: {headlines_data.get('sector', 'N/A')}")
            print(f"  Timeframe: {headlines_data.get('timeframe', 'N/A')}")
            print(f"  Headlines Found: {headlines_data.get('headline_count', 0)}")
            
            if 'message' in headlines_data:
                print(f"\n  ⚠ Message: {headlines_data['message']}")
            
            headlines = headlines_data.get('headlines', [])
            if headlines:
                print(f"\n  Sample Headlines (first 5 of {len(headlines)}):")
                for i, headline in enumerate(headlines[:5], 1):
                    print(f"\n    [{i}] {headline.get('title', 'N/A')}")
                    print(f"        Source: {headline.get('source', 'N/A')}")
                    print(f"        Date: {headline.get('date', 'N/A')[:50]}")
                    if headline.get('description'):
                        desc = headline.get('description', '')[:100]
                        print(f"        Preview: {desc}...")
            else:
                print("\n  ✗ FAILURE: No headlines retrieved!")
                print("\n  Possible causes:")
                print("    • RSS feeds are blocked by your network/firewall")
                print("    • RSS feed URLs have changed")
                print("    • Network connectivity issues")
                print("    • BeautifulSoup not installed (pip install beautifulsoup4)")
                print("\n  Check [SERVER] logs above for specific error messages.")
                
        except Exception as e:
            print(f"\n✗ ERROR in fetch_headlines: {e}")
            import traceback
            traceback.print_exc()
        
        # Test 2: Extract Risk Themes
        print("\n\n" + "="*80)
        print("TEST 2: Extracting Risk Themes from Articles (RAG-style)")
        print("="*80)
        print("\nThis fetches articles internally and extracts risk themes...")
        print("Watch [SERVER] logs for article-by-article analysis.\n")
        
        try:
            themes_data = await coordinator.extract_risk_themes("technology", "1w")
            
            print("\n" + "-"*80)
            print("RESULTS:")
            print("-"*80)
            print(f"✓ Risk extraction completed")
            print(f"  Sector: {themes_data.get('sector', 'N/A')}")
            print(f"  Timeframe: {themes_data.get('timeframe', 'N/A')}")
            print(f"  Articles Fetched: {themes_data.get('articles_fetched', 0)}")
            print(f"  Risks Identified: {themes_data.get('total_risks_identified', 0)}")
            
            if 'message' in themes_data:
                print(f"\n  ⚠ Message: {themes_data['message']}")
            
            risk_categories = themes_data.get('risk_categories', {})
            if risk_categories:
                print(f"\n  Risk Category Summary:")
                for category, info in sorted(risk_categories.items(), 
                                            key=lambda x: x[1].get('article_count', 0), 
                                            reverse=True):
                    print(f"    • {category}: {info.get('risk_count', 0)} risks in {info.get('article_count', 0)} articles")
            
            identified_risks = themes_data.get('identified_risks', [])
            if identified_risks:
                print(f"\n  Top {min(3, len(identified_risks))} Risks with Article Citations:")
                for i, risk_item in enumerate(identified_risks[:3], 1):
                    print(f"\n    [{i}] {risk_item.get('risk', 'N/A')}")
                    print(f"        Category: {risk_item.get('category', 'N/A')}")
                    print(f"        Mentioned in {risk_item.get('article_count', 0)} article(s)")
                    
                    articles = risk_item.get('articles', [])
                    if articles:
                        print(f"        Top citing article:")
                        article = articles[0]
                        print(f"          Title: {article.get('title', 'N/A')[:70]}...")
                        print(f"          Source: {article.get('source', 'N/A')}")
                        print(f"          Relevance: {article.get('relevance', 'N/A')}")
                        if 'matched_keywords' in article:
                            kw = article.get('matched_keywords', [])[:3]
                            print(f"          Keywords: {', '.join(kw)}")
            else:
                print("\n  ✗ FAILURE: No risks identified!")
                print("\n  This means:")
                if themes_data.get('articles_fetched', 0) == 0:
                    print("    • No articles were fetched (see TEST 1 results)")
                else:
                    print(f"    • {themes_data.get('articles_fetched', 0)} articles fetched but none matched risk patterns")
                    print("    • Check [SERVER] logs to see which articles were analyzed")
                    print("    • Risk keywords may need further adjustment")
                
        except Exception as e:
            print(f"\n✗ ERROR in extract_risk_themes: {e}")
            import traceback
            traceback.print_exc()
        
        # Test 3: Identify Sector Risks (Knowledge Base)
        print("\n\n" + "="*80)
        print("TEST 3: Identifying Structural Risks from Knowledge Base")
        print("="*80)
        print("\nThis uses the built-in sector risk database (no network calls).\n")
        
        try:
            risks_data = await coordinator.identify_sector_risks("technology")
            
            print("-"*80)
            print("RESULTS:")
            print("-"*80)
            print(f"✓ Sector risk identification completed")
            print(f"  Sector: {risks_data.get('sector', 'N/A')}")
            print(f"  Risk Type: {risks_data.get('risk_type', 'N/A')}")
            print(f"  Total Structural Risks: {risks_data.get('total_risk_count', 0)}")
            
            risk_categories = risks_data.get('risk_categories', [])
            if risk_categories:
                print(f"\n  Risk Categories (showing first 3):")
                for category_info in risk_categories[:3]:
                    category = category_info.get('category', 'N/A')
                    count = category_info.get('count', 0)
                    print(f"\n    {category} ({count} risks):")
                    risks = category_info.get('risks', [])
                    for risk in risks[:3]:
                        print(f"      • {risk}")
                    if len(risks) > 3:
                        print(f"      ... and {len(risks) - 3} more")
                        
        except Exception as e:
            print(f"\n✗ ERROR in identify_sector_risks: {e}")
            import traceback
            traceback.print_exc()
        
        # Final Summary
        print("\n\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        test1_pass = headlines_data.get('headline_count', 0) > 0 if 'headlines_data' in locals() else False
        test2_pass = themes_data.get('total_risks_identified', 0) > 0 if 'themes_data' in locals() else False
        test3_pass = risks_data.get('total_risk_count', 0) > 0 if 'risks_data' in locals() else False
        
        print(f"\n  Test 1 (Fetch Headlines): {'✓ PASS' if test1_pass else '✗ FAIL'}")
        print(f"  Test 2 (Extract Risks):   {'✓ PASS' if test2_pass else '✗ FAIL'}")
        print(f"  Test 3 (Knowledge Base):  {'✓ PASS' if test3_pass else '✗ FAIL'}")
        
        if test1_pass and test2_pass and test3_pass:
            print(f"\n  🎉 ALL TESTS PASSED! The news module is working correctly.")
        elif test1_pass and test3_pass and not test2_pass:
            print(f"\n  ⚠ Partial success: Headlines fetch works, but risk extraction needs tuning.")
        elif not test1_pass:
            print(f"\n  ✗ Critical issue: Cannot fetch headlines from RSS feeds.")
            print(f"     This is likely a network/connectivity issue.")
        
        print("\n" + "="*80)
        print("DIAGNOSTIC TIPS:")
        print("="*80)
        print("""
  If Test 1 fails:
    • Check network connectivity and firewall settings
    • Try accessing RSS feed URLs directly in your browser
    • Verify beautifulsoup4 is installed: pip install beautifulsoup4
    
  If Test 2 fails but Test 1 passes:
    • Review [SERVER] logs to see which keywords matched
    • Articles may be fetched but not matching risk patterns
    • This is less critical - knowledge base (Test 3) provides baseline risks
    
  If Test 3 fails:
    • This indicates a code issue with the knowledge base structure
    • This test should always pass
        """)
        print("="*80 + "\n")
        
    except Exception as e:
        logger.exception("Fatal error: %s", e)
    finally:
        await coordinator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())