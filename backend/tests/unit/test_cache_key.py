"""The cache key must change when, and only when, the answer could change.

A key that is too loose serves a wrong packet; a key that is too tight costs
tokens. These tests pin both directions, one component at a time.
"""

from __future__ import annotations

import pytest

from app.modules.analysis.service import cache_key

BASE = {
    "cv_text_sha256": "a" * 64,
    "extract_key": "b" * 64,
    "prompt_bundle": "c" * 64,
    "model": "deepseek-v4-flash",
    "runs": 3,
    "params": {"cover_min_words": 60, "cover_max_words": 150},
}


def test_the_same_inputs_always_give_the_same_key() -> None:
    assert cache_key(**BASE) == cache_key(**dict(BASE))


def test_the_key_is_a_sha256_hex_digest() -> None:
    key = cache_key(**BASE)

    assert len(key) == 64
    assert all(character in "0123456789abcdef" for character in key)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cv_text_sha256", "d" * 64),
        ("extract_key", "e" * 64),
        ("prompt_bundle", "f" * 64),
        ("model", "another-model"),
        ("runs", 1),
        ("params", {"cover_min_words": 40, "cover_max_words": 150}),
    ],
)
def test_every_component_of_the_key_matters(field: str, value: object) -> None:
    changed = {**BASE, field: value}

    assert cache_key(**changed) != cache_key(**BASE)


def test_a_cv_edit_and_a_model_change_never_collide() -> None:
    """Two independent changes must not cancel each other out in the hash."""
    edited_cv = cache_key(**{**BASE, "cv_text_sha256": "d" * 64})
    other_model = cache_key(**{**BASE, "model": "another-model"})
    both = cache_key(**{**BASE, "cv_text_sha256": "d" * 64, "model": "another-model"})

    assert len({cache_key(**BASE), edited_cv, other_model, both}) == 4


def test_the_parameter_order_does_not_matter() -> None:
    first = cache_key(**{**BASE, "params": {"cover_min_words": 60, "cover_max_words": 150}})
    second = cache_key(**{**BASE, "params": {"cover_max_words": 150, "cover_min_words": 60}})

    assert first == second


def test_no_parameters_is_the_same_as_empty_parameters() -> None:
    assert cache_key(**{**BASE, "params": None}) == cache_key(**{**BASE, "params": {}})


def test_a_key_without_parameters_is_not_a_key_with_defaults() -> None:
    without = cache_key(**{**BASE, "params": None})

    assert without != cache_key(**BASE)
