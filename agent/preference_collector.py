"""
Preference Collection Dialog Module.

Collects and validates user investment preferences dynamically when missing.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.conversation_manager import (
    AVAILABLE_SECTORS,
    INVESTMENT_GOALS,
    RISK_TOLERANCE_LEVELS,
    UserPreferences,
)


@dataclass
class PreferenceParseResult:
    """Result from parsing a natural-language preference response."""

    goals: List[str]
    sectors: List[str]
    risk_tolerance: Optional[str]
    confidence: str


class PreferenceCollector:
    """Dynamically collects missing user preferences over multiple turns."""

    def __init__(
        self, llm_provider: str = "groq", model: str = "llama-3.3-70b-versatile"
    ):
        self.llm_provider = llm_provider
        self.model = model
        self._groq_client = None

        self._question_map = {
            "risk_tolerance": "What's your risk tolerance? (low/medium/high)",
            "goals": "What are your investment goals? (growth, income, esg, value, defensive, diversified)",
            "sectors": "Which sectors interest you? (technology, healthcare, financial-services, energy, etc.)",
        }

        self._sector_aliases = {
            "tech": "technology",
            "technology": "technology",
            "health": "healthcare",
            "healthcare": "healthcare",
            "finance": "financial-services",
            "financial": "financial-services",
            "financial services": "financial-services",
            "energy": "energy",
            "consumer discretionary": "consumer-discretionary",
            "consumer staples": "consumer-staples",
            "utilities": "utilities",
            "real estate": "real-estate",
            "industrials": "industrials",
            "materials": "materials",
            "communication services": "communication-services",
        }

    def check_required_preferences(
        self,
        preferences: UserPreferences,
        required_fields: Optional[List[str]] = None,
    ) -> List[str]:
        """Return required fields that are still missing."""
        required = required_fields or ["goals", "sectors", "risk_tolerance"]
        missing: List[str] = []

        if "goals" in required and not preferences.goals:
            missing.append("goals")
        if "sectors" in required and not preferences.sectors:
            missing.append("sectors")
        if "risk_tolerance" in required and not preferences.risk_tolerance:
            missing.append("risk_tolerance")

        return missing

    def generate_preference_question(self, missing_fields: List[str]) -> str:
        """Generate a natural follow-up question for missing preference fields."""
        if not missing_fields:
            return "Thanks — I have everything I need."

        primary = missing_fields[0]
        return self._question_map.get(
            primary, "Could you share a bit more about your investment preferences?"
        )

    def parse_preference_response(self, user_input: str) -> PreferenceParseResult:
        """
        Parse user natural-language preference input.

        Attempts LLM parsing first when configured and available, then falls back
        to deterministic rule-based parsing for reliability.
        """
        llm_result = self._parse_with_llm(user_input)
        if llm_result is not None:
            return llm_result

        return self._parse_with_rules(user_input)

    def validate_preferences(self, preferences: UserPreferences) -> List[str]:
        """Validate preferences against allowed values."""
        return preferences.validate()

    def collect_preferences_turn(
        self,
        preferences: UserPreferences,
        user_input: str,
        required_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Process one turn of preference collection.

        Returns a state payload including updated preferences, remaining missing
        fields, completion status, and optional next question.
        """
        parsed = self.parse_preference_response(user_input)
        updated = self.update_preferences(preferences, parsed)

        validation_errors = self.validate_preferences(updated)
        missing_fields = self.check_required_preferences(updated, required_fields)
        is_complete = len(missing_fields) == 0 and len(validation_errors) == 0

        return {
            "updated_preferences": updated,
            "parsed_update": {
                "goals": parsed.goals,
                "sectors": parsed.sectors,
                "risk_tolerance": parsed.risk_tolerance,
                "confidence": parsed.confidence,
            },
            "missing_fields": missing_fields,
            "validation_errors": validation_errors,
            "is_complete": is_complete,
            "next_question": (
                None
                if is_complete
                else self.generate_preference_question(missing_fields)
            ),
        }

    def update_preferences(
        self,
        current: UserPreferences,
        parsed: PreferenceParseResult,
    ) -> UserPreferences:
        """Merge parsed preference values into current preferences."""
        goals = list(dict.fromkeys(current.goals + parsed.goals))
        sectors = list(dict.fromkeys(current.sectors + parsed.sectors))
        risk_tolerance = parsed.risk_tolerance or current.risk_tolerance

        return UserPreferences(
            goals=goals, sectors=sectors, risk_tolerance=risk_tolerance
        )

    def _parse_with_llm(self, user_input: str) -> Optional[PreferenceParseResult]:
        """LLM parser compatible with existing chatbot parsing behavior."""
        try:
            prompt = f"""Extract investment preferences from this user response.

AVAILABLE GOALS: {', '.join(INVESTMENT_GOALS)}
AVAILABLE SECTORS: {', '.join(AVAILABLE_SECTORS)}
RISK TOLERANCE LEVELS: {', '.join(RISK_TOLERANCE_LEVELS)}

User response: \"{user_input}\"

Return ONLY JSON:
{{
  \"goals\": [list of valid goal keys],
  \"sectors\": [list of valid sector keys],
  \"risk_tolerance\": \"low\" | \"medium\" | \"high\" | null,
  \"confidence\": \"high\" | \"medium\" | \"low\"
}}
"""

            from agent.llm_utils import call_llm
            content = call_llm(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=250,
            )

            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1]).strip()
            if content.startswith("json"):
                content = content[4:].strip()

            parsed = json.loads(content)
            goals = [g for g in parsed.get("goals", []) if g in INVESTMENT_GOALS]
            sectors = [s for s in parsed.get("sectors", []) if s in AVAILABLE_SECTORS]
            risk_tolerance = parsed.get("risk_tolerance")
            if risk_tolerance not in RISK_TOLERANCE_LEVELS:
                risk_tolerance = None

            confidence = parsed.get("confidence", "medium")
            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"

            return PreferenceParseResult(
                goals=goals,
                sectors=sectors,
                risk_tolerance=risk_tolerance,
                confidence=confidence,
            )
        except Exception:
            return None

    def _parse_with_rules(self, user_input: str) -> PreferenceParseResult:
        """Deterministic parser used when LLM parsing is unavailable."""
        text = user_input.lower()

        goals: List[str] = []
        sectors: List[str] = []
        risk_tolerance: Optional[str] = None

        # Goals (direct mentions)
        for goal in INVESTMENT_GOALS:
            if re.search(rf"\b{re.escape(goal)}\b", text):
                goals.append(goal)

        # Goal synonyms
        if "dividend" in text and "income" not in goals:
            goals.append("income")
        if "safe" in text and "defensive" not in goals:
            goals.append("defensive")

        # Sectors (exact + aliases)
        for sector in AVAILABLE_SECTORS:
            if re.search(rf"\b{re.escape(sector)}\b", text):
                sectors.append(sector)

        for alias, normalized in self._sector_aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", text):
                sectors.append(normalized)

        sectors = list(dict.fromkeys(sectors))

        # Risk tolerance
        if re.search(r"\b(low|conservative|safe)\b", text):
            risk_tolerance = "low"
        elif re.search(r"\b(medium|moderate|balanced)\b", text):
            risk_tolerance = "medium"
        elif re.search(r"\b(high|aggressive|risky)\b", text):
            risk_tolerance = "high"

        confidence = "low"
        signal_count = (
            int(bool(goals)) + int(bool(sectors)) + int(risk_tolerance is not None)
        )
        if signal_count >= 2:
            confidence = "high"
        elif signal_count == 1:
            confidence = "medium"

        return PreferenceParseResult(
            goals=list(dict.fromkeys(goals)),
            sectors=sectors,
            risk_tolerance=risk_tolerance,
            confidence=confidence,
        )
