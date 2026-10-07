"""Role → Pipecat LLM service, through a registry of provider builders."""

from __future__ import annotations

from collections.abc import Callable

from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import LLMService
from pipecat.services.openai.llm import OpenAILLMService

from clinic_bot.config import RoleConfig, Settings


def _google(cfg: RoleConfig, key: str) -> LLMService:
    return GoogleLLMService(
        api_key=key,
        settings=GoogleLLMService.Settings(
            model=cfg.model, temperature=cfg.temperature, max_tokens=cfg.max_tokens
        ),
    )


def _openai(cfg: RoleConfig, key: str) -> LLMService:
    return OpenAILLMService(
        api_key=key,
        settings=OpenAILLMService.Settings(
            model=cfg.model, temperature=cfg.temperature, max_tokens=cfg.max_tokens
        ),
    )


def _anthropic(cfg: RoleConfig, key: str) -> LLMService:
    return AnthropicLLMService(
        api_key=key,
        settings=AnthropicLLMService.Settings(
            model=cfg.model, temperature=cfg.temperature, max_tokens=cfg.max_tokens
        ),
    )


_BUILDERS: dict[str, Callable[[RoleConfig, str], LLMService]] = {
    "google": _google,
    "openai": _openai,
    "anthropic": _anthropic,
}


class PipecatLLMFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_main(self) -> LLMService:
        cfg = self._settings.role("main")
        return _BUILDERS[cfg.provider](cfg, self._settings.api_key(cfg.provider))
