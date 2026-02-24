"""
Tool Routing & Selection Module.

Maps classified intents to MCP tool calls and builds validated arguments
from extracted entities and user preferences.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from agent.conversation_manager import UserPreferences
from agent.intent_classifier import IntentClassification, IntentType


@dataclass
class ToolCall:
    """Represents a single MCP tool invocation."""

    tool_name: str
    server: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    requires_preferences: bool = False


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "get_market_indices": {"server": "market", "required_args": []},
    "get_sector_summary": {"server": "market", "required_args": ["sector"]},
    "get_stock_price": {"server": "market", "required_args": ["ticker"]},
    "get_stock_recommendations": {
        "server": "market",
        "required_args": ["sector", "goal"],
    },
    "get_stock_details": {"server": "market", "required_args": ["ticker"]},
    "fetch_headlines": {
        "server": "news",
        "required_args": ["sector", "timeframe"],
    },
    "extract_risk_themes": {
        "server": "news",
        "required_args": ["sector", "timeframe"],
    },
    "identify_sector_risks": {
        "server": "news",
        "required_args": ["sector_or_ticker"],
    },
    "compute_sector_volatility": {
        "server": "risk",
        "required_args": ["sector", "timeframe"],
    },
    "compare_sectors": {
        "server": "risk",
        "required_args": ["sector1", "sector2", "timeframe"],
    },
    "compute_sector_correlations": {
        "server": "risk",
        "required_args": ["sectors", "timeframe"],
    },
    "calculate_var": {
        "server": "risk",
        "required_args": ["portfolio", "confidence_level", "timeframe"],
    },
    "conduct_research": {
        "server": "coordinator",
        "required_args": ["sectors", "risk_tolerance"],
    },
}


INTENT_TO_TOOLS_MAP: Dict[str, List[str]] = {
    "market_overview": ["get_market_indices"],
    "sector_recommendations": ["get_sector_summary"],
    "sector_info": ["get_sector_summary", "compute_sector_volatility"],
    "stock_details": ["get_stock_details", "get_stock_price"],
    "stock_recommendations": ["get_stock_recommendations"],
    "risk_analysis": ["compute_sector_volatility", "identify_sector_risks"],
    "news_query": ["fetch_headlines", "extract_risk_themes"],
    "full_research": ["conduct_research"],
    "compare": ["compare_sectors"],
    "calculate_risk": ["compute_sector_volatility"],
    "news_for_sector": ["fetch_headlines", "extract_risk_themes"],
    "portfolio_analysis": ["calculate_var"],
}


PREFERENCE_REQUIRED_TOOLS = {"conduct_research"}  # Stock recommendations use defaults if no preferences


class ToolRouter:
    """Routes intent classifications to executable and validated tool calls."""

    def __init__(self, default_timeframe: str = "1 month"):
        self.default_timeframe = default_timeframe

    def route_intent_to_tools(
        self,
        classification: IntentClassification,
        preferences: Optional[UserPreferences] = None,
    ) -> List[ToolCall]:
        """
        Build tool calls for a classified intent.

        Returns an empty list when no tools are needed for the intent.
        Raises ValueError when required preferences or required tool arguments
        are missing.
        """
        intent_key = self._intent_to_key(classification.intent_type)
        tool_names = INTENT_TO_TOOLS_MAP.get(intent_key, [])
        if not tool_names:
            return []

        tool_calls: List[ToolCall] = []
        for tool_name in tool_names:
            requires_preferences = tool_name in PREFERENCE_REQUIRED_TOOLS
            if requires_preferences:
                self._check_preference_requirement(tool_name, preferences)

            arguments = self._build_tool_arguments(
                tool_name, classification, preferences
            )
            tool_call = ToolCall(
                tool_name=tool_name,
                server=TOOL_REGISTRY[tool_name]["server"],
                arguments=arguments,
                requires_preferences=requires_preferences,
            )
            self.validate_tool_call(tool_call)
            tool_calls.append(tool_call)

        return tool_calls

    def validate_tool_call(self, tool_call: ToolCall) -> bool:
        """Validate required arguments for a tool call."""
        if tool_call.tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: {tool_call.tool_name}")

        required_args = TOOL_REGISTRY[tool_call.tool_name]["required_args"]
        for arg in required_args:
            if arg not in tool_call.arguments:
                raise ValueError(
                    f"Missing required argument '{arg}' for tool '{tool_call.tool_name}'"
                )

            value = tool_call.arguments[arg]
            if value is None or value == "" or value == []:
                raise ValueError(
                    f"Argument '{arg}' for tool '{tool_call.tool_name}' cannot be empty"
                )

        return True

    def _build_tool_arguments(
        self,
        tool_name: str,
        classification: IntentClassification,
        preferences: Optional[UserPreferences],
    ) -> Dict[str, Any]:
        entities = classification.extracted_entities
        timeframe = entities.timeframe or self.default_timeframe

        primary_ticker = entities.tickers[0] if entities.tickers else None
        primary_sector = entities.sectors[0] if entities.sectors else None
        primary_goal = entities.goals[0] if entities.goals else None

        pref_sector = (
            preferences.sectors[0] if preferences and preferences.sectors else None
        )
        pref_goal = preferences.goals[0] if preferences and preferences.goals else None

        if tool_name == "get_market_indices":
            return {}

        if tool_name == "get_sector_summary":
            return {"sector": primary_sector or pref_sector}

        if tool_name in {"get_stock_price", "get_stock_details"}:
            return {"ticker": primary_ticker}

        if tool_name == "get_stock_recommendations":
            # Use extracted sector/goal from query, fallback to preferences
            sector = primary_sector or pref_sector
            goal = primary_goal or pref_goal
            
            # If no sector specified, use "all" to trigger multi-sector fetch
            if not sector:
                sector = "all"
            
            # If no goal, default based on sector or use growth
            if not goal:
                if sector in {"utilities", "consumer-staples", "real-estate"}:
                    goal = "income"  # These sectors suit income investing
                else:
                    goal = "growth"  # Default to growth
            
            return {
                "sector": sector,
                "goal": goal,
            }

        if tool_name in {"fetch_headlines", "extract_risk_themes"}:
            return {
                "sector": primary_sector or pref_sector,
                "timeframe": timeframe,
            }

        if tool_name == "identify_sector_risks":
            return {"sector_or_ticker": primary_ticker or primary_sector or pref_sector}

        if tool_name == "compute_sector_volatility":
            return {
                "sector": primary_sector or pref_sector,
                "timeframe": timeframe,
            }

        if tool_name == "compare_sectors":
            comparison_items = entities.comparison_items or entities.sectors
            return {
                "sector1": comparison_items[0] if len(comparison_items) > 0 else None,
                "sector2": comparison_items[1] if len(comparison_items) > 1 else None,
                "timeframe": timeframe,
            }

        if tool_name == "compute_sector_correlations":
            sectors = entities.sectors or (preferences.sectors if preferences else [])
            return {"sectors": sectors, "timeframe": timeframe}

        if tool_name == "calculate_var":
            return {
                "portfolio": {},
                "confidence_level": 0.95,
                "timeframe": timeframe,
            }

        if tool_name == "conduct_research":
            return {
                "sectors": entities.sectors
                or (preferences.sectors if preferences else []),
                "risk_tolerance": (
                    entities.risk_tolerance
                    or (preferences.risk_tolerance if preferences else None)
                ),
                "investment_goals": entities.goals
                or (preferences.goals if preferences else []),
            }

        return {}

    def _check_preference_requirement(
        self,
        tool_name: str,
        preferences: Optional[UserPreferences],
    ) -> None:
        if tool_name == "get_stock_recommendations":
            if not preferences or not preferences.goals or not preferences.sectors:
                raise ValueError(
                    "Stock recommendations require user preferences (sectors and goals)."
                )

        if tool_name == "conduct_research":
            if not preferences or not preferences.is_complete():
                raise ValueError(
                    "Full research requires complete preferences (goals, sectors, risk_tolerance)."
                )

    @staticmethod
    def _intent_to_key(intent_type: IntentType | str) -> str:
        if isinstance(intent_type, Enum):
            return intent_type.value
        return str(intent_type)


def route_intent_to_tools(
    classification: IntentClassification,
    preferences: Optional[UserPreferences] = None,
) -> List[ToolCall]:
    """Convenience function for routing an intent classification to tool calls."""
    return ToolRouter().route_intent_to_tools(classification, preferences)
