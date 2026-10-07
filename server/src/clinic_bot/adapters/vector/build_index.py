"""Chunk the authored docs by heading and (re)build the pgvector index.

The editable FAQ documents come from the database (SPEC 17.3): ``PgDocIndexer`` rebuilds
on startup when they (or the embedding model) changed, and after every admin save.
``clinic-build-index`` forces a full rebuild from the files in ``data/docs``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

from clinic_bot.adapters.vector.pgvector_store import PgVectorStore
from clinic_bot.ports.embeddings import Embedder
from clinic_bot.ports.vector_store import Chunk

_KIND_BY_DOC = {
    "clinic_info.md": "faq",
    "insurance.md": "faq",
    "services.md": "faq",
    "prep_sheets.md": "prep",
    "specialty_guide.md": "specialty",
}
_H1 = re.compile(r"^# (.+)$", re.MULTILINE)


def read_docs(docs_dir: Path, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Heading-split documents by name. ``overrides`` (stored edits) win over the files."""
    stored = overrides or {}
    return {
        name: stored.get(name) or (docs_dir / name).read_text(encoding="utf-8")
        for name in _KIND_BY_DOC
    }


def chunk_docs(docs_dir: Path, overrides: Mapping[str, str] | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    for name, text in read_docs(docs_dir, overrides).items():
        parts = _H1.split(text)
        for i in range(1, len(parts) - 1, 2):
            section, body = parts[i].strip(), parts[i + 1].strip()
            chunks.append(Chunk(f"{name}#{i // 2}", body, name, section, _KIND_BY_DOC[name]))
    for path in sorted((docs_dir / "intake").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), path.stem)
        chunks.append(Chunk(f"intake/{path.name}", text, f"intake/{path.name}", title, "intake"))
    return chunks


def embedding_text(chunk: Chunk) -> str:
    return chunk.text if chunk.kind == "intake" else f"{chunk.section}. {chunk.text}"


def docs_digest(docs: Mapping[str, str]) -> str:
    h = hashlib.sha256()
    for name in sorted(docs):
        h.update(f"{name}\0{docs[name]}\0".encode())
    return h.hexdigest()


async def build(docs_dir: Path, store: PgVectorStore, embedder: Embedder, index_key: str) -> int:
    """Full rebuild from the files (CLI)."""
    return await PgDocIndexer(docs_dir, store, embedder, index_key).rebuild({})


class PgDocIndexer:
    """``DocIndexer`` over pgvector. The stored stamp records the embedding model and the
    digest of the documents indexed last, so a change to either rebuilds."""

    def __init__(
        self, docs_dir: Path, store: PgVectorStore, embedder: Embedder, index_key: str
    ) -> None:
        self._docs_dir, self._store, self._embedder = docs_dir, store, embedder
        self._index_key = index_key

    def _stamp(self, docs: Mapping[str, str]) -> str:
        return f"{self._index_key} {docs_digest(read_docs(self._docs_dir, docs))}"

    async def rebuild(self, docs: Mapping[str, str]) -> int:
        chunks = chunk_docs(self._docs_dir, docs)
        vectors = await self._embedder.embed([embedding_text(c) for c in chunks])
        await self._store.replace(chunks, vectors, self._stamp(docs))
        return len(chunks)

    async def ensure_current(self, docs: Mapping[str, str]) -> bool:
        if await self._store.stamp() == self._stamp(docs) and await self._store.count() > 0:
            return False
        await self.rebuild(docs)
        return True
