"""Conversation analytics for conversational agent quality and usage tracking."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class QueryRecord:
    """Per-query analytics record."""

    query_index: int
    intent: Optional[str] = None
    tool_calls: int = 0
    response_time_ms: Optional[float] = None
    required_preferences: bool = False
    preference_collection_success: Optional[bool] = None
    timestamp: float = field(default_factory=time.time)


class ConversationAnalytics:
    """Tracks conversation quality and usage metrics for a session."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"session-{int(time.time())}"
        self.started_at = time.time()
        self._records: List[QueryRecord] = []
        self._conversation_lengths: List[int] = []

    def start_query(self) -> int:
        """Create a new query record and return its index."""
        index = len(self._records)
        self._records.append(QueryRecord(query_index=index))
        return index

    def record_intent(self, query_index: Optional[int], intent: str) -> None:
        """Attach intent label to a query."""
        record = self._safe_get(query_index)
        if record is None:
            return
        record.intent = intent

    def record_tool_calls(
        self, query_index: Optional[int], tool_calls_count: int
    ) -> None:
        """Record number of tool calls routed for a query."""
        record = self._safe_get(query_index)
        if record is None:
            return
        record.tool_calls = max(0, int(tool_calls_count))

    def record_response_time(
        self, query_index: Optional[int], elapsed_ms: float
    ) -> None:
        """Record end-to-end response time for a query."""
        record = self._safe_get(query_index)
        if record is None:
            return
        record.response_time_ms = max(0.0, float(elapsed_ms))

    def record_preference_collection(
        self,
        query_index: Optional[int],
        required: bool,
        success: Optional[bool] = None,
    ) -> None:
        """Track whether a query required preferences and if collection succeeded."""
        record = self._safe_get(query_index)
        if record is None:
            return

        record.required_preferences = bool(required)
        if required:
            record.preference_collection_success = success

    def record_conversation_length(self, turns: int) -> None:
        """Snapshot conversation length in user turns."""
        self._conversation_lengths.append(max(0, int(turns)))

    def generate_summary(self) -> Dict[str, Any]:
        """Generate analytics summary for current session."""
        intents = [r.intent for r in self._records if r.intent]
        intent_counts = Counter(intents)

        total_queries = len(self._records)
        total_tool_calls = sum(r.tool_calls for r in self._records)
        response_times = [
            r.response_time_ms for r in self._records if r.response_time_ms is not None
        ]

        pref_required = [r for r in self._records if r.required_preferences]
        pref_success = [
            r for r in pref_required if r.preference_collection_success is True
        ]

        avg_conversation_length = (
            sum(self._conversation_lengths) / len(self._conversation_lengths)
            if self._conversation_lengths
            else 0.0
        )

        avg_response_time_ms = (
            sum(response_times) / len(response_times) if response_times else 0.0
        )

        return {
            "session_id": self.session_id,
            "total_queries": total_queries,
            "intents_per_conversation": dict(intent_counts),
            "tool_calls_per_conversation": total_tool_calls,
            "average_conversation_length": round(avg_conversation_length, 2),
            "preference_collection_success_rate": (
                round(len(pref_success) / len(pref_required), 4)
                if pref_required
                else None
            ),
            "average_response_time_ms": round(avg_response_time_ms, 2),
            "uptime_seconds": round(time.time() - self.started_at, 2),
        }

    def export_json(self, file_path: str | Path) -> Path:
        """Export summary and per-query records to JSON."""
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "summary": self.generate_summary(),
            "records": [self._record_to_dict(record) for record in self._records],
        }

        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target

    def export_csv(self, file_path: str | Path) -> Path:
        """Export per-query records to CSV."""
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=[
                    "query_index",
                    "intent",
                    "tool_calls",
                    "response_time_ms",
                    "required_preferences",
                    "preference_collection_success",
                    "timestamp",
                ],
            )
            writer.writeheader()
            for record in self._records:
                writer.writerow(self._record_to_dict(record))

        return target

    def create_basic_visualization(self) -> str:
        """Return a simple text visualization of core metrics."""
        summary = self.generate_summary()
        intents = summary["intents_per_conversation"]
        response_ms = summary["average_response_time_ms"]
        tool_calls = summary["tool_calls_per_conversation"]

        lines = [
            "Conversation Analytics",
            f"Session: {summary['session_id']}",
            f"Total queries: {summary['total_queries']}",
            f"Tool calls: {tool_calls}",
            f"Avg response time: {response_ms} ms",
            "Intent distribution:",
        ]

        if not intents:
            lines.append("- (none)")
        else:
            max_count = max(intents.values())
            for intent, count in sorted(intents.items()):
                bar_len = int((count / max_count) * 20) if max_count else 0
                lines.append(f"- {intent:<24} {'#' * bar_len} ({count})")

        return "\n".join(lines)

    @property
    def records(self) -> List[QueryRecord]:
        """Expose records copy for test/debug usage."""
        return self._records.copy()

    def _safe_get(self, query_index: Optional[int]) -> Optional[QueryRecord]:
        if query_index is None:
            return None
        if query_index < 0 or query_index >= len(self._records):
            return None
        return self._records[query_index]

    @staticmethod
    def _record_to_dict(record: QueryRecord) -> Dict[str, Any]:
        return {
            "query_index": record.query_index,
            "intent": record.intent,
            "tool_calls": record.tool_calls,
            "response_time_ms": record.response_time_ms,
            "required_preferences": record.required_preferences,
            "preference_collection_success": record.preference_collection_success,
            "timestamp": record.timestamp,
        }
