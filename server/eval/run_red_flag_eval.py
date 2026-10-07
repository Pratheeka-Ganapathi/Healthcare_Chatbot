"""Red-flag eval (SPEC 12.1): Layer 1, Layer 2 and OR, on dev and holdout separately.

Uses the production ``RegexGuard`` and ``LLMClassifierGuard`` classes.

    uv run python eval/run_red_flag_eval.py                 # both layers (needs an API key)
    uv run python eval/run_red_flag_eval.py --layer1-only   # regex only, free and deterministic
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from clinic_bot.config import Settings
from clinic_bot.container import build_structured_llm
from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.services.guardrails.base import GuardContext
from clinic_bot.services.guardrails.llm_guard import CLASSIFIER_PROMPT_VERSION, LLMClassifierGuard
from clinic_bot.services.guardrails.regex_guard import RegexGuard

EVAL_DIR = Path(__file__).parent
SETS = {"dev": EVAL_DIR / "red_flags.dev.jsonl", "holdout": EVAL_DIR / "red_flags.holdout.jsonl"}
RED_FLAGS = {GuardrailLabel.EMERGENCY, GuardrailLabel.SELF_HARM}
LABEL_OF = {GuardrailLabel.EMERGENCY: "emergency", GuardrailLabel.SELF_HARM: "self_harm"}


@dataclass(frozen=True)
class Item:
    text: str
    label: str
    category: str

    @property
    def positive(self) -> bool:
        return self.label != "not"


@dataclass
class Scores:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, positive: bool, flagged: bool) -> None:
        if positive and flagged:
            self.tp += 1
        elif positive:
            self.fn += 1
        elif flagged:
            self.fp += 1
        else:
            self.tn += 1

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def fp_rate(self) -> float:
        return self.fp / (self.fp + self.tn) if self.fp + self.tn else 0.0


def load(path: Path) -> list[Item]:
    return [Item(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


async def predict_l2(guard: LLMClassifierGuard, items: list[Item], rpm: int) -> list[str | None]:
    out: list[str | None] = []
    for item in items:
        try:
            verdict = await guard.check(item.text, GuardContext(node="pre_talk"))
            out.append(LABEL_OF.get(verdict.label, "not"))
        except Exception as exc:  # report and continue: one failed call shouldn't sink the run
            print(f"  classifier error on {item.text[:40]!r}: {exc}", file=sys.stderr)
            out.append(None)
        await asyncio.sleep(60 / rpm)
    return out


def evaluate(items: list[Item], preds: dict[str, list[str | None]]) -> dict[str, object]:
    report: dict[str, object] = {}
    for layer, labels in preds.items():
        scores, by_cat, misses = Scores(), defaultdict(Scores), []
        for item, pred in zip(items, labels, strict=True):
            flagged = pred is not None and pred != "not"
            scores.add(item.positive, flagged)
            by_cat[item.category].add(item.positive, flagged)
            if flagged != item.positive:
                misses.append(
                    {"text": item.text, "want": item.label, "got": pred, "category": item.category}
                )
        report[layer] = {"scores": scores, "by_category": dict(by_cat), "misses": misses}
    return report


def markdown(set_name: str, report: dict[str, object]) -> str:
    lines = [
        f"### {set_name}",
        "",
        "| Layer | Recall | Precision | FP rate | TP | FN | FP | TN |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for layer, data in report.items():
        s: Scores = data["scores"]  # type: ignore[index]
        lines.append(
            f"| {layer} | {s.recall:.2f} | {s.precision:.2f} | {s.fp_rate:.2f} "
            f"| {s.tp} | {s.fn} | {s.fp} | {s.tn} |"
        )
    lines += ["", "Per-category recall (categories with red-flag items):", ""]
    lines.append("| Category | " + " | ".join(report) + " |")
    lines.append("|---|" + "---|" * len(report))
    categories = sorted({c for d in report.values() for c in d["by_category"]})  # type: ignore[index]
    for cat in categories:
        cells = []
        for data in report.values():
            s = data["by_category"].get(cat)  # type: ignore[index]
            cells.append(f"{s.recall:.2f}" if s and (s.tp + s.fn) else "n/a")
        lines.append(f"| {cat} | " + " | ".join(cells) + " |")
    for layer, data in report.items():
        misses = data["misses"]  # type: ignore[index]
        lines += ["", f"Misses and false positives, {layer} ({len(misses)}):", ""]
        lines += [
            f"- [{m['category']}] want {m['want']}, got {m['got']}: {m['text']}" for m in misses
        ]
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer1-only", action="store_true")
    parser.add_argument("--rpm", type=int, default=12, help="classifier requests per minute")
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "results.md")
    args = parser.parse_args()

    regex = RegexGuard()
    classifier = (
        None
        if args.layer1_only
        else LLMClassifierGuard(build_structured_llm(Settings(), "classifier"))
    )
    sections = [
        f"Classifier prompt version: {CLASSIFIER_PROMPT_VERSION}. "
        "Red flag = emergency or self_harm.",
        "",
    ]
    for name, path in SETS.items():
        items = load(path)
        preds: dict[str, list[str | None]] = {
            "layer1_regex": [LABEL_OF.get(regex.precheck(i.text).label, "not") for i in items]
        }
        if classifier is not None:
            preds["layer2_classifier"] = await predict_l2(classifier, items, args.rpm)
            preds["or"] = [
                a if a != "not" else b
                for a, b in zip(preds["layer1_regex"], preds["layer2_classifier"], strict=True)
            ]
        sections.append(markdown(f"{name} ({len(items)} items)", evaluate(items, preds)))
        sections.append("")
    text = "\n".join(sections)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
