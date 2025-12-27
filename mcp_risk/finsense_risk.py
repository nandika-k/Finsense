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
    LOG_FILE = Path(__file__).parent / "finsense_risk.log"
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
app = Server("finsense-risk")

# --- list_tools Handler ---
@app.list_tools()
async def list_tools() -> list[Tool]:
    log("list_tools called")
    return [
        Tool(
            name="compute_sector_volatility",
            description="Compute volatility for a sector",
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
            name="compare_sectors",
            description="Compare risk metrics between two sectors",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector1": {"type": "string"},
                    "sector2": {"type": "string"},
                    "timeframe": {"type": "string"}
                },
                "required": ["sector1", "sector2", "timeframe"]
            }
        ),
        Tool(
            name="compute_sector_correlations",
            description="Compute correlations between sectors",
            inputSchema={
                "type": "object",
                "properties": {
                    "sectors": {"type": "array", "items": {"type": "string"}},
                    "timeframe": {"type": "string"}
                },
                "required": ["sectors", "timeframe"]
            }
        ),
        Tool(
            name="calculate_var",
            description="Calculate Value at Risk (VaR) for a portfolio",
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio": {"type": "object", "description": "Portfolio holdings"},
                    "confidence_level": {"type": "number", "description": "Confidence level (e.g., 0.95, 0.99)"},
                    "timeframe": {"type": "string"}
                },
                "required": ["portfolio", "confidence_level", "timeframe"]
            }
        ),
        Tool(
            name="stress_test",
            description="Perform stress testing on a sector or portfolio",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {"type": "string"},
                    "scenario": {"type": "string", "description": "Stress scenario (e.g., 'market_crash', 'rate_hike')"}
                },
                "required": ["sector", "scenario"]
            }
        )
    ]

# --- call_tool Handler ---
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"call_tool: {name}")
    
    if name == "compute_sector_volatility":
        sector = arguments.get("sector", "")
        timeframe = arguments.get("timeframe", "")
        # Mock data - replace with real volatility calculations
        volatility_data = {
            "sector": sector,
            "timeframe": timeframe,
            "volatility": "18.5%",
            "annualized_volatility": "22.3%",
            "historical_average": "20.1%",
            "percentile": "65th",
            "trend": "decreasing"
        }
        return [TextContent(type="text", text=str(volatility_data))]
    
    elif name == "compare_sectors":
        s1 = arguments.get("sector1", "")
        s2 = arguments.get("sector2", "")
        timeframe = arguments.get("timeframe", "")
        # Mock data - replace with real comparison calculations
        comparison = {
            "sector1": s1,
            "sector2": s2,
            "timeframe": timeframe,
            "volatility_comparison": {
                s1: "18.5%",
                s2: "22.3%",
                "difference": "3.8%"
            },
            "sharpe_ratio": {
                s1: 1.25,
                s2: 0.95
            },
            "max_drawdown": {
                s1: "-15.2%",
                s2: "-22.8%"
            },
            "beta": {
                s1: 1.05,
                s2: 1.32
            },
            "recommendation": f"{s1} shows lower risk profile"
        }
        return [TextContent(type="text", text=str(comparison))]
    
    elif name == "compute_sector_correlations":
        sectors = arguments.get("sectors", [])
        timeframe = arguments.get("timeframe", "")
        # Mock data - replace with real correlation matrix
        correlations = {
            "timeframe": timeframe,
            "correlation_matrix": {
                f"{sectors[i]}-{sectors[j]}": round(0.3 + (i * j * 0.1) % 0.7, 2)
                for i in range(len(sectors))
                for j in range(i+1, len(sectors))
            } if len(sectors) > 1 else {},
            "average_correlation": 0.62,
            "highest_correlation": f"{sectors[0]}-{sectors[1]}: 0.85" if len(sectors) > 1 else "N/A",
            "diversification_score": "Moderate"
        }
        return [TextContent(type="text", text=str(correlations))]
    
    elif name == "calculate_var":
        portfolio = arguments.get("portfolio", {})
        confidence_level = arguments.get("confidence_level", 0.95)
        timeframe = arguments.get("timeframe", "")
        # Mock data - replace with real VaR calculation
        var_data = {
            "confidence_level": f"{confidence_level*100}%",
            "timeframe": timeframe,
            "var_1day": "$125,000",
            "var_1week": "$275,000",
            "var_1month": "$550,000",
            "portfolio_value": "$10,000,000",
            "var_percentage": "5.5%",
            "method": "Historical Simulation",
            "interpretation": f"With {confidence_level*100}% confidence, losses will not exceed VaR amount"
        }
        return [TextContent(type="text", text=str(var_data))]
    
    elif name == "stress_test":
        sector = arguments.get("sector", "")
        scenario = arguments.get("scenario", "")
        # Mock data - replace with real stress testing
        stress_results = {
            "sector": sector,
            "scenario": scenario,
            "projected_impact": "-18.5%",
            "worst_case": "-25.2%",
            "best_case": "-12.1%",
            "probability": "15%",
            "recovery_time": "6-9 months",
            "key_risks": [
                "Liquidity constraints",
                "Credit defaults",
                "Market contagion"
            ],
            "recommended_hedges": [
                "Increase cash reserves by 20%",
                "Purchase put options on sector ETF",
                "Diversify into defensive sectors"
            ]
        }
        return [TextContent(type="text", text=str(stress_results))]
    
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