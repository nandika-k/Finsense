"""
Clarification and disambiguation module.

Handles ambiguous or incomplete user requests by generating targeted
clarification prompts, suggesting spelling corrections, and identifying
queries outside product scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Dict, List, Optional

from agent.conversation_manager import AVAILABLE_SECTORS


@dataclass
class ClarificationDecision:
    """Structured result from ambiguity/disambiguation checks."""

    needs_clarification: bool
    clarification_type: Optional[str] = None
    message: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    missing_params: List[str] = field(default_factory=list)
    corrections: Dict[str, str] = field(default_factory=dict)


class ClarificationHandler:
    """Detects ambiguity and generates clarification workflows."""

    def __init__(self):
        self._ambiguous_sector_terms: Dict[str, List[str]] = {
            "tech": ["technology", "communication-services"],
            "consumer": ["consumer-discretionary", "consumer-staples"],
            "financial": ["financial-services"],
        }

        self._sector_aliases: Dict[str, str] = {
            "technology": "technology",
            "tech": "technology",
            "health": "healthcare",
            "healthcare": "healthcare",
            "financial": "financial-services",
            "finance": "financial-services",
            "financial services": "financial-services",
            "energy": "energy",
            "consumer": "consumer",
            "consumer discretionary": "consumer-discretionary",
            "consumer staples": "consumer-staples",
            "utilities": "utilities",
            "real estate": "real-estate",
            "real-estate": "real-estate",
            "industrials": "industrials",
            "materials": "materials",
            "communication services": "communication-services",
            "communications": "communication-services",
        }

        self._known_tickers = {
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "NVDA",
            "TSLA",
            "META",
            "JPM",
            "XOM",
            "UNH",
        }

        self._clarification_templates = {
            "ambiguous_sector": "I found multiple sector matches for '{term}': {options}. Which one should I use?",
            "missing_params": "To help with that, please share {missing}.",
            "spelling_correction": "Did you mean {suggestions}?",
            "out_of_scope": (
                "I can provide market data, sector analysis, and risk context, but I can't give personal timing or trade advice. "
                "If you'd like, I can share objective indicators to help your decision."
            ),
        }

    def detect_ambiguity(self, query: str) -> ClarificationDecision:
        """Detect if query needs clarification and return guidance payload."""
        if not query or not query.strip():
            return ClarificationDecision(
                needs_clarification=True,
                clarification_type="missing_params",
                missing_params=["your request details"],
                message=self._clarification_templates["missing_params"].format(
                    missing="what you'd like to analyze (sector or ticker)"
                ),
            )

        lowered = query.lower().strip()

        if self.is_out_of_scope(lowered):
            return ClarificationDecision(
                needs_clarification=True,
                clarification_type="out_of_scope",
                message=self._clarification_templates["out_of_scope"],
            )

        spelling_corrections = self.suggest_spelling_corrections(query)
        if spelling_corrections:
            suggestion_text = ", ".join(
                [f"'{original}' -> '{suggested}'" for original, suggested in spelling_corrections.items()]
            )
            return ClarificationDecision(
                needs_clarification=True,
                clarification_type="spelling_correction",
                corrections=spelling_corrections,
                message=self._clarification_templates["spelling_correction"].format(
                    suggestions=suggestion_text
                ),
            )

        ambiguous = self._find_ambiguous_sector(lowered)
        if ambiguous is not None:
            term, candidates = ambiguous
            return ClarificationDecision(
                needs_clarification=True,
                clarification_type="ambiguous_sector",
                candidates=candidates,
                message=self._clarification_templates["ambiguous_sector"].format(
                    term=term,
                    options=", ".join(candidates),
                ),
            )

        missing = self._detect_missing_critical_params(lowered)
        if missing:
            missing_text = ", ".join(missing)
            return ClarificationDecision(
                needs_clarification=True,
                clarification_type="missing_params",
                missing_params=missing,
                message=self._clarification_templates["missing_params"].format(missing=missing_text),
            )

        return ClarificationDecision(needs_clarification=False)

    def suggest_spelling_corrections(self, query: str) -> Dict[str, str]:
        """Suggest sector and ticker spelling corrections from noisy input."""
        corrections: Dict[str, str] = {}
        lowered = query.lower()

        sector_candidates = set(AVAILABLE_SECTORS)
        sector_candidates.update(self._sector_aliases.keys())

        for token in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", lowered):
            if token in sector_candidates:
                continue
            close = get_close_matches(token, list(sector_candidates), n=1, cutoff=0.83)
            if close:
                canonical = self._sector_aliases.get(close[0], close[0])
                corrections[token] = canonical

        for token in re.findall(r"\b[a-zA-Z]{2,5}\b", query):
            token_upper = token.upper()
            if token_upper in self._known_tickers:
                continue
            if token.lower() in {"stock", "stocks", "sector", "sectors", "show", "about", "with"}:
                continue
            close = get_close_matches(token_upper, list(self._known_tickers), n=1, cutoff=0.7)
            if close:
                corrections[token] = close[0]

        return corrections

    def parse_clarification_response(
        self,
        user_response: str,
        pending_clarification: ClarificationDecision,
    ) -> Dict[str, object]:
        """Parse user answer to a prior clarification prompt."""
        response = (user_response or "").strip().lower()
        if not pending_clarification.needs_clarification:
            return {"resolved": True, "entities": {}}

        if pending_clarification.clarification_type == "ambiguous_sector":
            sector = self._extract_sector(response)
            if sector:
                return {"resolved": True, "entities": {"sector": sector}}
            return {
                "resolved": False,
                "follow_up": "Please pick one sector from the options so I can continue.",
            }

        if pending_clarification.clarification_type == "missing_params":
            sector = self._extract_sector(response)
            ticker = self._extract_ticker(response)
            entities: Dict[str, str] = {}
            if sector:
                entities["sector"] = sector
            if ticker:
                entities["ticker"] = ticker
            return {
                "resolved": bool(entities),
                "entities": entities,
                "follow_up": None if entities else "Please provide a sector or ticker to proceed.",
            }

        if pending_clarification.clarification_type == "spelling_correction":
            negation = bool(re.search(r"\b(no|nope|not|wrong|incorrect)\b", response))
            affirmative = not negation and bool(re.search(r"\b(yes|yep|correct|right|sure)\b", response))
            if affirmative and pending_clarification.corrections:
                first_fix = next(iter(pending_clarification.corrections.values()))
                return {
                    "resolved": True,
                    "entities": {
                        "corrected_value": first_fix,
                    },
                }
            extracted_sector = self._extract_sector(response)
            return {
                "resolved": bool(extracted_sector),
                "entities": {"sector": extracted_sector} if extracted_sector else {},
                "follow_up": None if extracted_sector else "Please confirm the corrected sector/ticker.",
            }

        if pending_clarification.clarification_type == "out_of_scope":
            return {
                "resolved": True,
                "entities": {},
                "next_action": "offer_data_driven_alternative",
            }

        return {"resolved": False, "entities": {}}

    def is_out_of_scope(self, query: str) -> bool:
        """Detect requests for personal trade timing/advice outside allowed scope."""
        timing_advice_patterns = [
            # Timing and trade decisions
            r"\bwhen should i buy\b",
            r"\bshould i buy\b",
            r"\bshould i sell\b",
            r"\bshould i invest\b",
            r"\bshould i hold\b",
            r"\bexact entry\b",
            r"\bexact exit\b",
            # Price predictions
            r"\bwill\b.{0,40}\b(go up|go down|rise|fall|crash|moon)\b",
            r"\b(predict|forecast)\b.{0,30}\b(price|stock|market)\b",
            r"\bguaranteed return\b",
            r"\bguaranteed profit\b",
            # Personal financial advisory
            r"\bfinancial (plan|planning|advisor|advice)\b",
            r"\btax (advice|planning|tip)\b",
            r"\bretirement plan(ning)?\b",
            r"\bget rich\b",
        ]
        return any(re.search(pattern, query) for pattern in timing_advice_patterns)

    def _find_ambiguous_sector(self, lowered_query: str) -> Optional[tuple[str, List[str]]]:
        """Return ambiguous term and candidates if query uses broad sector language."""
        for term, candidates in self._ambiguous_sector_terms.items():
            if re.search(rf"\b{re.escape(term)}\b", lowered_query):
                if len(candidates) > 1:
                    return term, candidates
        return None

    def _detect_missing_critical_params(self, lowered_query: str) -> List[str]:
        """Detect missing minimum parameters for stock-centric requests."""
        has_stock_request = bool(re.search(r"\b(stock|stocks|equities|shares)\b", lowered_query))
        has_sector = self._extract_sector(lowered_query) is not None
        has_ticker = self._extract_ticker(lowered_query) is not None

        missing: List[str] = []
        if has_stock_request and not has_sector and not has_ticker:
            missing.append("a sector or ticker")
        return missing

    def _extract_sector(self, text: str) -> Optional[str]:
        """Extract normalized sector from user text."""
        for sector in AVAILABLE_SECTORS:
            if re.search(rf"\b{re.escape(sector)}\b", text):
                return sector

        for alias, normalized in self._sector_aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", text):
                return normalized if normalized in AVAILABLE_SECTORS else None

        return None

    def _extract_ticker(self, text: str) -> Optional[str]:
        """Extract known ticker from text."""
        for token in re.findall(r"\b[A-Za-z]{2,5}\b", text):
            symbol = token.upper()
            if symbol in self._known_tickers:
                return symbol
        return None
