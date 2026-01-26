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

    async def get_stock_recommendations(self, sector: str, goal: str) -> Dict[str, Any]:
        """Get stock recommendations for a sector based on investment goal"""
        result = await self.market_client.call_tool("get_stock_recommendations", {
            "sector": sector,
            "goal": goal
        })
        content = result["content"][0]["text"]
        import json
        recommendations = json.loads(content)
        return recommendations

    async def get_stock_details(self, ticker: str) -> Dict[str, Any]:
        """Get detailed information for a specific stock"""
        result = await self.market_client.call_tool("get_stock_details", {
            "ticker": ticker
        })
        content = result["content"][0]["text"]
        import json
        details = json.loads(content)
        return details

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

    async def conduct_research(self, sectors: List[str], risk_tolerance: str = "medium", investment_goals: List[str] = None) -> Dict[str, Any]:
        """
        Coordinates the research process by aggregating data from all MCP servers.
        
        Args:
            sectors: List of sector names to analyze
            risk_tolerance: User's risk tolerance (low/medium/high)
            investment_goals: Optional list of investment goals (growth, income, esg, value, defensive, diversified)
        
        Improvements:
        - Timeout protection (30s per operation)
        - Detailed error categorization
        - Progress tracking
        - Partial success handling
        - Summary statistics
        - Goal-based filtering and recommendations
        
        Flow:
        1. Fetch broad market context (Market Server)
        2. For each sector:
           - Get performance summary (Market Server)
           - Analyze volatility and risk metrics (Risk Server)
           - Extract risk themes from news (News Server)
        3. Analyze cross-sector correlations (Risk Server)
        4. Apply goal-based filtering and ranking
        """
        investment_goals = investment_goals or []
        
        logger.info("="*60)
        logger.info("STARTING COORDINATED RESEARCH")
        logger.info("Sectors: %s | Risk Tolerance: %s", sectors, risk_tolerance)
        if investment_goals:
            logger.info("Investment Goals: %s", ", ".join(investment_goals))
        logger.info("="*60)
        
        # Track statistics
        stats = {
            "total_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "timeouts": 0,
            "errors_by_type": {}
        }
        
        research_data = {
            "parameters": {
                "sectors": sectors,
                "risk_tolerance": risk_tolerance,
                "investment_goals": investment_goals
            },
            "market_context": {},
            "sector_deep_dives": {},
            "portfolio_implications": {},
            "goal_based_recommendations": {},
            "execution_summary": {}
        }

        # 1. Broad Market Context
        logger.info("\n[1/3] Fetching market context...")
        stats["total_operations"] += 1
        try:
            async with asyncio.timeout(30.0):
                research_data["market_context"] = await self.get_market_indices()
                stats["successful_operations"] += 1
                logger.info("✓ Market context retrieved successfully")
        except asyncio.TimeoutError:
            stats["failed_operations"] += 1
            stats["timeouts"] += 1
            error_msg = "Market indices request timed out after 30s"
            logger.error("✗ %s", error_msg)
            research_data["market_context"] = {
                "error": error_msg,
                "error_type": "timeout"
            }
        except Exception as e:
            stats["failed_operations"] += 1
            error_type = type(e).__name__
            stats["errors_by_type"][error_type] = stats["errors_by_type"].get(error_type, 0) + 1
            logger.error("✗ Market context failed: %s: %s", error_type, str(e)[:100])
            research_data["market_context"] = {
                "error": str(e),
                "error_type": error_type
            }

        # 2. Deep Dive per Sector
        logger.info("\n[2/3] Analyzing %d sectors...", len(sectors))
        for idx, sector in enumerate(sectors, 1):
            logger.info("\n  Sector %d/%d: %s", idx, len(sectors), sector.upper())
            
            sector_data = {
                "market_performance": None,
                "risk_profile": None,
                "news_analysis": None,
                "errors": []
            }
            
            # Run independent analysis tasks in parallel with timeout protection
            async def get_market_performance():
                async with asyncio.timeout(30.0):
                    return await self.get_sector_summary(sector)
            
            async def get_risk_profile():
                async with asyncio.timeout(30.0):
                    return await self.compute_sector_volatility(sector, "1y")
            
            async def get_news_analysis():
                async with asyncio.timeout(30.0):
                    return await self.extract_risk_themes(sector, "1m")
            
            tasks = [get_market_performance(), get_risk_profile(), get_news_analysis()]
            task_names = ["market_performance", "risk_profile", "news_analysis"]
            stats["total_operations"] += len(tasks)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results with detailed error handling
            for task_name, result in zip(task_names, results):
                if isinstance(result, asyncio.TimeoutError):
                    stats["failed_operations"] += 1
                    stats["timeouts"] += 1
                    error_msg = f"{task_name} timed out after 30s"
                    sector_data[task_name] = {"error": error_msg, "error_type": "timeout"}
                    sector_data["errors"].append(error_msg)
                    logger.warning("    ✗ %s: timeout", task_name)
                elif isinstance(result, Exception):
                    stats["failed_operations"] += 1
                    error_type = type(result).__name__
                    stats["errors_by_type"][error_type] = stats["errors_by_type"].get(error_type, 0) + 1
                    error_msg = f"{task_name}: {error_type}"
                    sector_data[task_name] = {
                        "error": str(result)[:200],
                        "error_type": error_type
                    }
                    sector_data["errors"].append(error_msg)
                    logger.warning("    ✗ %s: %s", task_name, error_type)
                else:
                    stats["successful_operations"] += 1
                    sector_data[task_name] = result
                    logger.info("    ✓ %s", task_name)
            
            # Calculate success rate for this sector
            sector_success_count = sum(1 for v in [sector_data["market_performance"], 
                                                     sector_data["risk_profile"], 
                                                     sector_data["news_analysis"]] 
                                        if v and "error" not in v)
            logger.info("  → Sector complete: %d/3 operations successful", sector_success_count)
            
            research_data["sector_deep_dives"][sector] = sector_data

        # 3. Cross-Sector Analysis
        if len(sectors) > 1:
            logger.info("\n[3/3] Computing cross-sector correlations...")
            stats["total_operations"] += 1
            try:
                async with asyncio.timeout(30.0):
                    correlations = await self.compute_sector_correlations(sectors, "1y")
                    research_data["portfolio_implications"]["correlations"] = correlations
                    stats["successful_operations"] += 1
                    logger.info("✓ Correlations computed successfully")
            except asyncio.TimeoutError:
                stats["failed_operations"] += 1
                stats["timeouts"] += 1
                logger.error("✗ Correlation analysis timed out after 30s")
                research_data["portfolio_implications"]["correlations"] = {
                    "error": "Correlation analysis timed out",
                    "error_type": "timeout"
                }
            except Exception as e:
                stats["failed_operations"] += 1
                error_type = type(e).__name__
                stats["errors_by_type"][error_type] = stats["errors_by_type"].get(error_type, 0) + 1
                logger.error("✗ Correlation analysis failed: %s: %s", error_type, str(e)[:100])
                research_data["portfolio_implications"]["correlations"] = {
                    "error": str(e),
                    "error_type": error_type
                }
        else:
            logger.info("\n[3/3] Skipping correlations (only 1 sector)")

        # 4. Apply goal-based filtering and recommendations
        if investment_goals:
            logger.info("\n[4/5] Applying goal-based sector filtering...")
            research_data["goal_based_recommendations"] = self._filter_by_goals(
                research_data["sector_deep_dives"],
                investment_goals,
                risk_tolerance
            )
            logger.info("✓ Generated %d goal-aligned sector recommendations", 
                       len(research_data["goal_based_recommendations"].get("ranked_sectors", [])))
            
            # 5. Get stock recommendations for specific goals
            stock_goals = [g for g in investment_goals if g in ["esg", "income", "growth"]]
            if stock_goals:
                logger.info("\n[5/5] Finding stock recommendations for goals: %s", ", ".join(stock_goals))
                top_sector_names = [s["sector"] for s in research_data["goal_based_recommendations"].get("top_picks", [])[:3]]
                try:
                    async with asyncio.timeout(45.0):
                        stock_recs = await self._recommend_stocks_for_goals(stock_goals, top_sector_names)
                        research_data["stock_recommendations"] = stock_recs
                        total_stocks = sum(len(v.get("stocks", [])) for v in stock_recs.values())
                        logger.info("✓ Found %d stock recommendations across %d goals", total_stocks, len(stock_recs))
                except asyncio.TimeoutError:
                    logger.warning("✗ Stock recommendations timed out after 45s")
                    research_data["stock_recommendations"] = {"error": "timeout"}
                except Exception as e:
                    logger.warning("✗ Stock recommendations failed: %s", str(e)[:100])
                    research_data["stock_recommendations"] = {"error": str(e)}
            else:
                logger.info("\n[5/5] Skipping stock recommendations (no applicable goals)")

        # Add execution summary
        success_rate = (stats["successful_operations"] / stats["total_operations"] * 100) if stats["total_operations"] > 0 else 0
        research_data["execution_summary"] = {
            "total_operations": stats["total_operations"],
            "successful": stats["successful_operations"],
            "failed": stats["failed_operations"],
            "timeouts": stats["timeouts"],
            "success_rate": f"{success_rate:.1f}%",
            "errors_by_type": stats["errors_by_type"]
        }
        
        logger.info("\n" + "="*60)
        logger.info("RESEARCH COMPLETE")
        logger.info("Success: %d/%d operations (%.1f%%)", 
                   stats["successful_operations"], 
                   stats["total_operations"],
                   success_rate)
        if stats["timeouts"] > 0:
            logger.warning("Timeouts: %d", stats["timeouts"])
        if stats["errors_by_type"]:
            logger.warning("Errors by type: %s", dict(stats["errors_by_type"]))
        logger.info("="*60)

        return research_data

    def _filter_by_goals(self, sector_data: Dict[str, Any], goals: List[str], risk_tolerance: str) -> Dict[str, Any]:
        """
        Filter and rank sectors based on investment goals.
        
        Args:
            sector_data: Sector deep dive data from research
            goals: List of investment goals (growth, income, esg, value, defensive, diversified)
            risk_tolerance: User's risk tolerance
            
        Returns:
            Dict with ranked_sectors and reasoning
        """
        goal_criteria = {
            "growth": {
                "prioritize": "high_performance",
                "max_volatility": {"low": 20, "medium": 30, "high": 50},
                "desc": "High-performing sectors with acceptable volatility for growth"
            },
            "income": {
                "prioritize": "low_volatility",
                "max_volatility": {"low": 15, "medium": 20, "high": 25},
                "desc": "Stable, low-volatility sectors suitable for dividend income"
            },
            "esg": {
                "prioritize": "esg_friendly",
                "preferred_sectors": ["utilities", "healthcare", "technology"],
                "desc": "Environmentally and socially responsible sectors"
            },
            "value": {
                "prioritize": "undervalued",
                "preferred_sectors": ["financial-services", "energy", "industrials", "materials"],
                "desc": "Potentially undervalued sectors with strong fundamentals"
            },
            "defensive": {
                "prioritize": "low_volatility",
                "max_volatility": {"low": 12, "medium": 18, "high": 22},
                "preferred_sectors": ["consumer-staples", "utilities", "healthcare"],
                "desc": "Defensive sectors for capital preservation"
            },
            "diversified": {
                "prioritize": "balanced",
                "desc": "Diversified exposure across multiple sectors"
            }
        }
        
        ranked_sectors = []
        
        for sector_name, data in sector_data.items():
            if "error" in data or not data:
                continue
                
            # Extract metrics
            risk_profile = data.get("risk_profile", {})
            market_perf = data.get("market_performance", {})
            news_analysis = data.get("news_analysis", {})
            
            # Parse volatility
            vol_str = risk_profile.get("annualized_volatility", "N/A")
            try:
                if isinstance(vol_str, str) and "%" in vol_str:
                    volatility = float(vol_str.replace("%", ""))
                elif isinstance(vol_str, (int, float)):
                    volatility = float(vol_str)
                else:
                    volatility = None
            except:
                volatility = None
            
            # Parse 1-month performance
            perf_1m_str = market_perf.get("performance_1m", "N/A")
            try:
                if isinstance(perf_1m_str, str) and "%" in perf_1m_str:
                    perf_1m = float(perf_1m_str.replace("%", ""))
                elif isinstance(perf_1m_str, (int, float)):
                    perf_1m = float(perf_1m_str)
                else:
                    perf_1m = None
            except:
                perf_1m = None
            
            # Score sector based on goals
            score = 0
            reasons = []
            
            for goal in goals:
                if goal not in goal_criteria:
                    continue
                    
                criteria = goal_criteria[goal]
                
                if criteria.get("prioritize") == "high_performance" and perf_1m is not None:
                    # Growth goal: reward high performance
                    if perf_1m > 5:
                        score += 30
                        reasons.append(f"Strong 1M performance ({perf_1m:.1f}%)")
                    elif perf_1m > 0:
                        score += 10
                    
                    # Check volatility acceptable for risk tolerance
                    max_vol = criteria.get("max_volatility", {}).get(risk_tolerance, 30)
                    if volatility and volatility <= max_vol:
                        score += 10
                        reasons.append(f"Volatility within {risk_tolerance} risk tolerance")
                
                elif criteria.get("prioritize") == "low_volatility" and volatility is not None:
                    # Income/Defensive goals: reward low volatility
                    max_vol = criteria.get("max_volatility", {}).get(risk_tolerance, 20)
                    if volatility <= max_vol:
                        score += 30
                        reasons.append(f"Low volatility ({volatility:.1f}%)")
                    
                    # Stable/positive performance is a bonus
                    if perf_1m is not None and perf_1m > 0:
                        score += 10
                        reasons.append("Positive recent performance")
                
                elif criteria.get("prioritize") == "esg_friendly":
                    # ESG goal: prioritize specific sectors
                    preferred = criteria.get("preferred_sectors", [])
                    if sector_name in preferred:
                        score += 25
                        reasons.append(f"ESG-aligned sector")
                    
                    # Low risk themes count
                    risk_count = len(news_analysis.get("identified_risks", []))
                    if risk_count < 15:
                        score += 10
                        reasons.append("Few identified risk themes")
                
                elif criteria.get("prioritize") == "undervalued":
                    # Value goal: prioritize specific sectors
                    preferred = criteria.get("preferred_sectors", [])
                    if sector_name in preferred:
                        score += 25
                        reasons.append("Traditional value sector")
                
                elif criteria.get("prioritize") == "balanced":
                    # Diversified: reward moderate metrics
                    if volatility and 15 <= volatility <= 25:
                        score += 15
                        reasons.append("Moderate volatility")
                    if perf_1m is not None and perf_1m > -5:
                        score += 10
            
            # Add sector to rankings
            if score > 0:
                ranked_sectors.append({
                    "sector": sector_name,
                    "score": score,
                    "volatility": f"{volatility:.2f}%" if volatility else "N/A",
                    "performance_1m": f"{perf_1m:.2f}%" if perf_1m else "N/A",
                    "reasons": reasons,
                    "risk_level": risk_profile.get("percentile", "N/A")
                })
        
        # Sort by score (descending)
        ranked_sectors.sort(key=lambda x: x["score"], reverse=True)
        
        # Generate summary
        top_picks = ranked_sectors[:3] if len(ranked_sectors) >= 3 else ranked_sectors
        
        return {
            "ranked_sectors": ranked_sectors,
            "top_picks": top_picks,
            "goals_applied": goals,
            "risk_tolerance": risk_tolerance,
            "summary": f"Based on your {', '.join(goals)} goals, we've identified {len(top_picks)} sectors worth researching."
        }

    async def _recommend_stocks_for_goals(self, goals: List[str], top_sectors: List[str]) -> Dict[str, Any]:
        """
        Recommend individual stocks based on investment goals.
        
        Args:
            goals: List of investment goals (growth, income, esg, etc.)
            top_sectors: List of top-ranked sectors to search within
            
        Returns:
            Dict with stock recommendations per goal
        """
        stock_recommendations = {}
        
        # Map goals to search criteria
        goal_search = {
            "esg": ["technology", "healthcare", "utilities"],
            "income": ["utilities", "consumer", "financial-services"],
            "growth": ["technology", "healthcare", "communications"]
        }
        
        for goal in goals:
            if goal not in goal_search:
                continue
            
            # Use intersection of goal's preferred sectors and top sectors
            sectors_to_search = goal_search.get(goal, [])
            if top_sectors:
                # Prefer top sectors, but fallback to goal defaults
                search_sectors = [s for s in top_sectors if s in sectors_to_search] or sectors_to_search[:2]
            else:
                search_sectors = sectors_to_search[:2]
            
            all_stocks = []
            for sector in search_sectors[:2]:  # Limit to 2 sectors per goal
                try:
                    stock_data = await self.get_stock_recommendations(sector, goal)
                    if "error" not in stock_data and "stocks" in stock_data:
                        all_stocks.extend(stock_data["stocks"])
                except Exception as e:
                    logger.warning(f"Failed to get stock recommendations for {sector}/{goal}: {e}")
                    continue
            
            # Score and filter stocks
            scored_stocks = []
            for stock in all_stocks:
                score = 0
                reasons = []
                
                # Parse metrics
                try:
                    perf_1m = float(stock.get("performance_1m", "0").rstrip("%"))
                    volatility = float(stock.get("volatility", "0").rstrip("%"))
                    div_yield = float(stock.get("dividend_yield", 0))
                    esg_score = float(stock.get("esg_score", 0))
                except:
                    continue
                
                # Goal-based scoring
                if goal == "esg":
                    # ESG scoring with fallback
                    if esg_score > 50:
                        score += 40
                        reasons.append(f"Strong ESG score ({esg_score:.0f})")
                    elif esg_score > 30:
                        score += 20
                        reasons.append(f"Good ESG score ({esg_score:.0f})")
                    elif esg_score > 0:
                        score += 10
                        reasons.append(f"ESG score: {esg_score:.0f}")
                    else:
                        # Fallback: score based on sector alignment and performance
                        score += 15
                        reasons.append("ESG-friendly sector")
                    
                    if volatility < 25:
                        score += 10
                        reasons.append("Low volatility")
                    
                    # Bonus for positive performance
                    if perf_1m > 0:
                        score += 5
                        reasons.append("Positive momentum")
                
                elif goal == "income":
                    if div_yield > 3:
                        score += 40
                        reasons.append(f"High dividend yield ({div_yield:.2f}%)")
                    elif div_yield > 2:
                        score += 20
                        reasons.append(f"Good dividend yield ({div_yield:.2f}%)")
                    if volatility < 20:
                        score += 10
                        reasons.append("Stable performance")
                
                elif goal == "growth":
                    if perf_1m > 5:
                        score += 40
                        reasons.append(f"Strong 1M performance ({perf_1m:+.1f}%)")
                    elif perf_1m > 0:
                        score += 20
                        reasons.append(f"Positive momentum ({perf_1m:+.1f}%)")
                    if volatility < 35:
                        score += 10
                
                if score > 0:
                    scored_stocks.append({
                        "ticker": stock["ticker"],
                        "name": stock["name"],
                        "price": stock["price"],
                        "performance_1m": stock["performance_1m"],
                        "volatility": stock["volatility"],
                        "dividend_yield": f"{div_yield:.2f}%" if div_yield > 0 else "N/A",
                        "esg_score": esg_score if esg_score > 0 else "N/A",
                        "score": score,
                        "reasons": reasons
                    })
            
            # Sort by score and take top 5
            scored_stocks.sort(key=lambda x: x["score"], reverse=True)
            top_stocks = scored_stocks[:5]
            
            if top_stocks:
                stock_recommendations[goal] = {
                    "goal": goal,
                    "stocks": top_stocks,
                    "summary": f"Top {len(top_stocks)} stocks for {goal} based on current market data"
                }
        
        return stock_recommendations


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
    
    async def close(self):
        """Alias for cleanup() for compatibility"""
        await self.cleanup()