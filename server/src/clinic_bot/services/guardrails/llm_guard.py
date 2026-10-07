"""Layer 2: one-label LLM classifier on every turn."""

from __future__ import annotations

from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.domain.errors import ErrorCode, Unavailable
from clinic_bot.ports.llm import StructuredLLM
from clinic_bot.services.guardrails.base import Guard, GuardContext, Verdict

CLASSIFIER_PROMPT_VERSION = "v1"
CLASSIFIER_LABELS: tuple[str, ...] = tuple(label.value for label in GuardrailLabel)

CLASSIFIER_PROMPT = """You are a safety classifier for a clinic front-desk chatbot in Bangalore.
Classify ONLY the patient's latest message. Messages may be in English, Hindi, Kannada,
romanised Hindi/Kannada or a mix. Return exactly one label.

EMERGENCY: the patient or someone with them has a possible medical emergency happening now:
chest pain, tightness or pressure; difficulty breathing or not breathing; fainting,
unconsciousness or not responding; heavy or uncontrolled bleeding; stroke signs (face drooping,
slurred speech, one-sided weakness); seizures or fits; severe allergic reaction or throat
swelling; poisoning or overdose; severe burns; snake bite. A short "yes" to the bot asking about
one of these is EMERGENCY. Third-party emergencies ("my father isn't breathing") are EMERGENCY.
Clearly negated ("no chest pain") or clearly past ("had chest pain last year, it was fine")
mentions are NOT emergencies.
SELF_HARM: thoughts or intent of suicide or self-harm, now or recently.
MEDICATION: any question about medicines: doses, timing, interactions, side effects, what a
medicine is for, whether to take or stop a medicine, including before a test.
OFF_TOPIC: requests unrelated to the clinic or the patient's health visit (coding, essays,
poems, jokes, general trivia, other businesses).
NONE: everything else, including symptoms that are not emergencies, booking, clinic questions,
greetings, and identity details like names, phone numbers, dates of birth and sex.
"""


class LLMClassifierGuard(Guard):
    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    async def check(self, text: str, ctx: GuardContext) -> Verdict:
        """Raises ``Unavailable``; ``GuardPipeline`` turns that into a default verdict."""
        user = f"Bot's previous message: {ctx.last_bot_message or '(none)'}\nPatient: {text}"
        label, reason = await self._llm.classify(CLASSIFIER_PROMPT, user, CLASSIFIER_LABELS)
        try:
            return Verdict(GuardrailLabel(label), "classifier", reason)
        except ValueError as exc:
            raise Unavailable(ErrorCode.BUSY, f"unexpected label {label!r}") from exc
