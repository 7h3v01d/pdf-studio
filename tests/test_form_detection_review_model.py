from __future__ import annotations

from form_detection_review_model import (
    checked_records,
    normalise_review_suggestions,
    review_summary,
    suggestion_type_counts,
)


def _record(identifier, kind, label, confidence, page=0):
    return {
        "suggestion_id": identifier,
        "kind": kind,
        "label": label,
        "confidence": confidence,
        "page": page,
        "rect": [10, 20, 110, 42],
        "rationale": "label plus detected geometry",
        "source": "ocr",
    }


def test_review_model_normalises_display_values_and_clamps_confidence():
    items = normalise_review_suggestions([
        _record("a", "text", "Full Name", 1.4, page=2),
        {
            "suggestion_id": "b",
            "kind": "signature_field",
            "name": "signature",
            "confidence": -0.2,
            "rect": [1, 2],
        },
    ])

    assert items[0].type_label == "Text"
    assert items[0].label == "Full Name"
    assert items[0].confidence_percent == 100
    assert items[0].page == 2
    assert items[1].type_label == "Signature Field"
    assert items[1].label == "signature"
    assert items[1].confidence_percent == 0
    assert items[1].rect == (1.0, 2.0, 0.0, 0.0)


def test_review_checked_records_preserves_detector_order():
    items = normalise_review_suggestions([
        _record("first", "text", "Name", 0.88),
        _record("second", "date", "Date", 0.78),
        _record("third", "checkbox", "Agree", 0.82),
    ])

    selected = checked_records(items, ["third", "first"])
    assert [item["suggestion_id"] for item in selected] == ["first", "third"]


def test_review_summary_reports_type_breakdown():
    items = normalise_review_suggestions([
        _record("a", "text", "Name", 0.88),
        _record("b", "text", "Email", 0.88),
        _record("c", "date", "Date", 0.78),
    ])

    assert suggestion_type_counts(items) == {"Text": 2, "Date": 1}
    summary = review_summary(items, page_number=0)
    assert summary == "Page 1: 3 suggestions ready (1 date, 2 text)."
    assert review_summary([], page_number=4) == (
        "Page 5: no suggestions ready for review."
    )
