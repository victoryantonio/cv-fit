"""Pairing a hand-written label with what the pipeline extracted.

Overlap decides which gold requirement an extraction is compared against, so a
mistake here shows up as an unexplained agreement drop rather than an error.
"""

from __future__ import annotations

from app.eval_metrics import match_requirements, overlap


def test_overlap_is_one_when_the_texts_agree() -> None:
    assert overlap("Strong Go", "strong go.") == 1.0


def test_a_short_label_inside_a_long_extraction_still_matches() -> None:
    """Jaccard would call this a miss; a hand label is always the short side."""
    assert overlap("strong go", "Strong Go. Our services are written in Go.") == 1.0


def test_disjoint_texts_share_nothing() -> None:
    assert overlap("Strong Go", "Excellent written English") == 0.0


def test_empty_text_never_matches() -> None:
    assert overlap("", "Strong Go") == 0.0
    assert overlap("Strong Go", "") == 0.0


def test_matching_prefers_the_best_pair_and_uses_each_item_once() -> None:
    mapping = match_requirements(
        ["Strong Go", "PostgreSQL tuning"],
        ["PostgreSQL tuning on large tables", "Strong Go. Daily Go work."],
    )

    assert mapping == {0: 1, 1: 0}


def test_two_labels_never_claim_the_same_requirement() -> None:
    mapping = match_requirements(["Go", "Go language"], ["Strong Go experience"])

    assert mapping == {0: 0}
    assert len(set(mapping.values())) == len(mapping)


def test_a_weak_pair_is_left_unmatched() -> None:
    assert match_requirements(["Strong Go"], ["Excellent written English"]) == {}


def test_an_extra_extracted_requirement_is_not_penalised_here() -> None:
    mapping = match_requirements(["Strong Go"], ["Strong Go", "Kubernetes", "Kafka"])

    assert mapping == {0: 0}
