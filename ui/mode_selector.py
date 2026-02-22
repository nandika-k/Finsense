"""Mode switching interface for chat vs batch workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AppMode(str, Enum):
    CHAT = "chat"
    BATCH = "batch"


@dataclass(frozen=True)
class ModeSwitchResult:
    mode: AppMode
    switched: bool
    message: str


def mode_selection_prompt() -> str:
    """Return the startup mode selection prompt."""
    return (
        "Welcome to Finsense! Choose your mode:\n"
        "1. Chat Mode - Ask questions and get instant answers\n"
        "2. Research Mode - Get comprehensive sector analysis\n\n"
        "Enter 1 or 2:"
    )


def parse_mode_selection(user_input: str, default: AppMode = AppMode.CHAT) -> AppMode:
    """
    Parse a startup mode choice.

    Accepted values:
    - `1`, `chat`, `c`
    - `2`, `research`, `batch`, `b`
    Returns default mode for unrecognized input.
    """
    value = (user_input or "").strip().lower()

    if value in {"1", "chat", "c"}:
        return AppMode.CHAT
    if value in {"2", "research", "batch", "b"}:
        return AppMode.BATCH
    return default


def switch_to_conversational(current_mode: AppMode) -> ModeSwitchResult:
    """Switch to conversational mode."""
    if current_mode == AppMode.CHAT:
        return ModeSwitchResult(
            mode=AppMode.CHAT,
            switched=False,
            message="Already in Chat Mode.",
        )

    return ModeSwitchResult(
        mode=AppMode.CHAT,
        switched=True,
        message="Switched to Chat Mode.",
    )


def switch_to_batch(current_mode: AppMode) -> ModeSwitchResult:
    """Switch to batch research mode."""
    if current_mode == AppMode.BATCH:
        return ModeSwitchResult(
            mode=AppMode.BATCH,
            switched=False,
            message="Already in Research Mode.",
        )

    return ModeSwitchResult(
        mode=AppMode.BATCH,
        switched=True,
        message="Switched to Research Mode.",
    )


def mode_specific_instructions(mode: AppMode) -> str:
    """Return concise usage hints for the active mode."""
    if mode == AppMode.CHAT:
        return (
            "Chat Mode: Ask focused questions like 'How is tech performing?' or "
            "'Show risk for healthcare'. Use /batch to switch modes."
        )

    return (
        "Research Mode: Run comprehensive sector analysis with your preferences. "
        "Use /chat to switch modes."
    )


def handle_mode_switch_command(user_input: str, current_mode: AppMode) -> Optional[ModeSwitchResult]:
    """
    Handle mid-conversation mode switch commands.

    Supported commands:
    - `/chat`, `switch to chat`, `chat mode`
    - `/batch`, `/research`, `switch to batch`, `research mode`

    Returns None when no mode switch command is detected.
    """
    value = (user_input or "").strip().lower()

    chat_commands = {"/chat", "switch to chat", "chat mode"}
    batch_commands = {"/batch", "/research", "switch to batch", "research mode", "batch mode"}

    if value in chat_commands:
        return switch_to_conversational(current_mode)
    if value in batch_commands:
        return switch_to_batch(current_mode)
    return None
