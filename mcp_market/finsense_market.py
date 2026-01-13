import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import sys
import os
import json
import yfinance as yf
from datetime import datetime, timedelta

# Ensure stdout is unbuffered
sys.stdout.reconfigure(line_buffering=True)

# Only log to file if DEBUG environment variable is set
if os.getenv("MCP_DEBUG"):
    import logging
    from pathlib import Path
    LOG_FILE = Path(__file__).parent / "finsense_market.log"
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
app = Server("finsense-market")

# --- list_tools Handler ---
@app.list_tools()
async def list_tools() -> list[Tool]:
    log("list_tools called")
    return [
        Tool(
            name="get_sector_summary",
            description="Get market summary for a sector",
            inputSchema={
                "type": "object",
                "properties": {"sector": {"type": "string"}},
                "required": ["sector"]
            }
        ),
        Tool(
            name="get_stock_price",
            description="Get current stock price for a ticker symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL, MSFT)"}
                },
                "required": ["ticker"]
            }
        ),
        Tool(
            name="get_market_indices",
            description="Get current values of major market indices",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_stock_recommendations",
            description="Get recommended stocks for a sector based on investment goal (esg, income, growth)",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sector name (e.g., technology, healthcare)"},
                    "goal": {"type": "string", "description": "Investment goal: esg, income, or growth"}
                },
                "required": ["sector", "goal"]
            }
        ),
        Tool(
            name="get_stock_details",
            description="Get detailed information for a specific stock including fundamentals and ESG data",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL, MSFT)"}
                },
                "required": ["ticker"]
            }
        )
    ]

