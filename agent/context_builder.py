"""
Context-Aware Response Builder.

Incorporates conversation history into responses by finding relevant turns,
detecting repeated questions, referencing prior answers, and suggesting
follow-up questions.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent.conversation_manager import Message


STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "to", "of", "for", "and", "or",
    "in", "on", "at", "by", "with", "this", "that", "it", "i", "me", "you", "my",
    "your", "about", "tell", "show", "what", "how", "can", "could", "please", "today",
}


@dataclass
class ReferenceMatch:
    """Represents a reference to prior conversation content."""

    user_message: str
    assistant_message: str
    similarity: float


class ContextBuilder:
    """Builds context-aware responses from conversation history."""

    def __init__(self, llm_provider: str = "groq", model: str = "llama-3.3-70b-versatile"):
        self.llm_provider = llm_provider
        self.model = model
        self._groq_client = None

    def get_relevant_history(
        self,
        user_query: str,
        history: Sequence[Message],
        top_k: int = 3,
        min_similarity: float = 0.12,
    ) -> List[Message]:
        """Return the most relevant history messages via lexical similarity."""
        if not user_query or not history:
            return []

        scored: List[Tuple[float, int, Message]] = []
        query_tokens = self._tokenize(user_query)

        for idx, message in enumerate(history):
            msg_tokens = self._tokenize(message.content)
            score = self._jaccard_similarity(query_tokens, msg_tokens)
            if score >= min_similarity:
                scored.append((score, idx, message))

        # sort by score desc, then recency desc
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:top_k]]

    def detect_repeated_question(
        self,
        user_query: str,
        history: Sequence[Message],
        threshold: float = 0.83,
    ) -> bool:
        """Detect whether current query is essentially a repeated user question."""
        normalized_query = self._normalize_text(user_query)
        if not normalized_query:
            return False

        prior_user_messages = [m for m in history if m.role == "user"]
        for message in prior_user_messages:
            previous = self._normalize_text(message.content)
            if not previous:
                continue
            ratio = SequenceMatcher(None, normalized_query, previous).ratio()
            if ratio >= threshold:
                return True

        return False

    def detect_references(
        self,
        user_query: str,
        history: Sequence[Message],
        top_k: int = 2,
    ) -> List[ReferenceMatch]:
        """
        Find prior user+assistant pairs relevant to current query.

        This links previous user questions to their nearest assistant replies.
        """
        if not history:
            return []

        relevant_users = [
            m for m in self.get_relevant_history(user_query, history, top_k=top_k * 2)
            if m.role == "user"
        ]

        references: List[ReferenceMatch] = []
        for user_msg in relevant_users:
            assistant_msg = self._find_next_assistant_reply(history, user_msg)
            if not assistant_msg:
                continue
            similarity = SequenceMatcher(
                None,
                self._normalize_text(user_query),
                self._normalize_text(user_msg.content),
            ).ratio()
            references.append(
                ReferenceMatch(
                    user_message=user_msg.content,
                    assistant_message=assistant_msg.content,
                    similarity=similarity,
                )
            )

        references.sort(key=lambda r: r.similarity, reverse=True)
        return references[:top_k]

    def generate_follow_up_suggestions(
        self,
        user_query: str,
        response_text: str,
        max_suggestions: int = 3,
    ) -> List[str]:
        """Generate lightweight follow-up suggestions from current topic."""
        combined = f"{user_query} {response_text}".lower()
        suggestions: List[str] = []

        if any(k in combined for k in ["market", "indices", "spx", "dji"]):
            suggestions.append("Would you like a sector breakdown behind those market moves?")
        if any(k in combined for k in ["sector", "technology", "healthcare", "energy"]):
            suggestions.append("Do you want a deeper risk profile for this sector?")
        if any(k in combined for k in ["risk", "volatility", "drawdown", "var"]):
            suggestions.append("Should I pull recent news themes driving that risk?")
        if any(k in combined for k in ["stock", "ticker", "recommendation"]):
            suggestions.append("Would you like me to compare these with another sector or goal?")

        if not suggestions:
            suggestions = [
                "Want me to run a broader market overview next?",
                "Would you like recommendations aligned to your risk profile?",
            ]

        return suggestions[:max_suggestions]

    def build_contextualized_response(
        self,
        user_query: str,
        base_response: str,
        history: Sequence[Message],
        include_followups: bool = True,
    ) -> str:
        """
        Build response that references prior context and avoids unnecessary repetition.

        If LLM is configured and available, it can polish phrasing while preserving
        factual content from `base_response`.
        """
        if not base_response:
            return "I need a bit more information before I can answer that."

        repeated = self.detect_repeated_question(user_query, history)
        references = self.detect_references(user_query, history, top_k=1)

        response = base_response.strip()

        if repeated:
            response = f"As mentioned earlier, {response[0].lower() + response[1:] if len(response) > 1 else response}"
        elif references:
            response = (
                "Based on your earlier question, this builds on the previous context.\n"
                + response
            )

        llm_polish = self._build_contextualized_response_with_llm(
            user_query=user_query,
            base_response=response,
            references=references,
        )
        if llm_polish:
            response = llm_polish

        if include_followups:
            follow_ups = self.generate_follow_up_suggestions(user_query, response)
            if follow_ups:
                response += "\n\nPossible next questions:\n"
                response += "\n".join([f"- {item}" for item in follow_ups])

        return response

    def _build_contextualized_response_with_llm(
        self,
        user_query: str,
        base_response: str,
        references: Sequence[ReferenceMatch],
    ) -> Optional[str]:
        """Optional LLM contextualizer with safe fallback to deterministic output."""
        if self.llm_provider != "groq":
            return None

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None

        try:
            from groq import Groq
        except ImportError:
            return None

        try:
            if self._groq_client is None:
                self._groq_client = Groq(api_key=api_key)

            ref_payload = [
                {
                    "user_message": ref.user_message,
                    "assistant_message": ref.assistant_message,
                    "similarity": round(ref.similarity, 3),
                }
                for ref in references
            ]

            prompt = f"""Rewrite the answer to be conversational and context-aware.
Use only the factual information in BASE_RESPONSE.

USER_QUERY:
{user_query}

BASE_RESPONSE:
{base_response}

REFERENCE_CONTEXT:
{json.dumps(ref_payload, indent=2)}

Constraints:
- Keep facts unchanged
- Keep concise (max 120 words)
- If references exist, include a short continuity phrase
- Do not invent data
"""

            response = self._groq_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=220,
            )
            polished = (response.choices[0].message.content or "").strip()
            return polished or None
        except Exception:
            return None

    def _find_next_assistant_reply(
        self,
        history: Sequence[Message],
        user_message: Message,
    ) -> Optional[Message]:
        """Find the closest assistant reply following a given user message."""
        try:
            idx = history.index(user_message)
        except ValueError:
            return None

        for message in history[idx + 1:]:
            if message.role == "assistant":
                return message
        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"\s+", " ", text)
        return re.sub(r"[^a-z0-9\s\-]", "", text)

    def _tokenize(self, text: str) -> List[str]:
        normalized = self._normalize_text(text)
        tokens = [tok for tok in normalized.split() if tok and tok not in STOPWORDS]
        return tokens

    @staticmethod
    def _jaccard_similarity(left: Sequence[str], right: Sequence[str]) -> float:
        left_set = set(left)
        right_set = set(right)
        if not left_set or not right_set:
            return 0.0
        intersection = len(left_set.intersection(right_set))
        union = len(left_set.union(right_set))
        return intersection / union if union else 0.0
