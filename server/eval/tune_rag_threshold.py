"""Pick the RAG similarity threshold for an embedding model (SPEC 7).

``eval/rag_threshold.jsonl`` has clinic-style questions labelled ``match``: true if the
clinic docs answer it (FAQ) or a specific symptom checklist fits it (intake), false if
the bot should say it doesn't know (FAQ) or use the general checklist (intake). Each
question is scored against the chunks exactly as ``answer_faq`` and the checklist lookup
do (top-1 cosine over the same ``kind`` filter), and every candidate threshold is
reported with its accuracy. No database needed: the chunks are embedded here.

    uv run python eval/tune_rag_threshold.py                      # the configured embedder
    uv run python eval/tune_rag_threshold.py --backend fastembed \\
        --model sentence-transformers/all-MiniLM-L6-v2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections.abc import Sequence
from pathlib import Path

from clinic_bot.adapters.vector.build_index import chunk_docs, embedding_text
from clinic_bot.config import SERVER_ROOT, Settings
from clinic_bot.container import build_embedder

EVAL = Path(__file__).resolve().parent / "rag_threshold.jsonl"
KINDS = {"faq": ("faq", "prep"), "intake": ("intake",)}
GENERAL = "intake/general.md"  # the fallback checklist is itself a chunk
QUOTA_PAUSE_S = 65


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def _correct(row: dict[str, object], doc: str, score: float, threshold: float) -> bool:
    hit = score >= threshold and not (row["kind"] == "intake" and doc == GENERAL)
    return hit == row["match"]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend")
    parser.add_argument("--model")
    args = parser.parse_args()
    overrides = {
        k: v for k, v in (("embed_backend", args.backend), ("embed_model", args.model)) if v
    }
    settings = Settings(**overrides)  # type: ignore[arg-type]
    embedder = build_embedder(settings)
    chunks = chunk_docs(SERVER_ROOT / "data" / "docs")
    rows = [json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines() if line]
    chunk_vecs = await embedder.embed([embedding_text(c) for c in chunks])
    if settings.embed_backend != "fastembed":
        print(f"Waiting {QUOTA_PAUSE_S}s: free-tier embedding quotas count every text per minute")
        await asyncio.sleep(QUOTA_PAUSE_S)
    question_vecs = await embedder.embed([r["text"] for r in rows])
    scored: list[tuple[dict[str, object], str, float]] = []
    for row, qv in zip(rows, question_vecs, strict=True):
        candidates = [(c, cv) for c, cv in zip(chunks, chunk_vecs, strict=True)
                      if c.kind in KINDS[str(row["kind"])]]  # fmt: skip
        best, best_vec = max(candidates, key=lambda pair: _cosine(qv, pair[1]))
        scored.append((row, best.doc, _cosine(qv, best_vec)))
    print(f"Embedder {settings.index_key}, {len(rows)} questions\n")
    for kind in KINDS:
        own = [s for s in scored if s[0]["kind"] == kind]
        yes = sorted(score for row, doc, score in own if row["match"])
        no = sorted(score for row, doc, score in own if not row["match"])
        print(
            f"{kind}: match scores {yes[0]:.3f}..{yes[-1]:.3f}, no-match {no[0]:.3f}..{no[-1]:.3f}"
        )
    print("\n| Threshold | FAQ correct | Intake correct |\n|---|---|---|")
    for step in range(20, 81, 2):
        t = step / 100
        cells = []
        for kind in KINDS:
            own = [s for s in scored if s[0]["kind"] == kind]
            cells.append(f"{sum(_correct(r, d, sc, t) for r, d, sc in own)}/{len(own)}")
        print(f"| {t:.2f} | {cells[0]} | {cells[1]} |")
    cutoffs = {"faq": settings.faq_cutoff, "intake": settings.checklist_cutoff}
    print(
        f"\nMisses at the configured cut-offs (FAQ {cutoffs['faq']}, intake {cutoffs['intake']}):"
    )
    for row, doc, score in scored:
        if not _correct(row, doc, score, cutoffs[str(row["kind"])]):
            print(f"- [{row['kind']}] {score:.3f} {doc}: {row['text']}")


if __name__ == "__main__":
    asyncio.run(main())
