"""``answer_faq`` routing: clinic docs first, MedlinePlus for general health topics."""

from __future__ import annotations

import re
from dataclasses import dataclass

from clinic_bot.domain.entities import Doctor
from clinic_bot.domain.enums import Specialty
from clinic_bot.domain.errors import ErrorCode, NotFound
from clinic_bot.ports.embeddings import Embedder
from clinic_bot.ports.health_info import HealthInfoProvider
from clinic_bot.ports.vector_store import VectorStore
from clinic_bot.services.directory import DoctorDirectory

FAQ_THRESHOLD = 0.35  # for the default fastembed model; config sets it per model
FAQ_TOP_K = 3
_HEALTH_TOPIC_WORDS = re.compile(
    r"\b(test|tests|scan|x-?ray|mri|ct|ultrasound|ecg|hba1c|thyroid|cholesterol|lipid|"
    r"diabetes|hypertension|blood pressure|anaemia|anemia|asthma|migraine|eczema|psoriasis|"
    r"arthritis|sinusitis|tonsillitis|infection|vaccine|vaccination|condition|disease|"
    r"syndrome|procedure|biopsy|endoscopy|colonoscopy|what is|what are|what does)\b",
    re.IGNORECASE,
)

_DOCTOR_QUESTION = re.compile(
    r"\b(dr\.?|doctors?|fees?|cost|costs|charges?|price|specialists?|physician|"
    r"dermatolog\w*|orthop\w*|p(a)?ediatric\w*|gyn(a)?ecolog\w*|ent)\b",
    re.IGNORECASE,
)
_FEE_QUESTION = re.compile(
    r"\b(fees?|cost|costs|charges?|price|prices|pay|how much|amount|rates?)\b", re.IGNORECASE
)
_DOCTOR_NAME = re.compile(r"\bdr\.?\s+([a-z]+(?:\s+[a-z]{1,2}\b)?)", re.IGNORECASE)
_SPECIALTY_WORDS = {
    Specialty.DERMATOLOGY: ("skin", "dermatolog"),
    Specialty.ORTHOPAEDICS: ("orthop", "bone", "joint"),
    Specialty.PAEDIATRICS: ("paediatric", "pediatric", "child", "kids"),
    Specialty.GYNAECOLOGY: ("gynaecolog", "gynecolog", "women"),
    Specialty.ENT: ("ent ", " ent", "ear", "nose", "throat"),
    Specialty.GENERAL_MEDICINE: ("general", "physician"),
}


@dataclass(frozen=True, slots=True)
class FaqAnswer:
    source: str  # "clinic" | "medlineplus"
    passages: tuple[str, ...]
    url: str | None = None
    title: str | None = None
    doctors: tuple[Doctor, ...] = ()
    fees_asked: bool = False  # fees are shown in chat only when the patient asked about cost


class FaqService:
    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        health: HealthInfoProvider,
        directory: DoctorDirectory,
        threshold: float = FAQ_THRESHOLD,
    ) -> None:
        self._embedder, self._store, self._health = embedder, store, health
        self._directory, self._threshold = directory, threshold

    async def answer(self, question: str, *, health_topics_allowed: bool) -> FaqAnswer:
        """Doctor/day/fee questions → doctor directory (never RAG); then clinic docs; then
        MedlinePlus for general health topics, only when ``health_topics_allowed`` (the
        turn's classifier label was a real NONE). Raises ``NotFound(NO_MATCH)``.
        """
        if _DOCTOR_QUESTION.search(question):
            return FaqAnswer(
                source="doctors",
                passages=(),
                doctors=self._doctors_for(question),
                fees_asked=bool(_FEE_QUESTION.search(question)),
            )
        [vector] = await self._embedder.embed([question])
        hits = await self._store.query(vector, k=FAQ_TOP_K, kinds=["faq", "prep"])
        if hits and hits[0].score >= self._threshold:
            kept = tuple(h.chunk.text for h in hits if h.score >= self._threshold)
            return FaqAnswer(source="clinic", passages=kept)
        if health_topics_allowed and _HEALTH_TOPIC_WORDS.search(question):
            topic = await self._health.search(question)
            if topic is not None:
                return FaqAnswer(
                    source="medlineplus",
                    passages=(topic.summary,),
                    url=topic.url,
                    title=topic.title,
                )
        raise NotFound(ErrorCode.NO_MATCH)

    def _doctors_for(self, question: str) -> tuple[Doctor, ...]:
        lowered = f" {question.lower()} "
        specialty = next(
            (sp for sp, words in _SPECIALTY_WORDS.items() if any(w in lowered for w in words)), None
        )
        name_match = _DOCTOR_NAME.search(question)
        name = f"Dr. {name_match.group(1)}" if name_match else None
        try:
            return self._directory.search(None if name else specialty, name)
        except NotFound:
            return self._directory.all()

    async def prep_for(self, specialty_label: str) -> str | None:
        """The authored prep paragraph for a specialty consultation, if any."""
        wanted = specialty_label.lower()
        [vector] = await self._embedder.embed([f"Preparing for a {wanted} consultation"])
        hits = await self._store.query(vector, k=3, kinds=["prep"])
        for hit in hits:
            section = hit.chunk.section.lower()
            if section.startswith("preparing for") and wanted in section:
                return hit.chunk.text
        return None
