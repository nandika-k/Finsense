"""
Intent Classification System

Analyzes user queries to determine intent and extract relevant entities.
Uses Groq LLM for natural language understanding.
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Literal
from enum import Enum
import logging

# Import available sectors and goals from conversation_manager
from agent.conversation_manager import AVAILABLE_SECTORS, INVESTMENT_GOALS

logger = logging.getLogger(__name__)

# Confidence levels
ConfidenceLevel = Literal["high", "medium", "low"]


class IntentType(str, Enum):
    """Enumeration of all supported intent types."""

    # Informational Queries
    MARKET_OVERVIEW = "market_overview"
    SECTOR_INFO = "sector_info"
    STOCK_DETAILS = "stock_details"
    RISK_ANALYSIS = "risk_analysis"
    NEWS_QUERY = "news_query"
    GENERAL_INFO = "general_info"

    # Recommendation Requests
    STOCK_RECOMMENDATIONS = "stock_recommendations"
    SECTOR_RECOMMENDATIONS = "sector_recommendations"
    PORTFOLIO_ANALYSIS = "portfolio_analysis"

    # Preference Management
    SET_PREFERENCES = "set_preferences"
    VIEW_PREFERENCES = "view_preferences"
    CLEAR_PREFERENCES = "clear_preferences"

    # Action Requests
    FULL_RESEARCH = "full_research"
    COMPARE = "compare"
    CALCULATE_RISK = "calculate_risk"
    NEWS_FOR_SECTOR = "news_for_sector"

    # Meta/Conversational
    GREETING = "greeting"
    NEEDS_CLARIFICATION = "needs_clarification"
    OUT_OF_SCOPE = "out_of_scope"


# Intent descriptions for LLM prompt
INTENT_DESCRIPTIONS = {
    "market_overview": "User wants general market status, indices, or overall market conditions",
    "sector_info": "User wants information about specific sector(s) - performance, characteristics, trends",
    "stock_details": "User wants details about specific stock(s) - price, fundamentals, company info",
    "risk_analysis": "User wants risk assessment, volatility analysis, or risk factors",
    "news_query": "User wants recent news, headlines, or current events",
    "general_info": "General informational question not covered by other categories",
    "stock_recommendations": "User wants stock picks or investment suggestions (requires preferences)",
    "sector_recommendations": "User wants sector allocation advice (requires preferences)",
    "portfolio_analysis": "User wants portfolio review or analysis (requires holdings)",
    "set_preferences": "User is providing or updating investment preferences (goals, sectors, risk tolerance)",
    "view_preferences": "User wants to see their current preferences",
    "clear_preferences": "User wants to reset/clear their preferences",
    "full_research": "User wants comprehensive research report (batch mode)",
    "compare": "User wants to compare multiple sectors or stocks",
    "calculate_risk": "User wants specific risk calculations (VaR, volatility, etc.)",
    "news_for_sector": "User wants news specific to a sector",
    "greeting": "User is greeting or starting conversation",
    "needs_clarification": "Query is ambiguous, unclear, or needs more information",
    "out_of_scope": "Query is outside Finsense capabilities (personal advice, specific trades, etc.)",
}


@dataclass
class ExtractedEntities:
    """Entities extracted from user query."""

    tickers: List[str] = field(default_factory=list)
    sectors: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    risk_tolerance: Optional[str] = None
    timeframe: Optional[str] = None
    comparison_items: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedEntities":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

    def is_empty(self) -> bool:
        """Check if no entities were extracted."""
        return (
            not self.tickers
            and not self.sectors
            and not self.goals
            and self.risk_tolerance is None
            and self.timeframe is None
            and not self.comparison_items
        )


@dataclass
class IntentClassification:
    """
    Result of intent classification.

    Attributes:
        intent_type: The classified intent
        confidence: Confidence level (high/medium/low)
        extracted_entities: Entities found in the query
        requires_preferences: Whether this intent needs user preferences
        clarification_needed: Whether clarification is required
        clarification_message: Optional message asking for clarification
        raw_query: Original user query
    """

    intent_type: IntentType
    confidence: ConfidenceLevel
    extracted_entities: ExtractedEntities
    requires_preferences: bool = False
    clarification_needed: bool = False
    clarification_message: Optional[str] = None
    raw_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "intent_type": self.intent_type.value,
            "confidence": self.confidence,
            "extracted_entities": self.extracted_entities.to_dict(),
            "requires_preferences": self.requires_preferences,
            "clarification_needed": self.clarification_needed,
            "clarification_message": self.clarification_message,
            "raw_query": self.raw_query,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentClassification":
        """Create from dictionary."""
        entities_dict = data.get("extracted_entities", {})
        return cls(
            intent_type=IntentType(data["intent_type"]),
            confidence=data["confidence"],
            extracted_entities=ExtractedEntities.from_dict(entities_dict),
            requires_preferences=data.get("requires_preferences", False),
            clarification_needed=data.get("clarification_needed", False),
            clarification_message=data.get("clarification_message"),
            raw_query=data.get("raw_query", ""),
        )


# Intents that require user preferences
PREFERENCE_REQUIRED_INTENTS = {
    IntentType.SECTOR_RECOMMENDATIONS,
    IntentType.FULL_RESEARCH,
}  # STOCK_RECOMMENDATIONS now uses defaults for quick picks


class IntentClassifier:
    """
    Classifies user intent and extracts entities using LLM.
    """

    def __init__(
        self, llm_provider: str = "groq", model: str = "llama-3.3-70b-versatile"
    ):
        """
        Initialize IntentClassifier.

        Args:
            llm_provider: LLM provider to use (default: "groq")
            model: Model name to use (default: "llama-3.3-70b-versatile")
        """
        self.llm_provider = llm_provider
        self.model = model
        self._groq_client = None

        logger.info(f"IntentClassifier initialized with {llm_provider}/{model}")

    def classify_intent(
        self, query: str, conversation_context: Optional[List[str]] = None
    ) -> IntentClassification:
        """
        Classify user intent and extract entities.

        Args:
            query: User's query string
            conversation_context: Optional previous messages for context

        Returns:
            IntentClassification with intent, confidence, and entities
        """
        if not query or not query.strip():
            logger.warning("Empty query provided")
            return self._create_fallback_classification(query, "Query is empty")

        query = query.strip()

        # Try LLM-based classification
        try:
            classification = self._classify_with_llm(query, conversation_context)

            # Apply fallback logic for low confidence
            if classification.confidence == "low":
                classification = self._apply_fallback_logic(classification)

            # Check if preferences are required
            classification.requires_preferences = (
                classification.intent_type in PREFERENCE_REQUIRED_INTENTS
            )

            logger.info(
                f"Classified intent: {classification.intent_type.value} "
                f"(confidence: {classification.confidence})"
            )

            return classification

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            # Create fallback and apply heuristics
            fallback = self._create_fallback_classification(
                query, "Unable to understand query. Could you rephrase?"
            )
            # Try to improve with heuristics
            return self._apply_fallback_logic(fallback)

    def _classify_with_llm(
        self, query: str, conversation_context: Optional[List[str]] = None
    ) -> IntentClassification:
        """Classify intent using LLM."""

        if self.llm_provider == "groq":
            return self._classify_with_groq(query, conversation_context)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def _classify_with_groq(
        self, query: str, conversation_context: Optional[List[str]] = None
    ) -> IntentClassification:
        """Classify intent using Groq LLM."""

        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq package not installed. Install with: pip install groq"
            )

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")

        # Initialize client if needed
        if self._groq_client is None:
            self._groq_client = Groq(api_key=api_key)

        # Build classification prompt
        prompt = self._build_classification_prompt(query, conversation_context)

        try:
            response = self._groq_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=800,
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            classification = self._parse_llm_response(result_text, query)
            return classification

        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            raise

    def _build_classification_prompt(
        self, query: str, conversation_context: Optional[List[str]] = None
    ) -> str:
        """Build prompt for intent classification."""

        # Build intent list for prompt
        intent_list = "\n".join(
            [
                f"- {intent.value}: {INTENT_DESCRIPTIONS[intent.value]}"
                for intent in IntentType
            ]
        )

        # Build available sectors list
        sectors_str = ", ".join(AVAILABLE_SECTORS)

        # Build available goals list
        goals_str = ", ".join(INVESTMENT_GOALS)

        context_section = ""
        if conversation_context and len(conversation_context) > 0:
            context_str = "\n".join([f"- {msg}" for msg in conversation_context[-3:]])
            context_section = f"\n\nRECENT CONVERSATION CONTEXT:\n{context_str}"

        prompt = f"""You are an intent classification system for a financial research assistant.

