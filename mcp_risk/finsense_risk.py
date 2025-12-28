import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import sys
import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

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

# --- Helper Functions ---
def get_sector_ticker(sector: str) -> str:
    """Map sector name to representative ETF ticker"""
    sector_map = {
        "technology": "XLK",
        "healthcare": "XLV",
        "financial-services": "XLF",
        "financial": "XLF",
        "energy": "XLE",
        "consumer": "XLY",
        "consumer-discretionary": "XLY",
        "industrials": "XLI",
        "materials": "XLB",
        "real-estate": "XLRE",
        "utilities": "XLU",
        "communications": "XLC",
        "consumer-staples": "XLP"
    }
    return sector_map.get(sector.lower(), "SPY")

def parse_timeframe(timeframe: str) -> tuple[str, int]:
    """Parse timeframe string to yfinance period and days"""
    timeframe_lower = timeframe.lower()
    
    if "1d" in timeframe_lower or "1 day" in timeframe_lower:
        return "5d", 1
    elif "1w" in timeframe_lower or "1 week" in timeframe_lower or "week" in timeframe_lower:
        return "1mo", 7
    elif "1m" in timeframe_lower or "1 month" in timeframe_lower or "month" in timeframe_lower:
        return "3mo", 30
    elif "3m" in timeframe_lower or "3 month" in timeframe_lower:
        return "6mo", 90
    elif "6m" in timeframe_lower or "6 month" in timeframe_lower:
        return "1y", 180
    elif "1y" in timeframe_lower or "1 year" in timeframe_lower or "year" in timeframe_lower:
        return "2y", 252
    elif "2y" in timeframe_lower or "2 year" in timeframe_lower:
        return "5y", 504
    elif "5y" in timeframe_lower or "5 year" in timeframe_lower:
        return "max", 1260
    else:
        # Default to 1 year
        return "2y", 252

def calculate_volatility_metrics(price_data: pd.Series, days: int) -> dict:
    """Calculate comprehensive volatility metrics from price data"""
    if len(price_data) < 2:
        return {}
    
    # Calculate daily returns
    returns = price_data.pct_change().dropna()
    
    if len(returns) == 0:
        return {}
    
    # Realized volatility (standard deviation of returns)
    realized_vol = returns.std()
    
    # Annualized volatility (multiply by sqrt of trading days)
    # Use actual number of days in data, but cap at 252 for annualization
    trading_days = min(len(returns), 252)
    annualized_vol = realized_vol * np.sqrt(252)
    
    # Rolling volatility (30-day and 60-day windows)
    rolling_30d = returns.rolling(window=min(30, len(returns))).std().iloc[-1] * np.sqrt(252) if len(returns) >= 30 else None
    rolling_60d = returns.rolling(window=min(60, len(returns))).std().iloc[-1] * np.sqrt(252) if len(returns) >= 60 else None
    
    # Calculate max drawdown
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # Volatility trend (compare recent vs older volatility)
    if len(returns) >= 60:
        recent_vol = returns.iloc[-30:].std() * np.sqrt(252)
        older_vol = returns.iloc[-60:-30].std() * np.sqrt(252)
        trend = "increasing" if recent_vol > older_vol * 1.05 else "decreasing" if recent_vol < older_vol * 0.95 else "stable"
    elif len(returns) >= 30:
        recent_vol = returns.iloc[-15:].std() * np.sqrt(252)
        older_vol = returns.iloc[-30:-15].std() * np.sqrt(252)
        trend = "increasing" if recent_vol > older_vol * 1.05 else "decreasing" if recent_vol < older_vol * 0.95 else "stable"
    else:
        trend = "insufficient_data"
    
    # Historical average (mean of rolling 30-day volatilities)
    if len(returns) >= 30:
        rolling_vols = returns.rolling(window=30).std() * np.sqrt(252)
        historical_avg = rolling_vols.mean()
    else:
        historical_avg = annualized_vol
    
    # Percentile calculation (simplified - compare to typical ranges)
    # Typical annualized volatility ranges: 10-15% (low), 15-25% (medium), 25%+ (high)
    if annualized_vol < 0.15:
        percentile_range = "low (bottom 25%)"
    elif annualized_vol < 0.25:
        percentile_range = "medium (25-75%)"
    else:
        percentile_range = "high (top 25%)"
    
    return {
        "realized_volatility": f"{realized_vol * 100:.2f}%",
        "annualized_volatility": f"{annualized_vol * 100:.2f}%",
        "rolling_30d_volatility": f"{rolling_30d * 100:.2f}%" if rolling_30d is not None else "N/A",
        "rolling_60d_volatility": f"{rolling_60d * 100:.2f}%" if rolling_60d is not None else "N/A",
        "historical_average": f"{historical_avg * 100:.2f}%",
        "max_drawdown": f"{max_drawdown * 100:.2f}%",
        "trend": trend,
        "percentile": percentile_range,
        "data_points": len(returns),
        # Store raw values for comparison calculations
        "_raw_returns": returns,
        "_raw_annualized_vol": annualized_vol,
        "_raw_max_drawdown": max_drawdown
    }

