"""answer_faq: clinic docs, doctor directory or MedlinePlus; the node does not change."""

from __future__ import annotations

from pydantic import BaseModel, Field

from clinic_bot.conversation.registry import HandlerContext, llm_function
from clinic_bot.conversation.result import ToolResult
from clinic_bot.conversation.views import doctor_data
from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.domain.errors import ErrorCode, NotFound


def _health_topics_allowed(question: str, ctx: HandlerContext) -> bool:
    """MedlinePlus only when the classifier really said NONE and no medication pattern
    matches the question, so a medicine question can never reach it (SPEC 6.5, 7)."""
    verdict = ctx.state.verdict
    if verdict is None or not verdict.done():
        return False
    result = verdict.result()
    classified_none = result.source == "classifier" and result.label is GuardrailLabel.NONE
    return classified_none and ctx.services.regex.precheck(question).label is GuardrailLabel.NONE


class FaqArgs(BaseModel):
    question: str = Field(description="The patient's question, in English")


@llm_function(
    name="answer_faq",
    description=(
        "Answer a question about the clinic (hours, location, insurance, services, test "
        "preparation, doctors and fees) or a general health topic such as what a test is."
    ),
    args=FaqArgs,
)
async def answer_faq(args: FaqArgs, ctx: HandlerContext) -> ToolResult:
    try:
        answer = await ctx.services.faq.answer(
            args.question, health_topics_allowed=_health_topics_allowed(args.question, ctx)
        )
    except NotFound:
        await ctx.io.say(ctx.messages.get("faq.no_match"))
        return ToolResult.failure(ErrorCode.NO_MATCH, silent=True)
    data: dict[str, object] = {
        "source": answer.source,
        "use_only_this": "Answer only from this. If it doesn't answer the question, say you "
        "don't know and offer the front desk. Then say where the conversation was.",
    }
    if answer.doctors:
        data["doctors"] = [doctor_data(d, with_fees=answer.fees_asked) for d in answer.doctors]
    if answer.passages:
        data["passages"] = list(answer.passages)
    if answer.url:
        data["source_link"] = answer.url
        data["link_rule"] = "End your answer with: Source: <source_link>"
    return ToolResult.success(data)
