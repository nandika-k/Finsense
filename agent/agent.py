import asyncio
import json
import sys
from pathlib import Path
import logging
import subprocess
from typing import Dict, Any, List

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
        """Close the connection"""
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            logger.info("Server stopped")


class FinsenseCoordinator:
    """Coordinates multiple MCP servers for financial analysis"""
    
    def __init__(self):
        self.news_client: MCPClient | None = None

    async def initialize(self):
        """Initialize all MCP server connections"""
        logger.info("Initializing Finsense Coordinator...")
        
        # Connect to news server
        news_server_path = BASE_DIR / "mcp_news" / "finsense_news.py"
        self.news_client = MCPClient(news_server_path)
        await self.news_client.start()
        
        # List available tools
        tools = await self.news_client.list_tools()
        logger.info("Available tools: %s", [t["name"] for t in tools])
        
        logger.info("✓ Coordinator initialized")

    async def fetch_headlines(self, sector: str, timeframe: str) -> List[str]:
        """Fetch news headlines for a sector"""
        result = await self.news_client.call_tool("fetch_headlines", {
            "sector": sector,
            "timeframe": timeframe
        })
        
        # Parse the result
        content = result["content"][0]["text"]
        # The result is a string representation of a list, so evaluate it
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

    async def cleanup(self):
        """Clean up all connections"""
        logger.info("Shutting down...")
        if self.news_client:
            await self.news_client.close()


async def main():
    """Example usage"""
    coordinator = FinsenseCoordinator()
    
    try:
        await coordinator.initialize()
        
        # Fetch headlines
        print("\n" + "="*60)
        print("Fetching technology sector headlines...")
        print("="*60)
        headlines = await coordinator.fetch_headlines("technology", "7d")
        for i, headline in enumerate(headlines, 1):
            print(f"{i}. {headline}")
        
        # Extract risk themes
        print("\n" + "="*60)
        print("Extracting risk themes...")
        print("="*60)
        themes = await coordinator.extract_risk_themes(headlines)
        for i, theme in enumerate(themes, 1):
            print(f"{i}. {theme}")
        
        print("\n" + "="*60)
        print("✓ Analysis complete")
        print("="*60 + "\n")
        
    except Exception as e:
        logger.exception("Error: %s", e)
    finally:
        await coordinator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())