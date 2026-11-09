"""Audit engine: matching, checks, regression cases."""

import pandas as pd
import pytest

from aadesk.denominators import Denominators
from aadesk.registry import load_registry
from aadesk.rfcheck import assess_row, best_match, summarise


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.fixture(scope="module")
def denominators():
    return Denominators()


def test_registry_ids_are_unique(registry):
    assert len({indicator.id for indicator in registry}) == len(registry)


def test_registry_flags_unavailable_sources(registry):
    unavailable = [i.id for i in registry if i.availability == "unavailable"]
    assert "IM-DISABILITY" in unavailable


def test_match_population_denominator(registry):
    indicator, score = best_match("Total population in target districts by year", registry)
    assert indicator is not None
    assert indicator.id == "POP-DENOM"
    assert score >= 0.45


def test_match_flood_exposure(registry):
    indicator, _ = best_match(
        "Number of people living in areas exposed to 1-in-100-year river flooding", registry)
    assert indicator is not None and indicator.id == "HAZ-FLOOD-EXPO"


def test_unknown_indicator_is_unmatched(registry):
    indicator, score = best_match(
        "Number of community feedback mechanisms established and functional", registry)
    assert indicator is None
    assert score < 0.45


def test_well_sourced_indicator_is_monitorable(registry, denominators):
    row = {"indicator_text": "Total population in target districts by year",
           "disaggregation": "none", "geography": "Somalia",
           "frequency": "annual", "baseline_year": 2020, "publication": "public"}
    assessment = assess_row(row, registry, denominators)
    # "none" must not be read as a demand for detail.
    assert assessment.status == "monitorable", assessment.flags


def test_unavailable_source_is_not_monitorable(registry, denominators):
    row = {"indicator_text": "Number of beneficiaries with disability status recorded",
           "disaggregation": "disability", "geography": "Chad",
           "frequency": "quarterly", "baseline_year": 2020, "publication": "internal"}
    assessment = assess_row(row, registry, denominators)
    assert assessment.status == "not monitorable"


def test_cadence_mismatch_is_flagged(registry, denominators):
    row = {"indicator_text": "Reduction in prevalence of global acute malnutrition (GAM)",
           "disaggregation": "age", "geography": "Yemen",
           "frequency": "monthly", "baseline_year": 2019, "publication": "public"}
    assessment = assess_row(row, registry, denominators)
    names = {check.name for check in assessment.warns}
    assert "cadence" in names


def test_internal_source_blocks_publication(registry, denominators):
    row = {"indicator_text": "Number of people reached with emergency cash assistance",
           "disaggregation": "sex", "geography": "Somalia",
           "frequency": "monthly", "baseline_year": 2020, "publication": "public"}
    assessment = assess_row(row, registry, denominators)
    disclosure = next(c for c in assessment.checks if c.name == "disclosure")
    assert disclosure.status == "warn"


def test_baseline_outside_series_fails(registry, denominators):
    row = {"indicator_text": "Total population in target districts by year",
           "disaggregation": "none", "geography": "Somalia",
           "frequency": "annual", "baseline_year": 1850, "publication": "public"}
    assessment = assess_row(row, registry, denominators)
    assert any(c.name == "baseline" and c.status == "fail" for c in assessment.checks)


def test_summary_counts_add_up(registry, denominators):
    frame = pd.DataFrame([
        {"indicator_text": "Total population in target districts by year",
         "disaggregation": "none", "geography": "Somalia", "frequency": "annual",
         "baseline_year": 2020, "publication": "public"},
        {"indicator_text": "Number of community feedback mechanisms established and functional",
         "disaggregation": "none", "geography": "Somalia", "frequency": "quarterly",
         "baseline_year": 2020, "publication": "internal"},
    ])
    assessments = [assess_row(row, registry, denominators)
                   for row in frame.to_dict(orient="records")]
    summary = summarise(assessments)
    assert summary["total"] == 2
    assert sum(summary[k] for k in
               ("monitorable", "conditional", "not_monitorable", "unmatched")) == 2
