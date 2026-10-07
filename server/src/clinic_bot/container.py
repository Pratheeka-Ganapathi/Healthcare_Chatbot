"""Composition root: the only module that imports adapters (SPEC 16.6)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog
from fastapi import WebSocket
from pipecat.services.llm_service import LLMService
from pipecat.services.stt_service import STTService
from sqlalchemy.ext.asyncio import AsyncEngine

from clinic_bot.adapters.clock import FrozenClock, SystemClock
from clinic_bot.adapters.db.browser import SqlTableBrowser
from clinic_bot.adapters.db.engine import create_engine, session_factory
from clinic_bot.adapters.db.uow import SqlUnitOfWorkFactory
from clinic_bot.adapters.embeddings.fastembed_embedder import FastEmbedEmbedder
from clinic_bot.adapters.embeddings.litellm_embedder import LiteLLMEmbedder
from clinic_bot.adapters.health.cached import CachedHealthInfo
from clinic_bot.adapters.health.medlineplus import MedlinePlusProvider
from clinic_bot.adapters.llm.litellm_client import LiteLLMStructuredLLM
from clinic_bot.adapters.llm.pipecat_factory import PipecatLLMFactory
from clinic_bot.adapters.llm.retry import RetryingLLM
from clinic_bot.adapters.llm.stt_factory import GeminiSTTFactory
from clinic_bot.adapters.messages import JsonMessageCatalog
from clinic_bot.adapters.vector.build_index import PgDocIndexer
from clinic_bot.adapters.vector.pgvector_store import PgVectorStore
from clinic_bot.config import Role, Settings
from clinic_bot.conversation.functions import booking, doctors, faq, identity, safety, scheduling
from clinic_bot.conversation.nodes.catalog import standard_nodes
from clinic_bot.conversation.prompts import PromptLibrary
from clinic_bot.conversation.registry import FunctionRegistry, Services
from clinic_bot.domain.day_resolver import DayResolver
from clinic_bot.domain.enums import Specialty
from clinic_bot.domain.errors import Unavailable
from clinic_bot.domain.policies import (
    BookingPolicy,
    CancellationPolicy,
    FeePolicy,
    LockoutPolicy,
    SlotTimingPolicy,
    SpecialtyRules,
)
from clinic_bot.pipeline.builder import PipelineBuilder
from clinic_bot.pipeline.session import ChatSession, SessionDeps
from clinic_bot.pipeline.speech import SpeechDeps, SpeechSession
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.embeddings import Embedder
from clinic_bot.ports.health_info import HealthInfoProvider
from clinic_bot.ports.llm import StructuredLLM
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory
from clinic_bot.ports.vector_store import DocIndexer, VectorStore
from clinic_bot.seed.seeder import Seeder
from clinic_bot.services.booking import BookingService
from clinic_bot.services.callback import CallbackService
from clinic_bot.services.chat_summaries import ChatSummaryService
from clinic_bot.services.directory import DoctorDirectory, SpecialtyMapper
from clinic_bot.services.faq import FaqService
from clinic_bot.services.guardrails.llm_guard import LLMClassifierGuard
from clinic_bot.services.guardrails.pipeline import GuardPipeline
from clinic_bot.services.guardrails.regex_guard import RegexGuard
from clinic_bot.services.intake import Checklist, ChecklistRetriever
from clinic_bot.services.scheduling import SchedulingService
from clinic_bot.services.staff import StaffServices
from clinic_bot.services.staff.accounts import AccountService
from clinic_bot.services.staff.auth import LoginThrottle, StaffAuthService
from clinic_bot.services.staff.clinic import ClinicAdminService
from clinic_bot.services.staff.clinic_docs import ClinicDocService
from clinic_bot.services.staff.consultations import ConsultationService
from clinic_bot.services.staff.records import VisitRecords
from clinic_bot.services.transcripts import TranscriptWriter
from clinic_bot.services.verification import VerificationService

FUNCTION_MODULES = (identity, doctors, scheduling, booking, faq, safety)


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )


def build_embedder(settings: Settings) -> Embedder:
    if settings.embed_backend == "fastembed":
        return FastEmbedEmbedder(settings.embed_model)
    return LiteLLMEmbedder(settings.embed_backend, settings.embed_model, settings.embed_api_key())


async def _vector_index(
    settings: Settings, o: Overrides, embedder: Embedder, data: Path, engine: AsyncEngine
) -> tuple[VectorStore, DocIndexer]:
    if o.vector_store is not None:
        if o.doc_indexer is None:
            raise ValueError("a vector_store override needs a doc_indexer override")
        return o.vector_store, o.doc_indexer
    store = PgVectorStore(engine)
    await store.ensure_schema()
    return store, PgDocIndexer(data / "docs", store, embedder, settings.index_key)


def build_structured_llm(
    settings: Settings, role: Role, *, retries: int = 1, backoff_s: float = 1.0
) -> StructuredLLM:
    cfg = settings.role(role)
    inner = LiteLLMStructuredLLM(
        cfg.provider, cfg.model, settings.api_key(cfg.provider), cfg.temperature, cfg.max_tokens
    )
    return RetryingLLM(inner, retries, backoff_s)


@dataclass
class Overrides:
    """Test seams. Anything left ``None`` is built from settings."""

    clock: Clock | None = None
    embedder: Embedder | None = None
    vector_store: VectorStore | None = None  # needs ``doc_indexer`` too
    doc_indexer: DocIndexer | None = None
    health: HealthInfoProvider | None = None
    classifier_llm: StructuredLLM | None = None
    mapper_llm: StructuredLLM | None = None
    summary_llm: StructuredLLM | None = None
    main_llm_factory: Callable[[], LLMService] | None = None
    stt_factory: Callable[[], STTService] | None = None


class Container:
    def __init__(self) -> None:
        self.settings: Settings
        self.clock: Clock
        self.uow: UnitOfWorkFactory
        self.services: Services
        self.session_deps: SessionDeps
        self.speech_deps: SpeechDeps
        self.staff: StaffServices

    @classmethod
    async def build(cls, settings: Settings, overrides: Overrides | None = None) -> Container:
        """FastAPI lifespan startup. Seeds an empty database (or reseeds if configured)."""
        o = overrides or Overrides()
        self = cls()
        self.settings = settings
        self.clock = o.clock or (
            FrozenClock(settings.clinic_now) if settings.clinic_now else SystemClock()
        )
        engine = create_engine(settings.database_url)
        self._engine = engine
        data = Path(settings.data_dir)
        seeder = Seeder(engine, self.clock, data / "docs")
        await (seeder.reseed() if settings.reseed_on_start else seeder.ensure_seeded())
        factory = session_factory(engine)
        self.uow = SqlUnitOfWorkFactory(factory, self.clock)
        messages = JsonMessageCatalog(data / "messages.en.json")
        embedder = o.embedder or build_embedder(settings)
        store, indexer = await _vector_index(settings, o, embedder, data, engine)
        self._http = httpx.AsyncClient()
        health = o.health or CachedHealthInfo(
            MedlinePlusProvider(self._http), Path(settings.health_cache_dir)
        )
        self.services = await self._services(settings, o, embedder, store, health, data)
        self.staff = self._staff(settings, indexer, SqlTableBrowser(factory))
        await self._sync_index()
        await self._bootstrap_admin(settings)
        self.session_deps = self._session_deps(settings, o, messages)
        self.speech_deps = SpeechDeps(
            o.stt_factory or GeminiSTTFactory(settings).create,
            settings.allowed_origins,
            settings.stt_max_seconds,
        )
        self.transcripts.start()
        return self

    @classmethod
    async def for_tests(cls, settings: Settings, overrides: Overrides) -> Container:
        """Same build path as production, with fakes injected through ``overrides``."""
        return await cls.build(settings, overrides)

    async def _services(
        self,
        settings: Settings,
        o: Overrides,
        embedder: Embedder,
        store: VectorStore,
        health: HealthInfoProvider,
        data: Path,
    ) -> Services:
        uow, clock = self.uow, self.clock
        directory = DoctorDirectory(uow)
        await directory.reload()
        guide = (data / "docs" / "specialty_guide.md").read_text(encoding="utf-8")
        mapper_llm = o.mapper_llm or build_structured_llm(settings, "mapper")
        general = Checklist.parse(
            (data / "docs" / "intake" / "general.md").read_text(encoding="utf-8")
        )
        self.transcripts = TranscriptWriter(uow)
        # Off the turn path, so it can wait out a per-minute rate limit (20s, then 40s).
        summary_llm = o.summary_llm or build_structured_llm(
            settings, "summary", retries=2, backoff_s=20.0
        )
        self.summaries = ChatSummaryService(summary_llm, uow, clock)
        self.guards = GuardPipeline(
            RegexGuard(),
            LLMClassifierGuard(o.classifier_llm or build_structured_llm(settings, "classifier")),
            settings.classifier_timeout_s,
        )
        return Services(
            verification=VerificationService(uow, clock, LockoutPolicy()),
            directory=directory,
            mapper=SpecialtyMapper(mapper_llm, guide, SpecialtyRules(), list(Specialty)),
            scheduling=SchedulingService(uow, clock, DayResolver(), SlotTimingPolicy(), directory),
            booking=BookingService(uow, clock, BookingPolicy(), FeePolicy(), CancellationPolicy()),
            checklists=ChecklistRetriever(embedder, store, general, settings.checklist_cutoff),
            faq=FaqService(embedder, store, health, directory, settings.faq_cutoff),
            callbacks=CallbackService(uow, clock),
            regex=self.guards.regex,
        )

    def _staff(
        self, settings: Settings, indexer: DocIndexer, tables: SqlTableBrowser
    ) -> StaffServices:
        uow, clock, directory = self.uow, self.clock, self.services.directory
        throttle = LoginThrottle(LockoutPolicy())
        return StaffServices(
            auth=StaffAuthService(uow, clock, throttle, settings.staff_session_hours),
            accounts=AccountService(uow, clock),
            records=VisitRecords(uow, clock, directory),
            consultations=ConsultationService(uow, clock, directory),
            clinic=ClinicAdminService(uow, clock, directory, tables),
            docs=ClinicDocService(uow, clock, indexer),
            tables=tables,
            directory=directory,
            clock=clock,
        )

    async def _sync_index(self) -> None:
        """Build the index, or rebuild it if the docs or the model changed. A hosted embedder
        can be rate limited at startup: the server then starts with the index it has, and
        the next start or admin save rebuilds it."""
        try:
            await self.staff.docs.sync_index()
        except Unavailable as exc:
            structlog.get_logger(__name__).warning("index_sync_failed", reason=str(exc))

    async def _bootstrap_admin(self, settings: Settings) -> None:
        """First admin from ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` (SPEC 17.1). A bad value
        stops startup, so a misconfigured deploy fails loudly."""
        if settings.admin_email and settings.admin_password:
            password = settings.admin_password.get_secret_value()
            await self.staff.accounts.ensure_admin(
                settings.admin_email, settings.admin_name, password
            )

    def _session_deps(
        self, settings: Settings, o: Overrides, messages: JsonMessageCatalog
    ) -> SessionDeps:
        registry = FunctionRegistry.from_modules(*FUNCTION_MODULES)
        nodes = standard_nodes(PromptLibrary("text"), registry, messages, self.services.directory)
        llm_factory = o.main_llm_factory or PipecatLLMFactory(settings).create_main
        return SessionDeps(
            builder=PipelineBuilder(
                self.guards, settings.max_input_chars, settings.allowed_origins
            ),
            llm_factory=llm_factory,
            services=self.services,
            messages=messages,
            nodes=nodes,
            transcripts=self.transcripts,
            summaries=self.summaries,
            clock=self.clock,
        )

    def new_session(self, websocket: WebSocket) -> ChatSession:
        return ChatSession(websocket, self.session_deps)

    def new_speech_session(self, websocket: WebSocket) -> SpeechSession:
        return SpeechSession(websocket, self.speech_deps)

    async def aclose(self) -> None:
        """FastAPI lifespan shutdown: finish summaries, flush transcripts, close clients."""
        await self.summaries.aclose()
        await self.transcripts.aclose()
        await self._http.aclose()
        await self._engine.dispose()
