"""End-to-end: registry + framework in, scorecard and brief out."""

import pandas as pd
import pytest

from aadesk.denominators import Denominators
from aadesk.registry import load_registry
from aadesk.report import build_brief, export_powerbi
from aadesk.rfcheck import audit_logframe


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    registry = load_registry()
    denominators = Denominators()
    frame = pd.DataFrame([
        {"result_level": "Output", "indicator_text": "Total population in target districts by year",
         "disaggregation": "none", "geography": "Somalia", "frequency": "annual",
         "baseline_year": 2020, "publication": "public"},
        {"result_level": "Outcome",
         "indicator_text": "Number of people reached with emergency cash assistance",
         "disaggregation": "sex", "geography": "Somalia", "frequency": "monthly",
         "baseline_year": 2019, "publication": "public"},
    ])
    assessments = audit_logframe(frame, registry, denominators)
    out = tmp_path_factory.mktemp("out")
    brief = build_brief(assessments, denominators, ["Somalia"], out / "brief.html",
                        title="Test brief", baseline_year=2019, reference_year=2020)
    powerbi = export_powerbi(assessments, denominators, ["Somalia"], out / "powerbi")
    return assessments, brief, powerbi


def test_brief_is_rendered_without_placeholders(run):
    _, brief, _ = run
    text = brief.read_text()
    assert "<svg" in text
    assert "Somalia" in text
    assert "{rows}" not in text and "{{" not in text


def test_powerbi_export_has_star_schema(run):
    _, _, powerbi = run
    for name in ("dim_indicator", "dim_country", "fact_assessment",
                 "fact_denominator", "model"):
        assert name in powerbi and powerbi[name].exists(), name
    fact = pd.read_csv(powerbi["fact_assessment"])
    assert "matched_id" in fact.columns
