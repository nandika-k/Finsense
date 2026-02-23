"""
Conversational Agent Core.

Main orchestrator for chat-mode interactions:
- tracks conversation state
- classifies intent
- collects preferences when needed
- routes and executes MCP tool calls
- formats and contextualizes responses
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agent.agent import FinsenseCoordinator
from agent.analytics import ConversationAnalytics
from agent.context_builder import ContextBuilder
from agent.conversation_manager import ConversationManager, UserPreferences
from agent.intent_classifier import IntentClassification, IntentClassifier, IntentType
from agent.preference_collector import PreferenceCollector
from agent.response_formatter import ResponseFormatter
from agent.tool_optimizer import ToolOptimizer
from agent.tool_router import ToolCall, ToolRouter


class ConversationalAgent:
    """Main entry point for conversational mode."""

    def __init__(
        self,
        conversation_manager: Optional[ConversationManager] = None,
        intent_classifier: Optional[IntentClassifier] = None,
        preference_collector: Optional[PreferenceCollector] = None,
        tool_router: Optional[ToolRouter] = None,
        tool_optimizer: Optional[ToolOptimizer] = None,
        response_formatter: Optional[ResponseFormatter] = None,
        context_builder: Optional[ContextBuilder] = None,
        coordinator: Optional[FinsenseCoordinator] = None,
        analytics: Optional[ConversationAnalytics] = None,
    ):
        self.conversation_manager = conversation_manager or ConversationManager()
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.preference_collector = preference_collector or PreferenceCollector()
        self.tool_router = tool_router or ToolRouter()
        self.tool_optimizer = tool_optimizer or ToolOptimizer()
        self.response_formatter = response_formatter or ResponseFormatter()
        self.context_builder = context_builder or ContextBuilder()
        self.coordinator = coordinator or FinsenseCoordinator()
        self.analytics = analytics or ConversationAnalytics(
            session_id=getattr(self.conversation_manager, "session_id", None)
        )

        self._initialized = False
        self._active_query_index: Optional[int] = None

    async def initialize(self) -> None:
        """Initialize tool coordinator connections."""
        if self._initialized:
            return
        if hasattr(self.coordinator, "initialize"):
            await self.coordinator.initialize()
        self._initialized = True

    async def close(self) -> None:
        """Close coordinator connections."""
        if hasattr(self.coordinator, "close"):
            await self.coordinator.close()

    async def process_message(self, user_message: str) -> str:
        """Process one user message and return assistant response."""
        start = time.perf_counter()
        self._active_query_index = self.analytics.start_query()
        self.conversation_manager.add_user_message(user_message)

        try:
            if not self._initialized:
                await self.initialize()

            history = self.conversation_manager.get_full_history()
            context_window = [m.content for m in history[-6:]]

            classification = self.intent_classifier.classify_intent(
                user_message,
                conversation_context=context_window,
            )
            self.analytics.record_intent(
                self._active_query_index, classification.intent_type.value
            )

            response = await self._handle_classified_message(classification)

            contextualized = self.context_builder.build_contextualized_response(
                user_query=user_message,
                base_response=response,
                history=self.conversation_manager.get_full_history(),
            )

            self.conversation_manager.add_assistant_message(
                contextualized,
                metadata={
                    "intent": classification.intent_type.value,
                    "confidence": classification.confidence,
                },
            )
            return contextualized

        except Exception as exc:
            error_response = self.response_formatter.format_error_message(str(exc))
            self.conversation_manager.add_assistant_message(
                error_response,
                metadata={"intent": "error", "error": str(exc)},
            )
            return error_response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.analytics.record_response_time(self._active_query_index, elapsed_ms)
            user_turns = sum(
                1
                for message in self.conversation_manager.get_full_history()
                if message.role == "user"
            )
            self.analytics.record_conversation_length(user_turns)
            self._active_query_index = None

    async def _handle_classified_message(
        self, classification: IntentClassification
    ) -> str:
        """Handle intent-specific paths before/after tool execution."""
        intent = classification.intent_type

        if classification.clarification_needed:
            prompt = (
                classification.clarification_message
                or "Could you provide a bit more detail?"
            )
            return self.response_formatter.format_clarification_prompt(prompt)

        if intent == IntentType.GREETING:
            return "Hi! I can help with market overviews, sector analysis, risks, news, or stock research."

        if intent == IntentType.OUT_OF_SCOPE:
            return (
                "I can’t provide personal buy/sell advice, but I can help you research market, "
                "sector, stock, and risk information to support your decision."
            )

        if intent == IntentType.VIEW_PREFERENCES:
            return self._format_preferences_view(
                self.conversation_manager.get_preferences()
            )

        if intent == IntentType.CLEAR_PREFERENCES:
            self.conversation_manager.clear_preferences()
            return "Your preferences have been cleared."

        if intent == IntentType.SET_PREFERENCES:
            return self._handle_set_preferences(classification.raw_query)

        current_preferences = self.conversation_manager.get_preferences()
        if classification.requires_preferences:
            self.analytics.record_preference_collection(
                self._active_query_index, required=True, success=None
            )
            missing = self.preference_collector.check_required_preferences(
                current_preferences
            )
            if missing:
                self.analytics.record_preference_collection(
                    self._active_query_index, required=True, success=False
                )
                question = self.preference_collector.generate_preference_question(
                    missing
                )
                return self.response_formatter.format_clarification_prompt(question)

        tool_calls = self.tool_router.route_intent_to_tools(
            classification,
            preferences=current_preferences,
        )

        if not tool_calls:
            self.analytics.record_tool_calls(self._active_query_index, 0)
            return "I understood your request, but there is no tool action mapped for it yet."

        tool_results = await self._execute_tool_calls(tool_calls)
        return self._format_tool_results(classification, tool_results)

    def _handle_set_preferences(self, user_message: str) -> str:
        """Collect/update preferences from a user message."""
        current = self.conversation_manager.get_preferences()
        outcome = self.preference_collector.collect_preferences_turn(
            current, user_message
        )
        updated: UserPreferences = outcome["updated_preferences"]

        self.conversation_manager.set_preferences(
            goals=updated.goals,
            sectors=updated.sectors,
            risk_tolerance=updated.risk_tolerance,
            validate=True,
        )

        if outcome["validation_errors"]:
            self.analytics.record_preference_collection(
                self._active_query_index, required=True, success=False
            )
            return self.response_formatter.format_error_message(
                "; ".join(outcome["validation_errors"])
            )

        if outcome["is_complete"]:
            self.analytics.record_preference_collection(
                self._active_query_index, required=True, success=True
            )
            return "Preferences updated successfully. " + self._format_preferences_view(
                updated
            )

        self.analytics.record_preference_collection(
            self._active_query_index, required=True, success=False
        )
        next_question = (
            outcome.get("next_question")
            or "Could you share a bit more preference detail?"
        )
        return self.response_formatter.format_clarification_prompt(next_question)

    async def _execute_tool_calls(self, tool_calls: List[ToolCall]) -> Dict[str, Any]:
        """Execute routed tool calls through coordinator methods."""
        self.analytics.record_tool_calls(self._active_query_index, len(tool_calls))

        async def invoke(call: ToolCall) -> Dict[str, Any] | Any:
            method = getattr(self.coordinator, call.tool_name, None)
            if method is None:
                return {"error": f"Coordinator missing tool method: {call.tool_name}"}

            try:
                return await method(**call.arguments)
            except Exception as exc:
                return {"error": str(exc)}

        return await self.tool_optimizer.execute_tool_calls(tool_calls, invoke)

    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get analytics summary for the current conversation session."""
        return self.analytics.generate_summary()

    def export_analytics_json(self, file_path: str) -> str:
        """Export analytics payload to JSON and return path."""
        return str(self.analytics.export_json(file_path))

    def export_analytics_csv(self, file_path: str) -> str:
        """Export query-level analytics to CSV and return path."""
        return str(self.analytics.export_csv(file_path))

    def get_basic_analytics_visualization(self) -> str:
        """Get text-based analytics visualization."""
        return self.analytics.create_basic_visualization()

    def _format_tool_results(
        self,
        classification: IntentClassification,
        tool_results: Dict[str, Any],
    ) -> str:
        """Format tool outputs according to intent type."""
        intent = classification.intent_type

        if intent == IntentType.MARKET_OVERVIEW:
            market_data = tool_results.get("get_market_indices", {})
            if isinstance(market_data, dict) and market_data.get("error"):
                return self.response_formatter.format_error_message(
                    market_data["error"]
                )
            return self.response_formatter.format_market_overview(market_data)

        if intent in {IntentType.SECTOR_INFO, IntentType.SECTOR_RECOMMENDATIONS}:
            return self.response_formatter.format_sector_analysis(
                tool_results.get("get_sector_summary", {}),
                tool_results.get("compute_sector_volatility"),
            )

        if intent == IntentType.STOCK_RECOMMENDATIONS:
            return self.response_formatter.format_stock_recommendations(
                tool_results.get("get_stock_recommendations", {})
            )

        if intent in {IntentType.RISK_ANALYSIS, IntentType.CALCULATE_RISK}:
            return self.response_formatter.format_risk_analysis(
                tool_results.get("compute_sector_volatility"),
                tool_results.get("identify_sector_risks"),
            )

        if intent in {IntentType.NEWS_QUERY, IntentType.NEWS_FOR_SECTOR}:
            return self.response_formatter.format_news_summary(
                tool_results.get("fetch_headlines"),
                tool_results.get("extract_risk_themes"),
                include_citations=True,
            )

        if intent == IntentType.STOCK_DETAILS:
            details = tool_results.get("get_stock_details", {})
            price = tool_results.get("get_stock_price", {})
            if details.get("error") and price.get("error"):
                return self.response_formatter.format_error_message(
                    details.get("error")
                )

            ticker = details.get("ticker") or price.get("ticker") or "N/A"
            name = details.get("name", "")
            current_price = price.get("price", details.get("price", "N/A"))
            perf_1m = details.get("performance_1m", "N/A")
            vol = details.get("volatility", "N/A")
            return (
                f"{ticker} {name}: current price {current_price}, 1M performance {perf_1m}, "
                f"volatility {vol}."
            )

        if intent == IntentType.COMPARE:
            comparison = tool_results.get("compare_sectors", {})
            if comparison.get("error"):
                return self.response_formatter.format_error_message(comparison["error"])
            return f"Sector comparison completed: {comparison}"

        if intent == IntentType.PORTFOLIO_ANALYSIS:
            var_data = tool_results.get("calculate_var", {})
            if var_data.get("error"):
                return self.response_formatter.format_error_message(var_data["error"])
            return f"Portfolio risk result: {var_data}"

        if intent == IntentType.FULL_RESEARCH:
            research = tool_results.get("conduct_research", {})
            if research.get("error"):
                return self.response_formatter.format_error_message(research["error"])
            summary = research.get("execution_summary", {})
            if summary:
                return (
                    f"Full research completed. Success rate: {summary.get('success_rate', 'N/A')} "
                    f"({summary.get('successful', 0)}/{summary.get('total_operations', 0)} operations)."
                )
            return "Full research completed successfully."

        # fallback for unmapped-but-executed intents
        if len(tool_results) == 1:
            only_value = next(iter(tool_results.values()))
            if isinstance(only_value, dict) and only_value.get("error"):
                return self.response_formatter.format_error_message(only_value["error"])
            return str(only_value)

        return str(tool_results)

    @staticmethod
    def _format_preferences_view(preferences: UserPreferences) -> str:
        """Render current preferences as user-facing summary."""
        goals = ", ".join(preferences.goals) if preferences.goals else "not set"
        sectors = ", ".join(preferences.sectors) if preferences.sectors else "not set"
        risk = preferences.risk_tolerance or "not set"
        return (
            "Current preferences:\n"
            f"- Goals: {goals}\n"
            f"- Sectors: {sectors}\n"
            f"- Risk tolerance: {risk}"
        )
