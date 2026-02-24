"""
Response Formatter Module.

Formats MCP tool outputs into natural, conversational responses for chat mode.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


class ResponseFormatter:
    """Formats tool results into user-facing conversational responses."""

    def __init__(
        self, llm_provider: str = "groq", model: str = "llama-3.3-70b-versatile"
    ):
        self.llm_provider = llm_provider
        self.model = model
        self._groq_client = None

        self.templates = {
            "error": "I hit an issue while processing that request: {message}",
            "clarification": "Could you clarify: {message}",
            "empty": "I don't have enough data yet to answer that. Could you share a bit more detail?",
        }

    def format_market_overview(self, market_data: Dict[str, Any]) -> str:
        """Format market indices into a concise direct answer."""
        if not market_data:
            return self.templates["empty"]

        index_order = ["SPX", "DJI", "IXIC", "RUT"]
        lines = ["Here’s a quick market snapshot:"]

        for index in index_order:
            data = market_data.get(index)
            if not isinstance(data, dict):
                continue
            value = data.get("value", "N/A")
            change = data.get("change", "N/A")
            lines.append(f"- {index}: {value} ({change})")

        if len(lines) == 1:
            return self.templates["empty"]

        return "\n".join(lines)

    def format_sector_analysis(
        self,
        sector_summary: Dict[str, Any],
        volatility_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format sector performance and volatility into structured analysis."""
        if not sector_summary:
            return self.templates["empty"]

        if sector_summary.get("error"):
            return self.format_error_message(sector_summary["error"])

        sector_name = sector_summary.get("sector", "This sector")
        perf_1m = sector_summary.get("performance_1m", "N/A")
        perf_3m = sector_summary.get("performance_3m", "N/A")
        perf_1y = sector_summary.get("performance_1y", "N/A")

        lines = [
            f"{sector_name} sector overview:",
            f"- Performance: 1M {perf_1m}, 3M {perf_3m}, 1Y {perf_1y}",
        ]

        top_performers = sector_summary.get("top_performers", [])
        if isinstance(top_performers, list) and top_performers:
            tickers = [
                item.get("ticker")
                for item in top_performers
                if isinstance(item, dict) and item.get("ticker")
            ]
            if tickers:
                lines.append(f"- Notable names: {', '.join(tickers[:5])}")

        if volatility_data:
            if volatility_data.get("error"):
                lines.append(
                    f"- Volatility: unavailable ({volatility_data.get('error')})"
                )
            else:
                annualized = volatility_data.get("annualized_volatility", "N/A")
                drawdown = volatility_data.get("max_drawdown", "N/A")
                relative = volatility_data.get("relative_to_market", "N/A")
                lines.append(
                    f"- Risk profile: annualized volatility {annualized}, max drawdown {drawdown}, relative to market {relative}"
                )

        return "\n".join(lines)
    def format_sector_comparison(self, comparison_data: Dict[str, Any]) -> str:
        """Format sector comparison results matching full report style."""
        if not comparison_data:
            return self.templates["empty"]

        if comparison_data.get("error"):
            return self.format_error_message(comparison_data["error"])

        sector1 = comparison_data.get("sector1", "Sector 1").upper()
        sector2 = comparison_data.get("sector2", "Sector 2").upper()
        timeframe = comparison_data.get("timeframe", "1 month")

        lines = [f"**💼 Sector Comparison: {sector1} vs {sector2}** ({timeframe})", ""]

        # Volatility comparison
        vol_comp = comparison_data.get("volatility_comparison", {})
        if vol_comp:
            lines.append("**Volatility:**")
            lines.append(f"- {sector1}: {vol_comp.get('tech', vol_comp.get(sector1.lower(), 'N/A'))}")
            lines.append(f"- {sector2}: {vol_comp.get('healthcare', vol_comp.get(sector2.lower(), 'N/A'))}")
            lower = vol_comp.get("lower_volatility", "")
            if lower:
                lines.append(f"- ✅ Lower volatility: **{lower.upper()}**")
            lines.append("")

        # Max drawdown
        dd_comp = comparison_data.get("max_drawdown", {})
        if dd_comp:
            lines.append("**Max Drawdown:**")
            lines.append(f"- {sector1}: {dd_comp.get('tech', dd_comp.get(sector1.lower(), 'N/A'))}")
            lines.append(f"- {sector2}: {dd_comp.get('healthcare', dd_comp.get(sector2.lower(), 'N/A'))}")
            lower = dd_comp.get("lower_drawdown", "")
            if lower:
                lines.append(f"- ✅ Smaller drawdown: **{lower.upper()}**")
            lines.append("")

        # Total return
        ret_comp = comparison_data.get("total_return", {})
        if ret_comp:
            lines.append("**Total Return:**")
            lines.append(f"- {sector1}: {ret_comp.get('tech', ret_comp.get(sector1.lower(), 'N/A'))}")
            lines.append(f"- {sector2}: {ret_comp.get('healthcare', ret_comp.get(sector2.lower(), 'N/A'))}")
            higher = ret_comp.get("higher_return", "")
            if higher:
                lines.append(f"- ✅ Higher return: **{higher.upper()}**")
            lines.append("")

        # Sharpe ratio
        sharpe_comp = comparison_data.get("sharpe_ratio", {})
        if sharpe_comp:
            lines.append("**Sharpe Ratio (Risk-Adjusted Return):**")
            lines.append(f"- {sector1}: {sharpe_comp.get('tech', sharpe_comp.get(sector1.lower(), 'N/A'))}")
            lines.append(f"- {sector2}: {sharpe_comp.get('healthcare', sharpe_comp.get(sector2.lower(), 'N/A'))}")
            higher = sharpe_comp.get("higher_sharpe", "")
            if higher:
                lines.append(f"- ✅ Better risk-adjusted: **{higher.upper()}**")
            lines.append("")

        # Beta
        beta_comp = comparison_data.get("beta", {})
        if beta_comp:
            lines.append("**Beta (Market Sensitivity):**")
            lines.append(f"- {sector1}: {beta_comp.get('tech', beta_comp.get(sector1.lower(), 'N/A'))}")
            lines.append(f"- {sector2}: {beta_comp.get('healthcare', beta_comp.get(sector2.lower(), 'N/A'))}")
            lower = beta_comp.get("lower_beta", "")
            if lower:
                lines.append(f"- ✅ Lower market sensitivity: **{lower.upper()}**")
            lines.append("")

        # Recommendation
        recommendation = comparison_data.get("recommendation", "")
        if recommendation:
            lines.append(f"**📊 Summary:** {recommendation}")

        return "\n".join(lines)
    def format_stock_recommendations(self, recommendations_data: Dict[str, Any]) -> str:
        """Format ranked stock recommendations with concise rationale fields."""
        if not recommendations_data:
            return self.templates["empty"]

        if recommendations_data.get("error"):
            return self.format_error_message(recommendations_data["error"])

        goal = recommendations_data.get("goal", "your goal")
        sector = recommendations_data.get("sector", "selected sector")
        stocks = recommendations_data.get("stocks", [])

        if not stocks:
            return (
                f"I don’t have stock recommendations for {sector} ({goal}) right now."
            )

        lines = [f"**📈 Stock Recommendations for {goal.upper()} in {sector.upper()}**", ""]
        for idx, stock in enumerate(stocks[:5], start=1):
            ticker = stock.get("ticker", "N/A")
            name = stock.get("name", "")
            price = stock.get("price", "N/A")
            perf = stock.get("performance_1m", "N/A")
            volatility = stock.get("volatility", "N/A")
            score = stock.get("score", "")
            dividend = stock.get("dividend_yield", "N/A")
            esg = stock.get("esg_score", "N/A")
            reasons = stock.get("reasons", [])

            lines.append(f"**{idx}. {ticker}** - {name}")
            lines.append(f"   - Price: ${price}")
            lines.append(f"   - 1M Performance: {perf}")
            lines.append(f"   - Volatility: {volatility}")
            if dividend and dividend != "N/A":
                lines.append(f"   - Dividend Yield: {dividend}")
            if esg and esg != "N/A":
                lines.append(f"   - ESG Score: {esg}")
            if score:
                lines.append(f"   - Score: {score}")
            if reasons:
                lines.append(f"   - Why: {', '.join(reasons[:2])}")
            lines.append("")

        return "\n".join(lines)

    def format_multi_sector_recommendations(
        self, stocks: List[Dict[str, Any]], goal: str
    ) -> str:
        """Format stock recommendations from multiple sectors."""
        if not stocks:
            return self.templates["empty"]

        lines = [f"**📈 Top Stocks Across Sectors** ({goal.upper()} focus)", ""]
        
        for idx, stock in enumerate(stocks[:10], start=1):
            ticker = stock.get("ticker", "N/A")
            name = stock.get("name", "")
            price = stock.get("price", "N/A")
            perf = stock.get("performance_1m", "N/A")
            volatility = stock.get("volatility", "N/A")
            sector = stock.get("sector", "").upper()
            dividend = stock.get("dividend_yield", "N/A")

            lines.append(f"**{idx}. {ticker}** - {name}")
            lines.append(f"   - Sector: {sector}")
            lines.append(f"   - Price: ${price}")
            lines.append(f"   - 1M Performance: {perf}")
            lines.append(f"   - Volatility: {volatility}")
            if dividend and dividend != "N/A" and dividend != 0:
                lines.append(f"   - Dividend Yield: {dividend}")
            lines.append("")

        return "\n".join(lines)

    def format_risk_analysis(
        self,
        volatility_data: Optional[Dict[str, Any]] = None,
        structural_risks_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format quantitative volatility and structural risk categories matching full report style."""
        if not volatility_data and not structural_risks_data:
            return self.templates["empty"]

        lines: List[str] = ["**🎯 Risk Analysis**", ""]

        if volatility_data:
            if volatility_data.get("error"):
                lines.append(
                    f"⚠️ Volatility metrics unavailable: {volatility_data.get('error')}"
                )
            else:
                sector = volatility_data.get("sector", "sector")
                annualized = volatility_data.get("annualized_volatility", "N/A")
                max_drawdown = volatility_data.get("max_drawdown", "N/A")
                trend = volatility_data.get("trend", "N/A")
                percentile = volatility_data.get("percentile", "N/A")
                relative = volatility_data.get("relative_to_market", "N/A")
                
                lines.append(f"**{sector.upper()} Risk Profile:**")
                lines.append(f"- Volatility: {annualized}")
                lines.append(f"- Max Drawdown: {max_drawdown}")
                if trend and trend != "N/A":
                    lines.append(f"- Trend: {trend}")
                if percentile and percentile != "N/A":
                    lines.append(f"- Risk Level: {percentile}")
                if relative and relative != "N/A":
                    lines.append(f"- Relative to Market: {relative}")
                lines.append("")

        if structural_risks_data:
            if structural_risks_data.get("error"):
                lines.append(
                    f"⚠️ Structural risk view unavailable: {structural_risks_data.get('error')}"
                )
            else:
                risks = structural_risks_data.get("risks", [])
                categories = structural_risks_data.get("risk_categories", [])
                
                if risks or categories:
                    lines.append("**Risk Themes:**")
                    
                    # Show individual risks with categories
                    if isinstance(risks, list) and risks:
                        for risk_item in risks[:5]:
                            if isinstance(risk_item, dict):
                                risk_text = risk_item.get("risk", "Unknown")
                                category = risk_item.get("category", "Uncategorized")
                                lines.append(f"- **[{category.upper()}]** {risk_text}")
                    elif isinstance(categories, list) and categories:
                        for cat in categories[:4]:
                            if isinstance(cat, dict):
                                cat_name = cat.get("category", "Unknown")
                                cat_risks = cat.get("risks", [])
                                if cat_risks:
                                    lines.append(f"- **[{cat_name.upper()}]** {', '.join(cat_risks[:2])}")
                                else:
                                    lines.append(f"- **[{cat_name.upper()}]**")
                    
                    lines.append("")
                
                summary = structural_risks_data.get("summary")
                if summary:
                    lines.append(f"*{summary}*")

        return "\n".join(lines)

    def format_news_summary(
        self,
        headlines_data: Optional[Dict[str, Any]] = None,
        risk_themes_data: Optional[Dict[str, Any]] = None,
        include_citations: bool = True,
    ) -> str:
        """Format headlines, risk themes, and optional article citations."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"[DEBUG format_news_summary] headlines_data keys: {headlines_data.keys() if headlines_data else 'None'}")
        logger.info(f"[DEBUG format_news_summary] risk_themes_data keys: {risk_themes_data.keys() if risk_themes_data else 'None'}")
        
        if not headlines_data and not risk_themes_data:
            return self.templates["empty"]

        lines: List[str] = []

        if headlines_data:
            if headlines_data.get("error"):
                lines.append(self.format_error_message(headlines_data["error"]))
            else:
                sector = headlines_data.get("sector", "sector")
                timeframe = headlines_data.get("timeframe", "recent period")
                count = headlines_data.get("headline_count", 0)
                lines.append(
                    f"**Recent News for {sector.upper()}** ({timeframe}): {count} headlines analyzed."
                )
                lines.append("")

                headlines = headlines_data.get("headlines", [])
                logger.info(f"[DEBUG format_news_summary] Number of headlines: {len(headlines)}")
                if headlines:
                    logger.info(f"[DEBUG format_news_summary] First headline keys: {headlines[0].keys() if headlines[0] else 'empty'}")
                    logger.info(f"[DEBUG format_news_summary] First headline URL: {headlines[0].get('url', 'NO URL')}")
                
                for item in headlines[:5]:  # Show more headlines
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title", "Untitled")
                    url = item.get("url", "")
                    sentiment = item.get("sentiment", "neutral")
                    source = item.get("source", "")
                    
                    # Format with clickable link if URL available
                    if url and url.startswith("http"):
                        lines.append(f"- [{title}]({url}) [{sentiment}]")
                    else:
                        source_info = f" ({source})" if source else ""
                        lines.append(f"- {title}{source_info} [{sentiment}]")
        
        logger.info(f"[DEBUG format_news_summary] Final lines count: {len(lines)}")

        if risk_themes_data:
            if risk_themes_data.get("error"):
                lines.append(self.format_error_message(risk_themes_data["error"]))
            else:
                summary = risk_themes_data.get("summary")
                if summary:
                    lines.append(f"Risk themes: {summary}")

                risks = risk_themes_data.get("identified_risks", [])
                for risk in risks[:3]:
                    if not isinstance(risk, dict):
                        continue
                    risk_name = risk.get("risk", "Unspecified risk")
                    category = risk.get("category", "Uncategorized")
                    article_count = risk.get("article_count", 0)
                    lines.append(
                        f"- {risk_name} ({category}) — referenced in {article_count} article(s)"
                    )

                if include_citations:
                    citation_block = self._format_news_citations(risk_themes_data)
                    if citation_block:
                        lines.append(citation_block)

        if not lines:
            return self.templates["empty"]

        return "\n".join(lines)

    def format_error_message(self, message: str) -> str:
        """Format user-friendly error message."""
        return self.templates["error"].format(message=message)

    def format_clarification_prompt(self, message: str) -> str:
        """Format clarification prompt."""
        return self.templates["clarification"].format(message=message)

    def generate_natural_language(
        self,
        response_type: str,
        payload: Dict[str, Any],
    ) -> Optional[str]:
        """Optional LLM polish for complex responses; returns None if unavailable."""
        try:
            prompt = (
                "Rewrite the following structured financial response into concise, clear, "
                "natural language. Use only the provided facts and do not add new claims.\n\n"
                f"Response type: {response_type}\n"
                f"Payload:\n{json.dumps(payload, indent=2)}"
            )

            from agent.llm_utils import call_llm
            result = call_llm(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=220,
            )
            return result
        except Exception:
            return None

    def _format_news_citations(self, risk_themes_data: Dict[str, Any]) -> str:
        """Build a compact citation block from risk themes article sources with real URLs."""
        risks = risk_themes_data.get("identified_risks", [])
        citations: List[str] = []

        for risk in risks[:3]:
            if not isinstance(risk, dict):
                continue
            risk_name = risk.get("risk", "Risk")
            articles = risk.get("articles", [])
            for article in articles[:2]:
                if not isinstance(article, dict):
                    continue
                title = article.get("title", "Untitled")
                url = article.get("url", "")
                source = article.get("source", "")
                
                # Format with clickable link if URL available
                if url and url.startswith("http"):
                    citations.append(f"- {risk_name}: [{title}]({url})")
                else:
                    source_info = f" ({source})" if source else ""
                    citations.append(f"- {risk_name}: {title}{source_info}")

        if not citations:
            return ""

        return "**Sources:**\n" + "\n".join(citations)
