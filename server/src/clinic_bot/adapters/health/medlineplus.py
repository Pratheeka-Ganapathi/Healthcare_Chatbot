"""MedlinePlus health-topics free-text search (wsearch.nlm.nih.gov)."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

import httpx

from clinic_bot.ports.health_info import HealthTopic

ENDPOINT = "https://wsearch.nlm.nih.gov/ws/query"
_TAG = re.compile(r"<[^>]+>")
_SENTENCE = re.compile(r"(?<=[.!])\s+")
MAX_SENTENCES = 3
_QUESTION_WORDS = re.compile(
    r"^(please\s+)?(tell\s+me\s+)?(what|whats|what's)\s+(is|are|does)\s+(an?\s+|the\s+)?"
    r"|\b(mean|means|for)\s*\??$|\?+$",
    re.IGNORECASE,
)


def topic_terms(query: str) -> str:
    """'What is an HbA1c test?' → 'HbA1c test'. Topic search ranks bare terms best."""
    return _QUESTION_WORDS.sub("", query.strip()).strip() or query


class MedlinePlusProvider:
    def __init__(self, client: httpx.AsyncClient, timeout_s: float = 3.0) -> None:
        self._client, self._timeout = client, timeout_s

    async def search(self, query: str) -> HealthTopic | None:
        """Top health topic for ``query``; ``None`` on no result, timeout or HTTP error."""
        try:
            response = await self._client.get(
                ENDPOINT,
                params={"db": "healthTopics", "term": topic_terms(query), "retmax": "1"},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        return parse_top_result(response.text)


def parse_top_result(xml_text: str) -> HealthTopic | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    doc = root.find("./list/document")
    if doc is None:
        return None
    fields = {c.get("name"): c.text or "" for c in doc.findall("content")}
    summary = _trim(fields.get("FullSummary", ""))
    if not summary:
        return None
    return HealthTopic(
        title=_clean(fields.get("title", "")), summary=summary, url=doc.get("url", "")
    )


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", html.unescape(raw)))).strip()


def _trim(raw: str) -> str:
    """First paragraph's 2-3 sentences, skipping a leading question heading."""
    paragraphs = re.findall(r"<p>(.*?)</p>", html.unescape(raw), flags=re.DOTALL)
    text = _clean(paragraphs[0]) if paragraphs else _clean(raw)
    sentences = [s for s in _SENTENCE.split(text) if s and not s.endswith(("?", ":"))]
    return " ".join(sentences[:MAX_SENTENCES])