# --- call_tool Handler ---
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"call_tool: {name}")
    
    if name == "get_sector_summary":
        sector = arguments.get("sector", "").lower()
        # Map sectors to representative ETFs
        sector_map = {
            "technology": "XLK",
            "healthcare": "XLV",
            "financial-services": "XLF",
            "energy": "XLE",
            "consumer": "XLY",
            "industrials": "XLI",
            "materials": "XLB",
            "real-estate": "XLRE",
            "utilities": "XLU",
            "communications": "XLC"
        }
        # Fallback companies for each sector
        sector_companies = {
            "technology": ["MSFT", "AAPL", "NVDA"],
            "healthcare": ["JNJ", "UNH", "PFE"],
            "financial-services": ["JPM", "BAC", "WFC"],
            "energy": ["XOM", "CVX", "MPC"],
            "consumer": ["AMZN", "WMT", "HD"],
            "industrials": ["BA", "CAT", "DE"],
            "materials": ["APD", "NEM", "FCX"],
            "real-estate": ["AMT", "SPG", "AVB"],
            "utilities": ["NEE", "DUK", "SO"],
            "communications": ["META", "GOOGL", "VZ"]
        }
        ticker_symbol = sector_map.get(sector, "SPY")
        # Capitalize sector name for display
        sector_display = sector.title().replace("-", " ").title()
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="1y")  # Get full year for 3m and 1y calculations
            
            if len(hist) > 0:
                current_price = hist['Close'].iloc[-1]
                price_1w_ago = hist['Close'].iloc[-5] if len(hist) >= 5 else hist['Close'].iloc[0]
                price_1m_ago = hist['Close'].iloc[-21] if len(hist) >= 21 else hist['Close'].iloc[0]
                price_3m_ago = hist['Close'].iloc[-63] if len(hist) >= 63 else hist['Close'].iloc[0]
                price_1y_ago = hist['Close'].iloc[0]
                
                perf_1d = ((current_price - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) > 1 else 0
                perf_1w = ((current_price - price_1w_ago) / price_1w_ago * 100) if price_1w_ago > 0 else 0
                perf_1m = ((current_price - price_1m_ago) / price_1m_ago * 100) if price_1m_ago > 0 else 0
                perf_3m = ((current_price - price_3m_ago) / price_3m_ago * 100) if price_3m_ago > 0 else 0
                perf_1y = ((current_price - price_1y_ago) / price_1y_ago * 100) if price_1y_ago > 0 else 0
                
                # Get top performers from sector companies
                top_performers = []
                companies = sector_companies.get(sector, ["N/A"])
                for company in companies[:3]:
                    try:
                        comp_ticker = yf.Ticker(company)
                        comp_hist = comp_ticker.history(period="5d")
                        if len(comp_hist) > 1:
                            comp_perf = ((comp_hist['Close'].iloc[-1] - comp_hist['Close'].iloc[-2]) / comp_hist['Close'].iloc[-2] * 100)
                            top_performers.append({"ticker": company})
                    except Exception as e:
                        log(f"Error fetching {company} data: {e}")
                
                # Calculate market weight as percentage of total market (SPY)
                market_weight = "N/A"
                try:
                    sector_market_cap = ticker.info.get("marketCap")
                    spy = yf.Ticker("SPY")
                    spy_market_cap = spy.info.get("marketCap")
                    if sector_market_cap and spy_market_cap:
                        market_weight = f"{(sector_market_cap / spy_market_cap * 100):.2f}%"
                except:
                    pass
                
                summary = {
                    "sector": sector_display,
                    "performance_1d": f"{perf_1d:+.2f}%",
                    "performance_1w": f"{perf_1w:+.2f}%",
                    "performance_1m": f"{perf_1m:+.2f}%",
                    "performance_3m": f"{perf_3m:+.2f}%",
                    "performance_1y": f"{perf_1y:+.2f}%",
                    "current_price": round(current_price, 2),
                    "market_cap": f"{ticker.info.get('marketCap', 'N/A'):,}" if isinstance(ticker.info.get('marketCap'), (int, float)) else "N/A",
                    "market_weight": market_weight,
                    "volume": f"{ticker.info.get('volume', 'N/A'):,}" if isinstance(ticker.info.get('volume'), (int, float)) else "N/A",
                    "top_performers": top_performers
                }
            else:
                summary = {"sector": sector_display, "error": "No data available"}
        except Exception as e:
            log(f"Error fetching sector summary: {e}")
            summary = {"sector": sector_display, "error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(summary, default=str))]
    
    elif name == "get_stock_price":
        ticker = arguments.get("ticker", "").upper()
        try:
            tick = yf.Ticker(ticker)
            info = tick.info
            hist = tick.history(period="1d")
            
            if len(hist) > 0:
                current_price = hist['Close'].iloc[-1]
                if len(hist) > 1:
                    previous_price = hist['Close'].iloc[-2]
                    change = current_price - previous_price
                    change_percent = (change / previous_price * 100) if previous_price > 0 else 0
                else:
                    change = 0
                    change_percent = 0
                
                stock_data = {
                    "ticker": ticker,
                    "price": round(current_price, 2),
                    "change": f"{change:+.2f}",
                    "change_percent": f"{change_percent:+.2f}%",
                    "volume": f"{info.get('volume', 'N/A'):,}" if isinstance(info.get('volume'), (int, float)) else "N/A",
                    "market_cap": f"{info.get('marketCap', 'N/A'):,}" if isinstance(info.get('marketCap'), (int, float)) else "N/A",
                    "pe_ratio": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A"
                }
            else:
                stock_data = {"ticker": ticker, "error": "No price data available"}
        except Exception as e:
            log(f"Error fetching stock price: {e}")
            stock_data = {"ticker": ticker, "error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(stock_data, default=str))]
    
    elif name == "get_market_indices":
        indices_map = {
            "SPX": "^GSPC",
            "DJI": "^DJI",
            "IXIC": "^IXIC",
            "RUT": "^RUT"
        }
        indices = {}
        
        try:
            for name_key, symbol in indices_map.items():
                tick = yf.Ticker(symbol)
                hist = tick.history(period="1d")
                
                if len(hist) > 0:
                    current_price = hist['Close'].iloc[-1]
                    if len(hist) > 1:
                        previous_price = hist['Close'].iloc[-2]
                        change_percent = ((current_price - previous_price) / previous_price * 100) if previous_price > 0 else 0
                    else:
                        change_percent = 0
                    
                    indices[name_key] = {
                        "value": round(current_price, 2),
                        "change": f"{change_percent:+.2f}%"
                    }
        except Exception as e:
            log(f"Error fetching market indices: {e}")
        
        return [TextContent(type="text", text=json.dumps(indices, default=str))]
    
    elif name == "get_stock_recommendations":
        sector = arguments.get("sector", "").lower()
        goal = arguments.get("goal", "").lower()
        
        # Map sectors to top companies
        sector_stocks = {
            "technology": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ADBE", "CRM"],
            "healthcare": ["JNJ", "UNH", "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR"],
            "financial-services": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW"],
            "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO"],
            "consumer": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TJX", "LOW"],
            "industrials": ["BA", "CAT", "GE", "HON", "UNP", "RTX", "LMT", "DE"],
            "materials": ["LIN", "APD", "SHW", "FCX", "NEM", "ECL", "DD", "NUE"],
            "real-estate": ["AMT", "PLD", "CCI", "EQIX", "SPG", "PSA", "O", "WELL"],
            "utilities": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL"],
            "communications": ["META", "GOOGL", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS"]
        }
        
        stock_list = sector_stocks.get(sector, [])
        if not stock_list:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown sector: {sector}"}, default=str))]
        
        recommendations = []
        try:
            for ticker_symbol in stock_list[:8]:  # Limit to 8 stocks
                try:
                    tick = yf.Ticker(ticker_symbol)
                    info = tick.info
                    hist = tick.history(period="3mo")
                    
                    if len(hist) < 5:
                        continue
                    
                    current_price = hist['Close'].iloc[-1]
                    price_1m_ago = hist['Close'].iloc[-21] if len(hist) >= 21 else hist['Close'].iloc[0]
                    perf_1m = ((current_price - price_1m_ago) / price_1m_ago * 100) if price_1m_ago > 0 else 0
                    
                    # Calculate volatility
                    returns = hist['Close'].pct_change().dropna()
                    volatility = returns.std() * (252 ** 0.5) * 100 if len(returns) > 0 else 0
                    
                    stock_data = {
                        "ticker": ticker_symbol,
                        "name": info.get("shortName", ticker_symbol),
                        "price": round(current_price, 2),
                        "performance_1m": f"{perf_1m:+.2f}%",
                        "volatility": f"{volatility:.2f}%",
                        "market_cap": info.get("marketCap", 0),
                        "dividend_yield": info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0,
                        "pe_ratio": info.get("trailingPE", 0),
                        "esg_score": info.get("esgScores", {}).get("totalEsg", 0) if isinstance(info.get("esgScores"), dict) else 0
                    }
                    recommendations.append(stock_data)
                except Exception as e:
                    log(f"Error fetching {ticker_symbol}: {e}")
                    continue
            
            # Sort by goal criteria
            if goal == "esg":
                recommendations.sort(key=lambda x: (x["esg_score"], -x.get("volatility", 100)), reverse=True)
            elif goal == "income":
                recommendations.sort(key=lambda x: x["dividend_yield"], reverse=True)
            elif goal == "growth":
                recommendations.sort(key=lambda x: float(x["performance_1m"].rstrip("%")), reverse=True)
            
            result = {
                "sector": sector,
                "goal": goal,
                "stocks": recommendations[:5]  # Return top 5
            }
        except Exception as e:
            log(f"Error in get_stock_recommendations: {e}")
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    
    elif name == "get_stock_details":
        ticker = arguments.get("ticker", "").upper()
        try:
            tick = yf.Ticker(ticker)
            info = tick.info
            hist = tick.history(period="1y")
            
            if len(hist) > 0:
                current_price = hist['Close'].iloc[-1]
                price_1m_ago = hist['Close'].iloc[-21] if len(hist) >= 21 else hist['Close'].iloc[0]
                price_3m_ago = hist['Close'].iloc[-63] if len(hist) >= 63 else hist['Close'].iloc[0]
                price_1y_ago = hist['Close'].iloc[0]
                
                perf_1m = ((current_price - price_1m_ago) / price_1m_ago * 100) if price_1m_ago > 0 else 0
                perf_3m = ((current_price - price_3m_ago) / price_3m_ago * 100) if price_3m_ago > 0 else 0
                perf_1y = ((current_price - price_1y_ago) / price_1y_ago * 100) if price_1y_ago > 0 else 0
                
                returns = hist['Close'].pct_change().dropna()
                volatility = returns.std() * (252 ** 0.5) * 100 if len(returns) > 0 else 0
                
                stock_details = {
                    "ticker": ticker,
                    "name": info.get("shortName", ticker),
                    "sector": info.get("sector", "N/A"),
                    "industry": info.get("industry", "N/A"),
                    "price": round(current_price, 2),
                    "performance_1m": f"{perf_1m:+.2f}%",
                    "performance_3m": f"{perf_3m:+.2f}%",
                    "performance_1y": f"{perf_1y:+.2f}%",
                    "volatility": f"{volatility:.2f}%",
                    "market_cap": info.get("marketCap", "N/A"),
                    "pe_ratio": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A",
                    "dividend_yield": f"{info.get('dividendYield', 0) * 100:.2f}%" if info.get("dividendYield") else "N/A",
                    "52w_high": round(info.get("fiftyTwoWeekHigh", 0), 2) if info.get("fiftyTwoWeekHigh") else "N/A",
                    "52w_low": round(info.get("fiftyTwoWeekLow", 0), 2) if info.get("fiftyTwoWeekLow") else "N/A",
                    "description": info.get("longBusinessSummary", "No description available")[:200]
                }
            else:
                stock_details = {"ticker": ticker, "error": "No data available"}
        except Exception as e:
            log(f"Error fetching stock details: {e}")
            stock_details = {"ticker": ticker, "error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(stock_details, default=str))]
    
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