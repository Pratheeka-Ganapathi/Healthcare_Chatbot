"""LiteLLM-backed StructuredLLM for out-of-pipeline calls (classifier, mapper, summaries)."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

import litellm
import openai

from clinic_bot.domain.errors import ErrorCode, Unavailable

# Provider name → LiteLLM model prefix. Adding a provider is one entry here.
_LITELLM_PREFIX: dict[str, str] = {
    "google": "gemini/",
    "openai": "openai/",
    "anthropic": "anthropic/",
}

litellm.suppress_debug_info = True

_LABEL_FIELD = re.compile(r'"label"\s*:\s*"([^"]+)"')


def parse_label(content: str) -> tuple[str, str]:
    """``(label, reason)`` from the JSON reply. The label comes first, so a reply cut off
    at the token limit (a long reason) still yields it."""
    try:
        data = json.loads(content)
        return str(data["label"]), str(data.get("reason", ""))
    except (ValueError, KeyError, TypeError):
        match = _LABEL_FIELD.search(content)
        if match is None:
            raise Unavailable(ErrorCode.BUSY, "unparseable classifier output") from None
        return match.group(1), ""


class LiteLLMStructuredLLM:
    def __init__(
        self, provider: str, model: str, api_key: str, temperature: float, max_tokens: int
    ) -> None:
        self._model = _LITELLM_PREFIX[provider] + model
        self._api_key, self._temperature, self._max_tokens = api_key, temperature, max_tokens

    async def classify(self, system: str, user: str, labels: Sequence[str]) -> tuple[str, str]:
        schema = {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": list(labels)},
                "reason": {"type": "string"},
            },
            "required": ["label", "reason"],
            "additionalProperties": False,
        }
        instructions = (
            f"{system}\n\nRespond with JSON only: "
            f'{{"label": one of {list(labels)}, "reason": "<one short line>"}}'
        )
        label, reason = parse_label(await self._complete(instructions, user, schema))
        if label not in labels:
            raise Unavailable(ErrorCode.BUSY, f"label outside enum: {label}")
        return label, reason

    async def write(self, system: str, user: str) -> str:
        text = (await self._complete(system, user, None)).strip()
        if not text:
            raise Unavailable(ErrorCode.BUSY, "empty completion")
        return text

    async def _complete(self, system: str, user: str, schema: dict[str, Any] | None) -> str:
        extra: dict[str, Any] = {}
        if schema is not None:
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "label", "schema": schema, "strict": True},
            }
        try:
            response = await litellm.acompletion(
                model=self._model,
                api_key=self._api_key,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                **extra,
            )
        except litellm.RateLimitError as exc:
            raise Unavailable(ErrorCode.BUSY, "rate limited", retryable=True) from exc
        except openai.OpenAIError as exc:  # base of every LiteLLM API exception
            raise Unavailable(ErrorCode.BUSY, type(exc).__name__) from exc
        return str(response.choices[0].message.content or "")