Classify the following user query into ONE of these intent types:

{intent_list}

Extract the following entities if present:
- tickers: Stock ticker symbols (e.g., AAPL, MSFT, GOOGL)
- sectors: Sector names from: {sectors_str}
- goals: Investment goals from: {goals_str}
- risk_tolerance: One of: low, medium, high
- timeframe: Time period mentioned (e.g., "this week", "last month", "YTD")
- comparison_items: Items being compared (sectors or stocks)

Assess confidence level:
- high: Intent is clear and unambiguous
- medium: Intent is likely correct but has some ambiguity
- low: Intent is unclear or query needs clarification

If confidence is low or query is ambiguous, set clarification_needed=true and provide a helpful clarification_message.{context_section}

USER QUERY: "{query}"

Respond ONLY with a JSON object in this exact format:
{{
  "intent_type": "intent_name",
  "confidence": "high|medium|low",
  "entities": {{
    "tickers": ["AAPL", "MSFT"],
    "sectors": ["technology"],
    "goals": ["growth"],
    "risk_tolerance": "medium",
    "timeframe": "this month",
    "comparison_items": ["technology", "healthcare"]
  }},
  "clarification_needed": false,
  "clarification_message": null
}}

IMPORTANT: 
- Use null for missing values, not empty strings
- Ensure ticker symbols are uppercase
- Match sector names exactly from the provided list
- Match goal names exactly from the provided list
- Only include entities that are explicitly mentioned or strongly implied"""

        return prompt

    def _parse_llm_response(
        self, response_text: str, original_query: str
    ) -> IntentClassification:
        """Parse LLM response into IntentClassification."""

        try:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
            )
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON object directly
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("No JSON found in response")

            data = json.loads(json_str)

            # Parse intent type
            intent_type_str = data.get("intent_type", "needs_clarification")
            try:
                intent_type = IntentType(intent_type_str)
            except ValueError:
                logger.warning(
                    f"Unknown intent type: {intent_type_str}, defaulting to needs_clarification"
                )
                intent_type = IntentType.NEEDS_CLARIFICATION

            # Parse confidence
            confidence = data.get("confidence", "low")
            if confidence not in ["high", "medium", "low"]:
                confidence = "medium"

            # Parse entities
            entities_data = data.get("entities", {})
            entities = ExtractedEntities(
                tickers=self._normalize_tickers(entities_data.get("tickers") or []),
                sectors=self._normalize_sectors(entities_data.get("sectors") or []),
                goals=self._normalize_goals(entities_data.get("goals") or []),
                risk_tolerance=entities_data.get("risk_tolerance"),
                timeframe=entities_data.get("timeframe"),
                comparison_items=entities_data.get("comparison_items") or [],
            )

            # Create classification
            classification = IntentClassification(
                intent_type=intent_type,
                confidence=confidence,
                extracted_entities=entities,
                clarification_needed=data.get("clarification_needed", False),
                clarification_message=data.get("clarification_message"),
                raw_query=original_query,
            )

            return classification

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            raise ValueError(f"Invalid JSON in LLM response: {e}")

        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            raise

    def _normalize_tickers(self, tickers: List[str]) -> List[str]:
        """Normalize ticker symbols to uppercase."""
        return [ticker.upper().strip() for ticker in tickers if ticker]

    def _normalize_sectors(self, sectors: List[str]) -> List[str]:
        """Normalize and validate sector names."""
        normalized = []
        for sector in sectors:
            sector_lower = sector.lower().strip()
            if sector_lower in AVAILABLE_SECTORS:
                normalized.append(sector_lower)
            else:
                # Try fuzzy matching
                for valid_sector in AVAILABLE_SECTORS:
                    if sector_lower in valid_sector or valid_sector in sector_lower:
                        normalized.append(valid_sector)
                        break
        return list(set(normalized))  # Deduplicate

    def _normalize_goals(self, goals: List[str]) -> List[str]:
        """Normalize and validate investment goals."""
        normalized = []
        for goal in goals:
            goal_lower = goal.lower().strip()
            if goal_lower in INVESTMENT_GOALS:
                normalized.append(goal_lower)
            else:
                # Try fuzzy matching
                for valid_goal in INVESTMENT_GOALS:
                    if goal_lower in valid_goal or valid_goal in goal_lower:
                        normalized.append(valid_goal)
                        break
        return list(set(normalized))  # Deduplicate

    def _apply_fallback_logic(
        self, classification: IntentClassification
    ) -> IntentClassification:
        """
        Apply fallback logic for low-confidence classifications.

        Uses heuristics to improve classification or request clarification.
        """
        query_lower = classification.raw_query.lower()
        query_words = set(query_lower.split())

        # Greeting detection (word-level matching)
        greeting_words = {"hello", "hi", "hey", "greetings", "sup", "howdy"}
        greeting_phrases = ["good morning", "good afternoon", "good evening"]

        # Check for exact word matches or phrase matches
        is_greeting = bool(greeting_words.intersection(query_words)) or any(
            phrase in query_lower for phrase in greeting_phrases
        )

        if is_greeting and len(query_words) <= 5:
            classification.intent_type = IntentType.GREETING
            classification.confidence = "high"
            classification.clarification_needed = False
            return classification

        # Market overview detection (support direct command phrasing)
        market_patterns = [
            r"\bmarket overview\b",
            r"\bmarket status\b",
            r"\bmarket snapshot\b",
            r"\b(indices|index)\b",
            r"\b(dow|nasdaq|s&p|spx|dji|ixic|russell)\b",
            r"\boverall market\b",
        ]
        if any(re.search(pattern, query_lower) for pattern in market_patterns):
            classification.intent_type = IntentType.MARKET_OVERVIEW
            classification.confidence = "high"
            classification.clarification_needed = False
            return classification

        # News/headlines fallback detection
        news_patterns = [r"\bnews\b", r"\bheadlines?\b", r"\bbreaking\b"]
        if any(re.search(pattern, query_lower) for pattern in news_patterns):
            classification.intent_type = IntentType.NEWS_QUERY
            classification.confidence = "medium"
            classification.clarification_needed = False
            return classification

        # Stock recommendation fallback detection
        stock_reco_patterns = [
            r"\bstock(s)?\b",
            r"\bstock ideas\b",
            r"\bstock picks\b",
            r"\brecommend.*stock",
        ]
        if any(re.search(pattern, query_lower) for pattern in stock_reco_patterns):
            classification.intent_type = IntentType.STOCK_RECOMMENDATIONS
            classification.confidence = "medium"
            classification.clarification_needed = False
            return classification

        # If still unclear, ask for clarification
        if (
            classification.confidence == "low"
            and not classification.clarification_needed
        ):
            classification.intent_type = IntentType.NEEDS_CLARIFICATION
            classification.clarification_needed = True
            classification.clarification_message = (
                "I'd be happy to help! Could you provide more details about what you're looking for? "
                "For example, are you interested in market data, sector information, stock recommendations, "
                "or something else?"
            )

        return classification

    def _create_fallback_classification(
        self, query: str, clarification_message: str
    ) -> IntentClassification:
        """Create a fallback classification for error cases."""
        return IntentClassification(
            intent_type=IntentType.NEEDS_CLARIFICATION,
            confidence="low",
            extracted_entities=ExtractedEntities(),
            clarification_needed=True,
            clarification_message=clarification_message,
            raw_query=query,
        )

    def batch_classify(
        self, queries: List[str], conversation_context: Optional[List[str]] = None
    ) -> List[IntentClassification]:
        """
        Classify multiple queries.

        Args:
            queries: List of user queries
            conversation_context: Optional conversation context

        Returns:
            List of IntentClassification objects
        """
        return [self.classify_intent(q, conversation_context) for q in queries]


# Convenience function for quick classification
def classify_intent(
    query: str, conversation_context: Optional[List[str]] = None
) -> IntentClassification:
    """
    Convenience function to classify a single query.

    Args:
        query: User query string
        conversation_context: Optional conversation context

    Returns:
        IntentClassification object
    """
    classifier = IntentClassifier()
    return classifier.classify_intent(query, conversation_context)
