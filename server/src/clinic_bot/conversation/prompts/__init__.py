"""Prompt files and the library that loads them."""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent

SUMMARY_PROMPT = (
    "Summarise the conversation so far in two or three sentences for your own memory: "
    "what the patient wanted, what was booked or cancelled, and anything still pending. "
    "Do not include phone numbers or dates of birth."
)


class PromptLibrary:
    def __init__(self, channel: str = "text") -> None:
        self._role = (_DIR / "role.md").read_text(encoding="utf-8").strip()
        self._channel = (_DIR / f"{channel}.md").read_text(encoding="utf-8").strip()

    def role(self) -> str:
        return f"{self._role}\n\n{self._channel}"
