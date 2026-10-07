"""The standard set of conversation nodes, ready for a NodeFactory."""

from __future__ import annotations

from clinic_bot.conversation.nodes.base import BaseNode
from clinic_bot.conversation.nodes.booked import BookedNode
from clinic_bot.conversation.nodes.cancel import CancelConfirmNode, CancelListNode
from clinic_bot.conversation.nodes.confirm import ConfirmNode
from clinic_bot.conversation.nodes.factory import NodeFactory
from clinic_bot.conversation.nodes.faq_only import FaqOnlyNode
from clinic_bot.conversation.nodes.greet import GreetNode
from clinic_bot.conversation.nodes.handoff import HandoffNode
from clinic_bot.conversation.nodes.pick_slot import PickSlotNode
from clinic_bot.conversation.nodes.pre_talk import PreTalkNode
from clinic_bot.conversation.nodes.router import RouterNode
from clinic_bot.conversation.nodes.suggest_doctor import SuggestDoctorNode
from clinic_bot.conversation.nodes.verify import VerifyNode
from clinic_bot.conversation.prompts import PromptLibrary
from clinic_bot.conversation.registry import FunctionRegistry
from clinic_bot.ports.messages import MessageCatalog
from clinic_bot.services.directory import DoctorDirectory

PLAIN_NODES: tuple[type[BaseNode], ...] = (
    GreetNode,
    VerifyNode,
    RouterNode,
    PreTalkNode,
    ConfirmNode,
    BookedNode,
    CancelListNode,
    CancelConfirmNode,
    FaqOnlyNode,
    HandoffNode,
)


def standard_nodes(
    prompts: PromptLibrary,
    registry: FunctionRegistry,
    messages: MessageCatalog,
    directory: DoctorDirectory,
) -> NodeFactory:
    nodes: list[BaseNode] = [cls(prompts, registry, messages) for cls in PLAIN_NODES]
    nodes += [
        SuggestDoctorNode(prompts, registry, messages, directory),
        PickSlotNode(prompts, registry, messages, directory),
    ]
    return NodeFactory(nodes)
