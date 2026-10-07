"""NodeFactory: node name → node object, and node → Flows config for one session."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from pipecat.flows import NodeConfig

from clinic_bot.conversation.nodes.base import BaseNode

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext

TERMINAL_NODES = frozenset({"handoff"})


class NodeFactory:
    def __init__(self, nodes: Iterable[BaseNode]) -> None:
        self._nodes = {node.name: node for node in nodes}

    def names(self) -> tuple[str, ...]:
        return tuple(self._nodes)

    async def create(self, name: str, ctx: HandlerContext) -> NodeConfig:
        """Run the node's async ``prepare`` then build its config. Raises KeyError."""
        node = self._nodes[name]
        await node.prepare(ctx)
        return node.build(ctx)
