"""All runtime configuration, read from the environment (SPEC 3)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Provider = Literal["google", "openai", "anthropic"]
Role = Literal["main", "classifier", "mapper", "summary"]

SERVER_ROOT = Path(__file__).resolve().parents[2]

# Demo defaults. Check current free-tier model ids in Google AI Studio and override via env.
DEFAULT_MAIN_MODEL = "gemini-3.6-flash"
DEFAULT_CLASSIFIER_MODEL = "gemini-3.5-flash-lite"
DEFAULT_STT_MODEL = "gemini-3.5-transcribe-live"
# RAG cut-offs per embedding backend, (FAQ, symptom checklist), on top-1 cosine. Models score
# differently (Gemini rates unrelated text far higher than MiniLM), so each needs its own.
# Measured with eval/tune_rag_threshold.py. Gemini's scores overlap, so its cut-off keeps every
# question the docs answer (refusing "what are your timings" is the worse error). openai is untuned.
DEFAULT_RAG_THRESHOLDS: dict[str, tuple[float, float]] = {
    "fastembed": (0.35, 0.35),
    "gemini": (0.60, 0.60),
    "openai": (0.35, 0.35),
}


class RoleConfig(BaseModel):
    provider: Provider
    model: str
    temperature: float
    max_tokens: int


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: Provider = "google"
    main_model: str = DEFAULT_MAIN_MODEL
    classifier_model: str = DEFAULT_CLASSIFIER_MODEL
    mapper_model: str | None = None  # defaults to main_model
    summary_model: str | None = None  # defaults to classifier_model (spares the main quota)

    main_provider: Provider | None = None
    classifier_provider: Provider | None = None
    mapper_provider: Provider | None = None
    summary_provider: Provider | None = None

    main_temperature: float = 0.3
    classifier_temperature: float = 0.0
    mapper_temperature: float = 0.0
    summary_temperature: float = 0.2
    main_max_tokens: int = 300
    classifier_max_tokens: int = 150
    mapper_max_tokens: int = 150
    summary_max_tokens: int = 250

    google_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Voice input (SPEC 10.1): Gemini Live transcription with the Google key; replies are
    # read aloud by the browser, so there is no server-side TTS.
    stt_model: str = DEFAULT_STT_MODEL
    stt_max_seconds: int = 60

    embed_backend: Literal["fastembed", "openai", "gemini"] = "fastembed"
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embed_api_key: str | None = None  # own key (own quota) for hosted embeddings
    faq_threshold: float | None = None  # override DEFAULT_RAG_THRESHOLDS[embed_backend]
    checklist_threshold: float | None = None

    clinic_now: datetime | None = None
    classifier_timeout_s: float = 4.0
    max_input_chars: int = 500
    # NoDecode: ``_split_origins`` parses the env string (comma-separated or a JSON list).
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Staff portal (SPEC 17): its own origin, the first admin, session length.
    staff_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5174", "http://127.0.0.1:5174"]
    )
    admin_email: str | None = None
    admin_password: SecretStr | None = None
    admin_name: str = "Clinic admin"
    staff_session_hours: int = 12

    database_url: str = "postgresql+asyncpg://clinic:clinic@localhost:5432/clinic"
    reseed_on_start: bool = False  # False: seed only an empty database (SPEC 9.1)
    health_cache_dir: str = str(SERVER_ROOT / ".cache" / "medlineplus")
    data_dir: str = str(SERVER_ROOT / "data")
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: str) -> str:
        """Hosts hand out ``postgres://…?sslmode=require``; asyncpg wants its own forms."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                value = "postgresql+asyncpg://" + value[len(prefix) :]
        return value.replace("sslmode=", "ssl=")

    @field_validator("allowed_origins", "staff_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Env gives a string: a JSON list or comma-separated origins."""
        if not isinstance(value, str):
            return value
        if value.strip().startswith("["):
            return json.loads(value)
        return [v.strip() for v in value.split(",") if v.strip()]

    def role(self, role: Role) -> RoleConfig:
        provider = {
            "main": self.main_provider,
            "classifier": self.classifier_provider,
            "mapper": self.mapper_provider,
            "summary": self.summary_provider,
        }[role] or self.llm_provider
        model = {
            "main": self.main_model,
            "classifier": self.classifier_model,
            "mapper": self.mapper_model or self.main_model,
            "summary": self.summary_model or self.classifier_model,
        }[role]
        return RoleConfig(
            provider=provider,
            model=model,
            temperature=getattr(self, f"{role}_temperature"),
            max_tokens=getattr(self, f"{role}_max_tokens"),
        )

    def api_key(self, provider: Provider) -> str:
        key = {
            "google": self.google_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }[provider]
        if not key:
            raise RuntimeError(f"Missing API key for provider '{provider}'")
        return key

    def embedding_key(self) -> str:
        """``EMBED_API_KEY`` if set, else the matching LLM provider's key."""
        if self.embed_api_key:
            return self.embed_api_key
        provider: Provider = "google" if self.embed_backend == "gemini" else "openai"
        return self.api_key(provider)

    @property
    def faq_cutoff(self) -> float:
        """Below this top-1 score ``answer_faq`` answers NO_MATCH (SPEC 7)."""
        default, _ = DEFAULT_RAG_THRESHOLDS[self.embed_backend]
        return default if self.faq_threshold is None else self.faq_threshold

    @property
    def checklist_cutoff(self) -> float:
        """Below this top-1 score pre-talk uses the general checklist (SPEC 4.4)."""
        _, default = DEFAULT_RAG_THRESHOLDS[self.embed_backend]
        return default if self.checklist_threshold is None else self.checklist_threshold

    @property
    def index_key(self) -> str:
        """Embedding backend + model the RAG index is built with, so a change rebuilds it."""
        return f"{self.embed_backend}:{self.embed_model}"
