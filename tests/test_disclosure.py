"""Disclosure gate and small-count suppression."""

import pandas as pd
import pytest

from aadesk.disclosure import Decision, enforce, gate, suppress_small_counts


def test_internal_into_public_needs_review():
    decision = gate("beneficiaries", "internal", "public")
    assert isinstance(decision, Decision)
    assert decision.outcome == "review"
    assert decision.allowed


def test_restricted_into_public_is_blocked():
    decision = gate("individual_record", "restricted", "public")
    assert decision.outcome == "blocked"
    assert not decision.allowed


def test_public_into_internal_is_clear():
    assert gate("population", "public", "internal").outcome == "clear"


def test_small_counts_are_generalised():
    assert suppress_small_counts(3) == "<5"
    assert suppress_small_counts(3000) == 3000
    assert suppress_small_counts(0) == 0
    assert suppress_small_counts(None) is None


def test_enforce_drops_sensitive_columns():
    frame = pd.DataFrame({"country": ["Somalia"], "people": [12],
                          "case_notes": ["identifying detail"]})
    filtered, dropped = enforce(frame, {"country": "public", "people": "public",
                                        "case_notes": "restricted"}, "public")
    assert list(filtered.columns) == ["country", "people"]
    assert dropped == [("case_notes", "restricted")]
