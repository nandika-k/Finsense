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

        lines = [f"Top stock ideas for {goal} in {sector}:"]
        for idx, stock in enumerate(stocks[:5], start=1):
            ticker = stock.get("ticker", "N/A")
            name = stock.get("name", "")
            perf = stock.get("performance_1m", "N/A")
            volatility = stock.get("volatility", "N/A")
            lines.append(
                f"{idx}. {ticker} ({name}) — 1M: {perf}, Volatility: {volatility}"
            )

        return "\n".join(lines)

    def format_risk_analysis(
        self,
        volatility_data: Optional[Dict[str, Any]] = None,
        structural_risks_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format quantitative volatility and structural risk categories."""
        if not volatility_data and not structural_risks_data:
            return self.templates["empty"]

        lines: List[str] = ["Risk analysis summary:"]

        if volatility_data:
            if volatility_data.get("error"):
                lines.append(
                    f"- Volatility metrics unavailable: {volatility_data.get('error')}"
                )
            else:
                sector = volatility_data.get("sector", "sector")
                annualized = volatility_data.get("annualized_volatility", "N/A")
                var_95 = volatility_data.get("var_95", "N/A")
                max_drawdown = volatility_data.get("max_drawdown", "N/A")
                lines.append(
                    f"- {sector}: annualized volatility {annualized}, VaR(95%) {var_95}, max drawdown {max_drawdown}"
                )

        if structural_risks_data:
            if structural_risks_data.get("error"):
                lines.append(
                    f"- Structural risk view unavailable: {structural_risks_data.get('error')}"
                )
            else:
                categories = structural_risks_data.get("risk_categories", [])
                if isinstance(categories, list) and categories:
                    category_names = [
                        c.get("category", "Unknown")
                        for c in categories[:4]
                        if isinstance(c, dict)
                    ]
                    lines.append(
                        f"- Structural risk categories: {', '.join(category_names)}"
                    )
                summary = structural_risks_data.get("summary")
                if summary:
                    lines.append(f"- {summary}")

        return "\n".join(lines)

    def format_news_summary(
        self,
        headlines_data: Optional[Dict[str, Any]] = None,
        risk_themes_data: Optional[Dict[str, Any]] = None,
        include_citations: bool = True,
    ) -> str:
        """Format headlines, risk themes, and optional article citations."""
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
                    f"Recent news for {sector} ({timeframe}): {count} headlines analyzed."
                )

                headlines = headlines_data.get("headlines", [])
                for item in headlines[:3]:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title", "Untitled")
                    sentiment = item.get("sentiment", "neutral")
                    lines.append(f"- {title} [{sentiment}]")

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
        """Build a compact citation block from risk themes article sources."""
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
                source = (
                    article.get("source") or article.get("url") or "Source unavailable"
                )
                citations.append(f"- {risk_name}: {title} ({source})")

        if not citations:
            return ""

        return "Citations:\n" + "\n".join(citations)