def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Calculate Sharpe ratio (annualized)"""
    if len(returns) == 0:
        return 0.0
    # Annualized return
    total_return = (1 + returns).prod() - 1
    periods_per_year = 252
    annualized_return = (1 + total_return) ** (periods_per_year / len(returns)) - 1
    # Annualized volatility
    annualized_vol = returns.std() * np.sqrt(252)
    # Sharpe ratio
    if annualized_vol == 0:
        return 0.0
    return (annualized_return - risk_free_rate) / annualized_vol

def calculate_beta(sector_returns: pd.Series, market_returns: pd.Series) -> float:
    """Calculate beta (correlation × relative volatility)"""
    if len(sector_returns) == 0 or len(market_returns) == 0:
        return 1.0
    # Align the series
    aligned = pd.DataFrame({'sector': sector_returns, 'market': market_returns}).dropna()
    if len(aligned) < 2:
        return 1.0
    # Calculate covariance and variance
    covariance = aligned['sector'].cov(aligned['market'])
    market_variance = aligned['market'].var()
    if market_variance == 0:
        return 1.0
    beta = covariance / market_variance
    return beta

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
        )
    ]

# --- call_tool Handler ---
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"call_tool: {name}")
    
    if name == "compute_sector_volatility":
        sector = arguments.get("sector", "")
        timeframe = arguments.get("timeframe", "")
        
        try:
            # Get sector ticker
            ticker_symbol = get_sector_ticker(sector)
            
            # Parse timeframe
            period, days = parse_timeframe(timeframe)
            
            # Fetch historical data
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period=period)
            
            if hist.empty or len(hist) < 2:
                return [TextContent(
                    type="text", 
                    text=json.dumps({
                        "error": f"Insufficient data for sector '{sector}' (ticker: {ticker_symbol})",
                        "sector": sector,
                        "ticker": ticker_symbol
                    })
                )]
            
            # Calculate volatility metrics
            price_data = hist['Close']
            metrics = calculate_volatility_metrics(price_data, days)
            
            # Remove internal raw values before returning
            metrics_clean = {k: v for k, v in metrics.items() if not k.startswith('_')}
            
            # Get market comparison (SPY)
            try:
                spy_ticker = yf.Ticker("SPY")
                spy_hist = spy_ticker.history(period=period)
                if not spy_hist.empty and len(spy_hist) >= 2:
                    spy_returns = spy_hist['Close'].pct_change().dropna()
                    spy_vol = spy_returns.std() * np.sqrt(252)
                    market_vol = f"{spy_vol * 100:.2f}%"
                    
                    # Calculate relative volatility
                    sector_vol = float(metrics_clean["annualized_volatility"].rstrip('%')) / 100
                    relative_to_market = sector_vol / spy_vol if spy_vol > 0 else 1.0
                    metrics_clean["market_volatility"] = market_vol
                    metrics_clean["relative_to_market"] = f"{relative_to_market:.2f}x"
                else:
                    metrics_clean["market_volatility"] = "N/A"
                    metrics_clean["relative_to_market"] = "N/A"
            except Exception as e:
                log(f"Error fetching market data: {e}")
                metrics_clean["market_volatility"] = "N/A"
                metrics_clean["relative_to_market"] = "N/A"
            
            # Compile results
            volatility_data = {
                "sector": sector,
                "ticker": ticker_symbol,
                "timeframe": timeframe,
                "period_analyzed": period,
                **metrics_clean
            }
            
            return [TextContent(type="text", text=json.dumps(volatility_data, indent=2))]
            
        except Exception as e:
            log(f"Error computing sector volatility: {e}")
            return [TextContent(
                type="text", 
                text=json.dumps({
                    "error": f"Failed to compute volatility for sector '{sector}': {str(e)}",
                    "sector": sector,
                    "timeframe": timeframe
                })
            )]
    
    elif name == "compare_sectors":
        s1 = arguments.get("sector1", "")
        s2 = arguments.get("sector2", "")
        timeframe = arguments.get("timeframe", "")
        
        try:
            # Get tickers for both sectors
            ticker1 = get_sector_ticker(s1)
            ticker2 = get_sector_ticker(s2)
            
            # Parse timeframe
            period, days = parse_timeframe(timeframe)
            
            # Fetch historical data for both sectors
            t1 = yf.Ticker(ticker1)
            t2 = yf.Ticker(ticker2)
            hist1 = t1.history(period=period)
            hist2 = t2.history(period=period)
            
            if hist1.empty or len(hist1) < 2 or hist2.empty or len(hist2) < 2:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Insufficient data for comparison",
                        "sector1": s1,
                        "sector2": s2,
                        "ticker1": ticker1,
                        "ticker2": ticker2
                    })
                )]
            
            # Calculate metrics for both sectors
            price1 = hist1['Close']
            price2 = hist2['Close']
            metrics1 = calculate_volatility_metrics(price1, days)
            metrics2 = calculate_volatility_metrics(price2, days)
            
            # Get raw values for calculations
            returns1 = metrics1.get("_raw_returns", pd.Series())
            returns2 = metrics2.get("_raw_returns", pd.Series())
            vol1 = metrics1.get("_raw_annualized_vol", 0.0)
            vol2 = metrics2.get("_raw_annualized_vol", 0.0)
            drawdown1 = metrics1.get("_raw_max_drawdown", 0.0)
            drawdown2 = metrics2.get("_raw_max_drawdown", 0.0)
            
            # Calculate total returns
            total_return1 = ((price1.iloc[-1] / price1.iloc[0]) - 1) * 100 if len(price1) > 0 else 0.0
            total_return2 = ((price2.iloc[-1] / price2.iloc[0]) - 1) * 100 if len(price2) > 0 else 0.0
            
            # Calculate Sharpe ratios
            sharpe1 = calculate_sharpe_ratio(returns1) if len(returns1) > 0 else 0.0
            sharpe2 = calculate_sharpe_ratio(returns2) if len(returns2) > 0 else 0.0
            
            # Calculate beta (relative to SPY)
            beta1 = 1.0
            beta2 = 1.0
            try:
                spy_ticker = yf.Ticker("SPY")
                spy_hist = spy_ticker.history(period=period)
                if not spy_hist.empty and len(spy_hist) >= 2:
                    spy_returns = spy_hist['Close'].pct_change().dropna()
                    # Align returns with market
                    if len(returns1) > 0:
                        aligned1 = pd.DataFrame({'sector': returns1, 'market': spy_returns}).dropna()
                        if len(aligned1) >= 2:
                            beta1 = calculate_beta(aligned1['sector'], aligned1['market'])
                    if len(returns2) > 0:
                        aligned2 = pd.DataFrame({'sector': returns2, 'market': spy_returns}).dropna()
                        if len(aligned2) >= 2:
                            beta2 = calculate_beta(aligned2['sector'], aligned2['market'])
            except Exception as e:
                log(f"Error calculating beta: {e}")
            
            # Calculate differences
            vol_diff = vol1 - vol2
            drawdown_diff = drawdown1 - drawdown2
            sharpe_diff = sharpe1 - sharpe2
            return_diff = total_return1 - total_return2
            beta_diff = beta1 - beta2
            
            # Generate recommendation
            risk_factors = []
            if vol1 < vol2:
                risk_factors.append(f"{s1} has lower volatility")
            else:
                risk_factors.append(f"{s2} has lower volatility")
            
            if abs(drawdown1) < abs(drawdown2):
                risk_factors.append(f"{s1} has smaller max drawdown")
            else:
                risk_factors.append(f"{s2} has smaller max drawdown")
            
            if sharpe1 > sharpe2:
                risk_factors.append(f"{s1} has better risk-adjusted returns (Sharpe)")
            else:
                risk_factors.append(f"{s2} has better risk-adjusted returns (Sharpe)")
            
            recommendation = f"Based on {timeframe} analysis: " + "; ".join(risk_factors[:2])
            
            # Compile comparison results
            comparison = {
                "sector1": s1,
                "sector2": s2,
                "ticker1": ticker1,
                "ticker2": ticker2,
                "timeframe": timeframe,
                "volatility_comparison": {
                    s1: f"{vol1 * 100:.2f}%",
                    s2: f"{vol2 * 100:.2f}%",
                    "difference": f"{vol_diff * 100:+.2f}%",
                    "lower_volatility": s1 if vol1 < vol2 else s2
                },
                "max_drawdown": {
                    s1: f"{drawdown1 * 100:.2f}%",
                    s2: f"{drawdown2 * 100:.2f}%",
                    "difference": f"{drawdown_diff * 100:+.2f}%",
                    "lower_drawdown": s1 if abs(drawdown1) < abs(drawdown2) else s2
                },
                "total_return": {
                    s1: f"{total_return1:.2f}%",
                    s2: f"{total_return2:.2f}%",
                    "difference": f"{return_diff:+.2f}%",
                    "higher_return": s1 if total_return1 > total_return2 else s2
                },
                "sharpe_ratio": {
                    s1: round(sharpe1, 2),
                    s2: round(sharpe2, 2),
                    "difference": round(sharpe_diff, 2),
                    "higher_sharpe": s1 if sharpe1 > sharpe2 else s2
                },
                "beta": {
                    s1: round(beta1, 2),
                    s2: round(beta2, 2),
                    "difference": round(beta_diff, 2),
                    "lower_beta": s1 if beta1 < beta2 else s2
                },
                "recommendation": recommendation
            }
            
            return [TextContent(type="text", text=json.dumps(comparison, indent=2))]
            
        except Exception as e:
            log(f"Error comparing sectors: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Failed to compare sectors: {str(e)}",
                    "sector1": s1,
                    "sector2": s2,
                    "timeframe": timeframe
                })
            )]
    
    elif name == "compute_sector_correlations":
        sectors = arguments.get("sectors", [])
        timeframe = arguments.get("timeframe", "")
        
        try:
            if len(sectors) < 2:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "At least 2 sectors required for correlation analysis",
                        "sectors": sectors
                    })
                )]
            
            # Parse timeframe
            period, days = parse_timeframe(timeframe)
            
            # Fetch historical data for all sectors
            sector_data = {}
            sector_tickers = {}
            returns_data = {}
            
            for sector in sectors:
                ticker_symbol = get_sector_ticker(sector)
                sector_tickers[sector] = ticker_symbol
                
                try:
                    ticker = yf.Ticker(ticker_symbol)
                    hist = ticker.history(period=period)
                    
                    if not hist.empty and len(hist) >= 2:
                        # Calculate daily returns
                        returns = hist['Close'].pct_change().dropna()
                        returns_data[sector] = returns
                        sector_data[sector] = hist
                    else:
                        log(f"Insufficient data for {sector} ({ticker_symbol})")
                except Exception as e:
                    log(f"Error fetching data for {sector} ({ticker_symbol}): {e}")
            
            if len(returns_data) < 2:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Insufficient data for correlation analysis",
                        "sectors": sectors,
                        "available_data": list(returns_data.keys())
                    })
                )]
            
            # Align all return series to common dates
            returns_df = pd.DataFrame(returns_data)
            returns_df = returns_df.dropna()  # Remove rows with any NaN values
            
            if len(returns_df) < 2:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Insufficient overlapping data for correlation analysis",
                        "sectors": sectors
                    })
                )]
            
            # Calculate correlation matrix
            correlation_matrix = returns_df.corr()
            
            # Extract pairwise correlations (excluding diagonal)
            pairwise_correlations = {}
            correlations_list = []
            
            for i, sector1 in enumerate(correlation_matrix.columns):
                for j, sector2 in enumerate(correlation_matrix.columns):
                    if i < j:  # Only upper triangle to avoid duplicates
                        corr_value = correlation_matrix.loc[sector1, sector2]
                        pair_key = f"{sector1}-{sector2}"
                        pairwise_correlations[pair_key] = round(corr_value, 3)
                        correlations_list.append({
                            "sector1": sector1,
                            "sector2": sector2,
                            "correlation": round(corr_value, 3)
                        })
            
            # Calculate average correlation
            if correlations_list:
                avg_correlation = sum(c["correlation"] for c in correlations_list) / len(correlations_list)
            else:
                avg_correlation = 0.0
            
            # Find highest and lowest correlations
            if correlations_list:
                highest = max(correlations_list, key=lambda x: x["correlation"])
                lowest = min(correlations_list, key=lambda x: x["correlation"])
                highest_pair = f"{highest['sector1']}-{highest['sector2']}: {highest['correlation']:.3f}"
                lowest_pair = f"{lowest['sector1']}-{lowest['sector2']}: {lowest['correlation']:.3f}"
            else:
                highest_pair = "N/A"
                lowest_pair = "N/A"
            
            # Calculate diversification score
            # Lower average correlation = better diversification
            if avg_correlation < 0.3:
                diversification_score = "High"
                diversification_interpretation = "Sectors show low correlation, providing good diversification benefits"
            elif avg_correlation < 0.6:
                diversification_score = "Moderate"
                diversification_interpretation = "Sectors show moderate correlation, some diversification benefits"
            else:
                diversification_score = "Low"
                diversification_interpretation = "Sectors are highly correlated, limited diversification benefits"
            
            # Identify sectors that move together (correlation > 0.7 = strong, > 0.6 = moderate-high)
            high_correlation_pairs = [
                f"{c['sector1']}-{c['sector2']} ({c['correlation']:.3f})" 
                for c in correlations_list 
                if c['correlation'] > 0.7
            ]
            
            # Identify moderately correlated pairs (0.6-0.7)
            moderate_high_correlation_pairs = [
                f"{c['sector1']}-{c['sector2']} ({c['correlation']:.3f})" 
                for c in correlations_list 
                if 0.6 <= c['correlation'] <= 0.7
            ]
            
            # Identify best diversification pairs (correlation < 0.3 = strong, < 0.4 = moderate-low)
            low_correlation_pairs = [
                f"{c['sector1']}-{c['sector2']} ({c['correlation']:.3f})" 
                for c in correlations_list 
                if c['correlation'] < 0.3
            ]
            
            # Identify moderately independent pairs (0.3-0.4)
            moderate_low_correlation_pairs = [
                f"{c['sector1']}-{c['sector2']} ({c['correlation']:.3f})" 
                for c in correlations_list 
                if 0.3 <= c['correlation'] < 0.4
            ]
            
            # Compile results
            correlation_results = {
                "timeframe": timeframe,
                "period_analyzed": period,
                "sectors_analyzed": list(returns_df.columns),
                "tickers": {s: sector_tickers.get(s, "N/A") for s in returns_df.columns},
                "data_points": len(returns_df),
                "correlation_matrix": pairwise_correlations,
                "average_correlation": round(avg_correlation, 3),
                "highest_correlation": {
                    "pair": highest_pair,
                    "sector1": highest['sector1'] if correlations_list else "N/A",
                    "sector2": highest['sector2'] if correlations_list else "N/A",
                    "value": round(highest['correlation'], 3) if correlations_list else "N/A",
                    "interpretation": "These sectors tend to move together"
                },
                "lowest_correlation": {
                    "pair": lowest_pair,
                    "sector1": lowest['sector1'] if correlations_list else "N/A",
                    "sector2": lowest['sector2'] if correlations_list else "N/A",
                    "value": round(lowest['correlation'], 3) if correlations_list else "N/A",
                    "interpretation": "Best diversification opportunity"
                },
                "diversification_score": diversification_score,
                "diversification_interpretation": diversification_interpretation,
                "highly_correlated_pairs": high_correlation_pairs if high_correlation_pairs else [],
                "moderately_correlated_pairs": moderate_high_correlation_pairs if moderate_high_correlation_pairs else [],
                "low_correlation_pairs": low_correlation_pairs if low_correlation_pairs else [],
                "moderately_independent_pairs": moderate_low_correlation_pairs if moderate_low_correlation_pairs else [],
                "insights": {
                    "sectors_moving_together": high_correlation_pairs[:3] if high_correlation_pairs else (moderate_high_correlation_pairs[:2] if moderate_high_correlation_pairs else ["None identified (all correlations < 0.6)"]),
                    "best_diversification_opportunities": low_correlation_pairs[:3] if low_correlation_pairs else (moderate_low_correlation_pairs[:2] if moderate_low_correlation_pairs else ["None identified (all correlations > 0.4)"])
                }
            }
            
            return [TextContent(type="text", text=json.dumps(correlation_results, indent=2))]
            
        except Exception as e:
            log(f"Error computing sector correlations: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Failed to compute sector correlations: {str(e)}",
                    "sectors": sectors,
                    "timeframe": timeframe
                })
            )]
    
    elif name == "calculate_var":
        portfolio = arguments.get("portfolio", {})
        confidence_level = arguments.get("confidence_level", 0.95)
        timeframe = arguments.get("timeframe", "")
        portfolio_value = arguments.get("portfolio_value", None)  # Optional: portfolio value in dollars
        
        try:
            if not portfolio or len(portfolio) == 0:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Portfolio is empty or invalid",
                        "portfolio": portfolio
                    })
                )]
            
            # Validate and normalize portfolio weights
            total_weight = sum(float(w) for w in portfolio.values())
            if abs(total_weight - 1.0) > 0.01:  # Allow small rounding errors
                # Normalize weights if they don't sum to 1
                portfolio = {k: float(v) / total_weight for k, v in portfolio.items()}
                log(f"Portfolio weights normalized to sum to 1.0")
            
            # Parse timeframe for historical data
            period, days = parse_timeframe(timeframe)
            # Use longer period for better VaR estimation
            if period == "5d":
                period = "3mo"
            elif period in ["1mo", "3mo"]:
                period = "1y"
            
            # Fetch historical data for all holdings
            holdings_returns = {}
            holdings_tickers = {}
            
            for holding, weight in portfolio.items():
                # Check if it's a sector name or ticker symbol
                if holding.lower() in ["technology", "healthcare", "financial-services", "financial", 
                                      "energy", "consumer", "consumer-discretionary", "industrials",
                                      "materials", "real-estate", "utilities", "communications", 
                                      "consumer-staples"]:
                    ticker_symbol = get_sector_ticker(holding)
                    holdings_tickers[holding] = ticker_symbol
                else:
                    # Assume it's a ticker symbol
                    ticker_symbol = holding.upper()
                    holdings_tickers[holding] = ticker_symbol
                
                try:
                    ticker = yf.Ticker(ticker_symbol)
                    hist = ticker.history(period=period)
                    
                    if not hist.empty and len(hist) >= 2:
                        # Calculate daily returns
                        returns = hist['Close'].pct_change().dropna()
                        holdings_returns[holding] = returns
                    else:
                        log(f"Insufficient data for {holding} ({ticker_symbol})")
                except Exception as e:
                    log(f"Error fetching data for {holding} ({ticker_symbol}): {e}")
            
            if len(holdings_returns) == 0:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Could not fetch data for any portfolio holdings",
                        "portfolio": portfolio,
                        "tickers_attempted": holdings_tickers
                    })
                )]
            
            # Align all return series to common dates
            returns_df = pd.DataFrame(holdings_returns)
            returns_df = returns_df.dropna()  # Remove rows with any NaN values
            
            if len(returns_df) < 30:  # Need at least 30 days for meaningful VaR
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Insufficient overlapping data for VaR calculation",
                        "data_points": len(returns_df),
                        "minimum_required": 30
                    })
                )]
            
            # Calculate portfolio returns (weighted average)
            portfolio_weights = [float(portfolio.get(holding, 0)) for holding in returns_df.columns]
            portfolio_returns = (returns_df * portfolio_weights).sum(axis=1)
            
            # Calculate VaR using Historical Simulation method
            # VaR is the loss at the (1 - confidence_level) percentile
            # For 95% confidence, we want the 5th percentile (worst 5% of outcomes)
            percentile = (1 - confidence_level) * 100
            
            # 1-day VaR (as percentage) - the percentile gives us the worst return
            # VaR is the absolute value of negative returns (losses)
            var_percentile_value = np.percentile(portfolio_returns, percentile)
            var_1day_pct = abs(var_percentile_value) if var_percentile_value < 0 else 0.0
            
            # Multi-day VaR using square root of time rule (simplified)
            # VaR scales with square root of time for independent returns
            var_1week_pct = var_1day_pct * np.sqrt(5)  # 5 trading days
            var_1month_pct = var_1day_pct * np.sqrt(21)  # ~21 trading days
            
            # Convert to absolute values if portfolio value provided
            if portfolio_value:
                portfolio_value = float(portfolio_value)
                var_1day_abs = portfolio_value * var_1day_pct
                var_1week_abs = portfolio_value * var_1week_pct
                var_1month_abs = portfolio_value * var_1month_pct
            else:
                portfolio_value = None
                var_1day_abs = None
                var_1week_abs = None
                var_1month_abs = None
            
            # Calculate additional statistics
            mean_return = portfolio_returns.mean()
            std_return = portfolio_returns.std()
            min_return = portfolio_returns.min()
            max_return = portfolio_returns.max()
            
            # Expected shortfall (Conditional VaR) - average of losses beyond VaR
            var_threshold = np.percentile(portfolio_returns, percentile)
            tail_losses = portfolio_returns[portfolio_returns <= var_threshold]
            expected_shortfall = abs(tail_losses.mean()) if len(tail_losses) > 0 else var_1day_pct
            
            # Compile results
            var_data = {
                "confidence_level": f"{confidence_level*100}%",
                "timeframe": timeframe,
                "method": "Historical Simulation",
                "data_points": len(portfolio_returns),
                "period_analyzed": period,
                "portfolio_holdings": {
                    holding: {
                        "weight": f"{float(portfolio.get(holding, 0))*100:.1f}%",
                        "ticker": holdings_tickers.get(holding, "N/A")
                    }
                    for holding in portfolio.keys()
                },
                "var_percentage": {
                    "1_day": f"{var_1day_pct*100:.2f}%",
                    "1_week": f"{var_1week_pct*100:.2f}%",
                    "1_month": f"{var_1month_pct*100:.2f}%"
                },
                "portfolio_statistics": {
                    "mean_daily_return": f"{mean_return*100:.4f}%",
                    "volatility": f"{std_return*100:.2f}%",
                    "worst_day": f"{min_return*100:.2f}%",
                    "best_day": f"{max_return*100:.2f}%"
                },
                "expected_shortfall": f"{expected_shortfall*100:.2f}%",
                "interpretation": f"With {confidence_level*100}% confidence, the portfolio is expected to lose no more than {var_1day_pct*100:.2f}% in a single day"
            }
            
            # Add absolute VaR if portfolio value provided
            if portfolio_value:
                var_data["portfolio_value"] = f"${portfolio_value:,.2f}"
                var_data["var_absolute"] = {
                    "1_day": f"${var_1day_abs:,.2f}",
                    "1_week": f"${var_1week_abs:,.2f}",
                    "1_month": f"${var_1month_abs:,.2f}"
                }
                var_data["interpretation"] += f" (${var_1day_abs:,.2f} for a ${portfolio_value:,.2f} portfolio)"
            
            return [TextContent(type="text", text=json.dumps(var_data, indent=2))]
            
        except Exception as e:
            log(f"Error calculating VaR: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Failed to calculate VaR: {str(e)}",
                    "portfolio": portfolio,
                    "confidence_level": confidence_level,
                    "timeframe": timeframe
                })
            )]
    
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