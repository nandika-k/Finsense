"""Tool call optimization utilities for conversational execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from agent.tool_router import ToolCall


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class ToolCache:
    """Simple in-memory cache with TTL and hit/miss tracking."""

    def __init__(
        self,
        default_ttl_seconds: int = 300,
        now_fn: Optional[Callable[[], float]] = None,
    ):
        self.default_ttl_seconds = default_ttl_seconds
        self._now_fn = now_fn or time.time
        self._entries: Dict[str, _CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    def generate_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Generate a deterministic cache key for tool call parameters."""
        normalized = self._normalize(arguments)
        payload = {
            "tool_name": tool_name,
            "arguments": normalized,
        }
        serialized = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.expires_at <= self._now_fn():
            del self._entries[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        self._entries[key] = _CacheEntry(value=value, expires_at=self._now_fn() + ttl)

    def clear(self) -> None:
        self._entries.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> Dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._entries),
        }

    def _normalize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._normalize(value[k]) for k in sorted(value)}
        if isinstance(value, list):
            return [self._normalize(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self._normalize(v) for v in value)
        if isinstance(value, set):
            return sorted(self._normalize(v) for v in value)
        return value


class ToolOptimizer:
    """Optimizes tool execution via caching, batching hints, and parallel runs."""

    _BATCHABLE_ARGS = {
        "get_stock_details": "ticker",
        "get_stock_price": "ticker",
    }

    def __init__(
        self, cache: Optional[ToolCache] = None, default_ttl_seconds: int = 300
    ):
        self.cache = cache or ToolCache(default_ttl_seconds=default_ttl_seconds)
        self.default_ttl_seconds = default_ttl_seconds

    def detect_batch_requests(
        self, tool_calls: Sequence[ToolCall]
    ) -> List[Dict[str, Any]]:
        """Detect groups of similar calls that could be batched by the backend."""
        grouped: Dict[tuple[str, str], List[ToolCall]] = {}

        for call in tool_calls:
            batch_arg = self._BATCHABLE_ARGS.get(call.tool_name)
            if not batch_arg:
                continue

            arguments_wo_batch = {
                k: v for k, v in call.arguments.items() if k != batch_arg
            }
            base_key = json.dumps(
                self.cache._normalize(arguments_wo_batch), sort_keys=True, default=str
            )
            grouped.setdefault((call.tool_name, base_key), []).append(call)

        batches: List[Dict[str, Any]] = []
        for (tool_name, _), calls in grouped.items():
            if len(calls) < 2:
                continue
            batch_arg = self._BATCHABLE_ARGS[tool_name]
            batch_values = [
                call.arguments.get(batch_arg)
                for call in calls
                if call.arguments.get(batch_arg)
            ]
            if len(batch_values) < 2:
                continue
            batches.append(
                {
                    "tool_name": tool_name,
                    "batch_argument": batch_arg,
                    "values": batch_values,
                    "calls": calls,
                }
            )

        return batches

    async def execute_tool_calls(
        self,
        tool_calls: Sequence[ToolCall],
        invoke_tool: Callable[[ToolCall], Awaitable[Any]],
    ) -> Dict[str, Any]:
        """Execute tool calls with sequential execution for same-server calls.
        
        MCP stdio transport doesn't support concurrent requests on the same connection,
        so tools targeting the same server must be executed sequentially to avoid
        "readuntil() called while another coroutine is already waiting" errors.
        Tools targeting different servers can still run in parallel.
        """
        results: Dict[str, Any] = {}
        
        # Group tool calls by server to avoid concurrent MCP connection access
        server_groups: Dict[str, List[ToolCall]] = {}
        for call in tool_calls:
            server = getattr(call, 'server', 'default')
            server_groups.setdefault(server, []).append(call)

        async def execute_one(call: ToolCall) -> tuple[str, Any]:
            cache_key = self.cache.generate_key(call.tool_name, call.arguments)
            cached = self.cache.get(cache_key)
            if cached is not None:
                return call.tool_name, cached

            result = await invoke_tool(call)
            if not self._is_error(result):
                self.cache.set(
                    cache_key,
                    result,
                    ttl_seconds=self._cache_ttl_for_tool(call.tool_name),
                )
            return call.tool_name, result

        async def execute_server_group(calls: List[ToolCall]) -> List[tuple[str, Any]]:
            """Execute all calls for one server sequentially."""
            group_results = []
            for call in calls:
                result = await execute_one(call)
                group_results.append(result)
            return group_results

        # Execute server groups in parallel, but calls within each group sequentially
        group_tasks = [execute_server_group(calls) for calls in server_groups.values()]
        all_group_results = await asyncio.gather(*group_tasks)
        
        for group_results in all_group_results:
            for tool_name, result in group_results:
                results[tool_name] = result
        return results

    def _cache_ttl_for_tool(self, tool_name: str) -> int:
        if tool_name == "get_market_indices":
            return 60
        return self.default_ttl_seconds

    @staticmethod
    def _is_error(value: Any) -> bool:
        return isinstance(value, dict) and bool(value.get("error"))
