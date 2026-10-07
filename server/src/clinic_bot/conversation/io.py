"""What the conversation layer needs from the running session.

Implemented by the pipeline layer, so nodes and handlers never touch frames.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pipecat.flows import NodeConfig

    from clinic_bot.conversation.result import UIPayload


class ConversationIO(Protocol):
    async def say(self, text: str) -> None:
        """Send fixed bot text. Not gated; it is added to the LLM context."""
        ...

    async def ui(self, payload: UIPayload) -> None:
        """Send a structured UI block to the widget."""
        ...

    async def add_user_context(self, text: str) -> None:
        """Append a user message to the LLM context without running the LLM."""
        ...

    async def set_node(self, config: NodeConfig) -> None:
        """Move the flow to another node outside a function call."""
        ...
