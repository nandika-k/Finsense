"""
Conversation Manager Module

Central orchestrator for conversational interactions with the Finsense agent.
Manages conversation history, user preferences, and session state.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field, asdict
import logging

logger = logging.getLogger(__name__)

# Constants for validation (imported from ui/chatbot.py concepts)
AVAILABLE_SECTORS = [
    "technology",
    "healthcare",
    "financial-services",
    "energy",
    "consumer",
    "consumer-discretionary",
    "consumer-staples",
    "utilities",
    "real-estate",
    "industrials",
    "materials",
    "communication-services"
]

INVESTMENT_GOALS = [
    "growth",
    "income",
    "esg",
    "value",
    "defensive",
    "diversified"
]

RISK_TOLERANCE_LEVELS = ["low", "medium", "high"]

# Message role types
MessageRole = Literal["user", "assistant", "system"]


@dataclass
class Message:
    """Represents a single message in the conversation."""
    role: MessageRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create message from dictionary."""
        return cls(**data)


@dataclass
class UserPreferences:
    """User investment preferences."""
    goals: List[str] = field(default_factory=list)
    sectors: List[str] = field(default_factory=list)
    risk_tolerance: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert preferences to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreferences":
        """Create preferences from dictionary."""
        return cls(**data)
    
    def validate(self) -> List[str]:
        """
        Validate preferences and return list of validation errors.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Validate goals
        invalid_goals = [g for g in self.goals if g not in INVESTMENT_GOALS]
        if invalid_goals:
            errors.append(f"Invalid goals: {invalid_goals}. Valid: {INVESTMENT_GOALS}")
        
        # Validate sectors
        invalid_sectors = [s for s in self.sectors if s not in AVAILABLE_SECTORS]
        if invalid_sectors:
            errors.append(f"Invalid sectors: {invalid_sectors}. Valid: {AVAILABLE_SECTORS}")
        
        # Validate risk tolerance
        if self.risk_tolerance and self.risk_tolerance not in RISK_TOLERANCE_LEVELS:
            errors.append(f"Invalid risk_tolerance: {self.risk_tolerance}. Valid: {RISK_TOLERANCE_LEVELS}")
        
        return errors
    
    def is_complete(self) -> bool:
        """Check if all required preferences are set."""
        return bool(self.goals) and bool(self.sectors) and self.risk_tolerance is not None
    
    def missing_fields(self) -> List[str]:
        """Return list of missing required fields."""
        missing = []
        if not self.goals:
            missing.append("goals")
        if not self.sectors:
            missing.append("sectors")
        if self.risk_tolerance is None:
            missing.append("risk_tolerance")
        return missing


class ConversationManager:
    """
    Central orchestrator for conversational interactions.
    
    Manages:
    - Conversation history (append-only log of messages)
    - User preferences (goals, sectors, risk_tolerance)
    - Session state
    - History pruning/summarization for token management
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        max_history_turns: int = 20,
        enable_summarization: bool = True
    ):
        """
        Initialize ConversationManager.
        
        Args:
            session_id: Unique session identifier (auto-generated if None)
            max_history_turns: Maximum turns before summarization (default: 20)
            enable_summarization: Enable automatic history summarization (default: True)
        """
        self.session_id = session_id or self._generate_session_id()
        self.max_history_turns = max_history_turns
        self.enable_summarization = enable_summarization
        
        # Core storage
        self._history: List[Message] = []
        self._preferences = UserPreferences()
        self._session_metadata: Dict[str, Any] = {
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "turn_count": 0,
            "summarization_count": 0
        }
        
        # Summarization state
        self._summary: Optional[str] = None
        self._summarized_until_turn: int = 0
        
        logger.info(f"ConversationManager initialized with session_id: {self.session_id}")
    
    # ==================== History Management ====================
    
    def add_message(
        self,
        role: MessageRole,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Add a message to conversation history.
        
        Args:
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata dictionary
            
        Returns:
            The created Message object
        """
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self._history.append(message)
        
        # Update session metadata
        self._session_metadata["last_activity"] = datetime.utcnow().isoformat()
        if role == "user":
            self._session_metadata["turn_count"] += 1
        
        # Check if summarization needed
        if self.enable_summarization and self._should_summarize():
            self._trigger_summarization()
        
        logger.debug(f"Added {role} message (length: {len(content)} chars)")
        return message
    
    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Convenience method to add user message."""
        return self.add_message("user", content, metadata)
    
    def add_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Convenience method to add assistant message."""
        return self.add_message("assistant", content, metadata)
    
    def add_system_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Convenience method to add system message."""
        return self.add_message("system", content, metadata)
    
    def get_full_history(self) -> List[Message]:
        """
        Get complete conversation history.
        
        Returns:
            List of all Message objects
        """
        return self._history.copy()
    
    def get_last_n(self, n: int) -> List[Message]:
        """
        Get last N messages from history.
        
        Args:
            n: Number of messages to retrieve
            
        Returns:
            List of last N Message objects
        """
        return self._history[-n:] if n > 0 else []
    
    def get_history_as_dicts(self) -> List[Dict[str, Any]]:
        """
        Get conversation history as list of dictionaries.
        
        Returns:
            List of message dictionaries
        """
        return [msg.to_dict() for msg in self._history]
    
    def get_message_count(self) -> int:
        """Get total number of messages in history."""
        return len(self._history)
    
    def get_turn_count(self) -> int:
        """Get number of user turns (user messages)."""
        return self._session_metadata["turn_count"]
    
    def clear_history(self) -> None:
        """Clear all conversation history (use with caution)."""
        logger.warning(f"Clearing conversation history for session {self.session_id}")
        self._history.clear()
        self._summary = None
        self._summarized_until_turn = 0
        self._session_metadata["turn_count"] = 0
        self._session_metadata["summarization_count"] = 0
    
    # ==================== Preference Management ====================
    
    def get_preferences(self) -> UserPreferences:
        """
        Get current user preferences.
        
        Returns:
            UserPreferences object (copy)
        """
        return UserPreferences(
            goals=self._preferences.goals.copy(),
            sectors=self._preferences.sectors.copy(),
            risk_tolerance=self._preferences.risk_tolerance
        )
    
    def set_preferences(
        self,
        goals: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
        risk_tolerance: Optional[str] = None,
        validate: bool = True
    ) -> bool:
        """
        Set user preferences (replaces existing values).
        
        Args:
            goals: Investment goals
            sectors: Sectors of interest
            risk_tolerance: Risk tolerance level
            validate: Validate preferences before setting (default: True)
            
        Returns:
            True if successful, False if validation failed
        """
        # Create new preferences object
        new_prefs = UserPreferences(
            goals=goals if goals is not None else self._preferences.goals,
            sectors=sectors if sectors is not None else self._preferences.sectors,
            risk_tolerance=risk_tolerance if risk_tolerance is not None else self._preferences.risk_tolerance
        )
        
        # Validate if requested
        if validate:
            errors = new_prefs.validate()
            if errors:
                logger.error(f"Preference validation failed: {errors}")
                return False
        
        # Update preferences
        self._preferences = new_prefs
        logger.info(f"Preferences updated: {self._preferences.to_dict()}")
        return True
    
    def update_preferences(
        self,
        goals: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
        risk_tolerance: Optional[str] = None,
        validate: bool = True
    ) -> bool:
        """
        Update user preferences (merges with existing values).
        
        For lists (goals, sectors), new values are appended (deduplicated).
        For risk_tolerance, new value replaces old value.
        
        Args:
            goals: Investment goals to add
            sectors: Sectors to add
            risk_tolerance: Risk tolerance level (replaces)
            validate: Validate preferences before updating
            
        Returns:
            True if successful, False if validation failed
        """
        # Merge goals (deduplicate)
        merged_goals = self._preferences.goals.copy()
        if goals:
            merged_goals.extend([g for g in goals if g not in merged_goals])
        
        # Merge sectors (deduplicate)
        merged_sectors = self._preferences.sectors.copy()
        if sectors:
            merged_sectors.extend([s for s in sectors if s not in merged_sectors])
        
        # Risk tolerance replaces
        merged_risk = risk_tolerance if risk_tolerance is not None else self._preferences.risk_tolerance
        
        return self.set_preferences(merged_goals, merged_sectors, merged_risk, validate)
    
    def clear_preferences(self) -> None:
        """Clear all user preferences."""
        logger.info(f"Clearing preferences for session {self.session_id}")
        self._preferences = UserPreferences()
    
    def are_preferences_complete(self) -> bool:
        """Check if all required preferences are set."""
        return self._preferences.is_complete()
    
    def get_missing_preferences(self) -> List[str]:
        """Get list of missing required preference fields."""
        return self._preferences.missing_fields()
    
    # ==================== Session State ====================
    
    def get_session_metadata(self) -> Dict[str, Any]:
        """
        Get session metadata.
        
        Returns:
            Dictionary with session information
        """
        return {
            **self._session_metadata,
            "session_id": self.session_id,
            "message_count": len(self._history),
            "has_summary": self._summary is not None,
            "preferences_complete": self._preferences.is_complete()
        }
    
    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive session summary.
        
        Returns:
            Dictionary with session state overview
        """
        return {
            "session_id": self.session_id,
            "metadata": self.get_session_metadata(),
            "preferences": self._preferences.to_dict(),
            "history_summary": {
                "total_messages": len(self._history),
                "user_turns": self._session_metadata["turn_count"],
                "assistant_messages": sum(1 for m in self._history if m.role == "assistant"),
                "system_messages": sum(1 for m in self._history if m.role == "system"),
                "has_conversation_summary": self._summary is not None,
                "summarized_until_turn": self._summarized_until_turn
            }
        }
    
    # ==================== History Summarization ====================
    
    def _should_summarize(self) -> bool:
        """Check if history should be summarized."""
        turn_count = self._session_metadata["turn_count"]
        return turn_count > self.max_history_turns and turn_count > self._summarized_until_turn
    
    def _trigger_summarization(self) -> None:
        """
        Trigger automatic history summarization.
        
        This is a placeholder that logs the need for summarization.
        Actual LLM-based summarization should be implemented via summarize_history_with_llm().
        """
        logger.info(f"Conversation exceeds {self.max_history_turns} turns. Summarization recommended.")
        logger.info("Call summarize_history_with_llm() to generate summary with LLM.")
    
    def summarize_history_with_llm(self, llm_provider: str = "groq") -> Optional[str]:
        """
        Summarize conversation history using LLM.
        
        This generates a concise summary of the conversation so far,
        which can be used to maintain context while reducing token usage.
        
        Args:
            llm_provider: LLM provider to use (default: "groq")
            
        Returns:
            Summary string if successful, None otherwise
        """
        if not self._history:
            logger.warning("No history to summarize")
            return None
        
        try:
            if llm_provider == "groq":
                summary = self._summarize_with_groq()
            else:
                logger.error(f"Unsupported LLM provider: {llm_provider}")
                return None
            
            if summary:
                self._summary = summary
                self._summarized_until_turn = self._session_metadata["turn_count"]
                self._session_metadata["summarization_count"] += 1
                logger.info(f"History summarized successfully (turn {self._summarized_until_turn})")
            
            return summary
        
        except Exception as e:
            logger.error(f"Failed to summarize history: {e}")
            return None
    
    def _summarize_with_groq(self) -> Optional[str]:
        """Summarize conversation history using Groq LLM."""
        try:
            from groq import Groq
        except ImportError:
            logger.error("groq package not installed. Install with: pip install groq")
            return None
        
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY not set. Skipping LLM summarization.")
            return None
        
        try:
            client = Groq(api_key=api_key)
            
            # Build conversation transcript
            transcript = self._build_transcript_for_summarization()
            
            # Create summarization prompt
            prompt = f"""Summarize the following conversation between a user and an AI financial assistant.
Focus on:
1. Key topics discussed
2. User's investment preferences (goals, sectors, risk tolerance)
3. Important questions asked and answers provided
4. Any decisions or conclusions reached

Keep the summary concise (2-4 paragraphs) but comprehensive.

CONVERSATION:
{transcript}

SUMMARY:"""
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            summary = response.choices[0].message.content.strip()
            return summary
        
        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            return None
    
    def _build_transcript_for_summarization(self) -> str:
        """Build conversation transcript for summarization."""
        lines = []
        for msg in self._history:
            role = msg.role.upper()
            lines.append(f"{role}: {msg.content}")
        return "\n\n".join(lines)
    
    def get_conversation_summary(self) -> Optional[str]:
        """
        Get existing conversation summary.
        
        Returns:
            Summary string if exists, None otherwise
        """
        return self._summary
    
    def has_summary(self) -> bool:
        """Check if conversation has been summarized."""
        return self._summary is not None
    
    # ==================== Export/Import ====================
    
    def export_conversation(self, file_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Export conversation to dictionary (and optionally to JSON file).
        
        Args:
            file_path: Optional path to save JSON file
            
        Returns:
            Dictionary with complete conversation state
        """
        export_data = {
            "session_id": self.session_id,
            "metadata": self._session_metadata,
            "preferences": self._preferences.to_dict(),
            "history": [msg.to_dict() for msg in self._history],
            "summary": self._summary,
            "summarized_until_turn": self._summarized_until_turn,
            "export_timestamp": datetime.utcnow().isoformat()
        }
        
        if file_path:
            try:
                file_path = Path(file_path)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"Conversation exported to {file_path}")
            
            except Exception as e:
                logger.error(f"Failed to export conversation to file: {e}")
        
        return export_data
    
    def import_conversation(self, data: Dict[str, Any]) -> bool:
        """
        Import conversation from dictionary.
        
        Args:
            data: Dictionary with conversation state (from export_conversation)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate required fields
            required_fields = ["session_id", "metadata", "preferences", "history"]
            if not all(field in data for field in required_fields):
                logger.error(f"Import data missing required fields: {required_fields}")
                return False
            
            # Import session metadata
            self.session_id = data["session_id"]
            self._session_metadata = data["metadata"]
            
            # Import preferences
            self._preferences = UserPreferences.from_dict(data["preferences"])
            
            # Import history
            self._history = [Message.from_dict(msg) for msg in data["history"]]
            
            # Import summary (optional)
            self._summary = data.get("summary")
            self._summarized_until_turn = data.get("summarized_until_turn", 0)
            
            logger.info(f"Conversation imported successfully (session: {self.session_id})")
            return True
        
        except Exception as e:
            logger.error(f"Failed to import conversation: {e}")
            return False
    
    @classmethod
    def from_file(cls, file_path: Path) -> Optional["ConversationManager"]:
        """
        Create ConversationManager from exported JSON file.
        
        Args:
            file_path: Path to exported conversation JSON
            
        Returns:
            ConversationManager instance if successful, None otherwise
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            manager = cls()
            if manager.import_conversation(data):
                return manager
            return None
        
        except Exception as e:
            logger.error(f"Failed to load conversation from file: {e}")
            return None
    
    # ==================== Utility Methods ====================
    
    @staticmethod
    def _generate_session_id() -> str:
        """Generate unique session identifier."""
        import uuid
        return f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def __repr__(self) -> str:
        """String representation of ConversationManager."""
        return (
            f"ConversationManager(session_id='{self.session_id}', "
            f"messages={len(self._history)}, "
            f"turns={self._session_metadata['turn_count']}, "
            f"preferences_complete={self._preferences.is_complete()})"
        )
