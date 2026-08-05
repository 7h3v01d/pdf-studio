"""Pure helpers for presenting and approving smart form suggestions.

The review model deliberately contains no Qt imports so confidence filtering,
labels, summaries, and checked-record handling remain easy to unit test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ReviewSuggestion:
    record: dict
    suggestion_id: str
    page: int
    kind: str
    type_label: str
    label: str
    confidence: float
    confidence_percent: int
    rationale: str
    source: str
    rect: tuple[float, float, float, float]

    @classmethod
    def from_record(cls, record: dict) -> "ReviewSuggestion":
        raw = dict(record or {})
        kind = str(raw.get("kind") or "field").strip().lower()
        type_label = kind.replace("_", " ").title()
        label = str(
            raw.get("label")
            or raw.get("name")
            or "Unnamed suggestion"
        ).strip()
        confidence = min(1.0, max(0.0, float(raw.get("confidence", 0.0) or 0.0)))
        rect_value = list(raw.get("rect") or (0.0, 0.0, 0.0, 0.0))[:4]
        while len(rect_value) < 4:
            rect_value.append(0.0)
        rect = tuple(float(value) for value in rect_value)
        return cls(
            record=raw,
            suggestion_id=str(raw.get("suggestion_id") or ""),
            page=max(0, int(raw.get("page", 0) or 0)),
            kind=kind,
            type_label=type_label,
            label=label,
            confidence=confidence,
            confidence_percent=int(round(confidence * 100)),
            rationale=str(raw.get("rationale") or "").strip(),
            source=str(raw.get("source") or "unknown").strip(),
            rect=rect,
        )


def normalise_review_suggestions(
    suggestions: Iterable[dict],
) -> list[ReviewSuggestion]:
    """Return stable, display-ready suggestions in detector order."""
    return [ReviewSuggestion.from_record(record) for record in suggestions or []]


def checked_records(
    suggestions: Iterable[ReviewSuggestion], checked_ids: Iterable[str]
) -> list[dict]:
    """Return original records whose stable IDs are checked."""
    wanted = {str(value) for value in checked_ids}
    return [
        dict(item.record)
        for item in suggestions
        if item.suggestion_id in wanted
    ]


def suggestion_type_counts(
    suggestions: Iterable[ReviewSuggestion],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in suggestions:
        counts[item.type_label] = counts.get(item.type_label, 0) + 1
    return counts


def review_summary(
    suggestions: Iterable[ReviewSuggestion], *, page_number: int | None = None
) -> str:
    records = list(suggestions)
    count = len(records)
    if not count:
        if page_number is None:
            return "No suggestions ready for review."
        return f"Page {page_number + 1}: no suggestions ready for review."

    counts = suggestion_type_counts(records)
    breakdown = ", ".join(
        f"{amount} {kind.lower()}" for kind, amount in sorted(counts.items())
    )
    prefix = f"Page {page_number + 1}: " if page_number is not None else ""
    noun = "suggestion" if count == 1 else "suggestions"
    return f"{prefix}{count} {noun} ready ({breakdown})."
