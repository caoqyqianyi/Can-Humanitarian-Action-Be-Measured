"""Monitorability audit: does the data behind a promised indicator exist?

Each indicator in a results framework is matched against the registry and then
put through six checks. The output is deliberately blunt — a proposal team needs
to know, before signature, which of its indicators will still be reported on
month 18, and which will quietly become "to be confirmed".
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field

import pandas as pd

from .denominators import Denominators
from .registry import Indicator

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "to", "with", "within", "per",
    "number", "share", "proportion", "percentage", "percent", "total", "level",
    "rate", "value", "target", "targeted", "activity", "activities", "result",
    "output", "outcome", "indicator", "annual", "monthly", "quarterly",
}

CADENCE_RANK = {
    "per activation": 1.0,
    "ad hoc": 1.0,
    "biennial": 0.5,
    "annual": 1.0,
    "seasonal": 3.0,
    "quarterly": 4.0,
    "monthly": 12.0,
}

PUBLICATION_RANK = {"public": 0, "internal": 1, "restricted": 2}

MATCH_THRESHOLD = 0.45


def normalise(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {w for w in normalise(text).split() if w not in STOPWORDS and len(w) > 2}


def cadence(text: str) -> tuple[str, float]:
    text = normalise(text)
    for label in ("monthly", "quarterly", "seasonal", "biennial", "annual",
                  "per activation", "ad hoc"):
        if label in text:
            return label, CADENCE_RANK[label]
    if re.search(r"\b(month|quarter|year|season|activation)\b", text):
        return text, 1.0
    return "unspecified", 1.0


def disaggregation_list(text: str) -> list[str]:
    text = normalise(text)
    found = []
    for key, needles in (
        ("sex", ("sex", "gender", "male female")),
        ("age_group", ("age", "age group", "age group 5 17")),
        ("disability", ("disability", "disabilities", "washington group")),
        ("geography", ("geographic", "district", "region", "province")),
        ("crop", ("crop", "maize", "wheat", "rice")),
        ("partner_type", ("partner", "localisation", "localization")),
        ("displacement_status", ("displacement", "idp", "refugee", "host community")),
        ("incident_type", ("incident", "type of incident")),
        ("none", ("none", "not disaggregated", "aggregate only")),
    ):
        if any(needle in text for needle in needles):
            found.append(key)
    return found or ["unspecified"]


@dataclass
class Check:
    name: str
    status: str  # pass | warn | fail
    detail: str


@dataclass
class Assessment:
    indicator_text: str
    result_level: str = ""
    unit: str = ""
    geography: str = ""
    baseline_year: int | None = None
    publication: str = "public"
    matched_id: str = ""
    matched_name: str = ""
    match_score: float = 0.0
    status: str = "unmatched"
    checks: list[Check] = field(default_factory=list)
    summary: str = ""

    @property
    def fails(self) -> list[Check]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warns(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    @property
    def flags(self) -> str:
        return " | ".join(f"[{c.status[0].upper()}] {c.name}: {c.detail}"
                          for c in self.checks if c.status != "pass")

    def to_row(self) -> dict:
        return {
            "indicator_text": self.indicator_text,
            "result_level": self.result_level,
            "matched_id": self.matched_id,
            "matched_name": self.matched_name,
            "match_score": round(self.match_score, 3),
            "status": self.status,
            "fails": len(self.fails),
            "warns": len(self.warns),
            "geography": self.geography,
            "baseline_year": self.baseline_year,
            "publication": self.publication,
            "flags": self.flags,
            "summary": self.summary,
        }


# --------------------------------------------------------------------- matching
def score_against(text: str, indicator: Indicator) -> float:
    a = tokens(text)
    b = tokens(indicator.searchable_text)
    if not a or not b:
        return 0.0
    jaccard = len(a & b) / len(a | b)
    score = 1.5 * jaccard

    # A multi-word registry phrase appearing verbatim is strong evidence.
    haystack = normalise(text)
    for keyword in [indicator.name, *indicator.keywords]:
        needle = normalise(keyword)
        if len(needle.split()) >= 2 and needle in haystack:
            score += 0.30
    # Whole-name similarity catches paraphrases the tokens miss.
    score += 0.25 * difflib.SequenceMatcher(
        a=normalise(indicator.name), b=haystack).ratio()
    return round(min(1.0, score), 3)


def best_match(text: str, indicators: list[Indicator]) -> tuple[Indicator | None, float]:
    scored = [(ind, score_against(text, ind)) for ind in indicators]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    best, score = scored[0]
    return (best if score >= MATCH_THRESHOLD else None), score


# ----------------------------------------------------------------------- checks
def _check_availability(ind: Indicator) -> Check:
    if ind.availability == "available":
        return Check("availability", "pass",
                     f"open source exists ({ind.source_custodian or ind.source_id})")
    if ind.availability == "partial":
        return Check("availability", "warn",
                     f"source exists but needs preparation ({ind.source_custodian})")
    return Check("availability", "fail",
                 "no consistent data source identified across the portfolio")


def _check_disaggregation(ind: Indicator, requested: list[str]) -> Check:
    supported = {d for d in ind.disaggregation if d != "none"}
    missing = [d for d in requested if d not in supported and d != "unspecified"]
    if not requested or requested in (["unspecified"], ["none"]):
        return Check("disaggregation", "pass", "no disaggregation promised")
    if not supported:
        return Check("disaggregation", "warn",
                     f"source is aggregate only; promised {', '.join(missing) or 'detail'} "
                     "cannot be produced")
    if missing:
        return Check("disaggregation", "warn",
                     f"source supports {', '.join(sorted(supported))}; "
                     f"promised {', '.join(missing)} is not available")
    return Check("disaggregation", "pass", f"supports {', '.join(sorted(supported))}")


def _check_cadence(ind: Indicator, promised: str) -> Check:
    promised_label, promised_rank = cadence(promised)
    source_label, source_rank = cadence(ind.frequency)
    if promised_rank > source_rank:
        return Check("cadence", "warn",
                     f"promised {promised_label}; source runs {source_label} — "
                     "values will be carried forward, not measured")
    return Check("cadence", "pass", f"source cadence {source_label} covers {promised_label}")


def _check_geography_and_baseline(ind: Indicator, geography: str,
                                  baseline_year: int | None,
                                  denominators: Denominators | None) -> Check:
    if denominators is None or not geography:
        return Check("geography", "pass", "not evaluated (no denominator layer)")

    country, score = denominators.resolve(geography)
    if country is None:
        return Check("geography", "warn",
                     f"'{geography}' not resolvable to a national unit in the "
                     "population series; denominator must come from the programme")

    first, last = denominators.year_range
    if baseline_year and not first <= int(baseline_year) <= last:
        return Check("baseline", "fail",
                     f"baseline {baseline_year} outside the series ({first}–{last})")

    if baseline_year:
        value = denominators.value(geography, int(baseline_year))
        return Check("geography", "pass",
                     f"{country} covered; baseline {baseline_year} = "
                     f"{value:,.0f} people" if value else f"{country} covered")

    latest = denominators.value(geography, last)
    return Check("geography", "pass",
                 f"{country} covered through {last} ({latest:,.0f} people)")


def _check_disclosure(ind: Indicator, publication: str) -> Check:
    pub_rank = PUBLICATION_RANK.get(publication.lower(), 0)
    ind_rank = PUBLICATION_RANK.get(ind.disclosure.lower(), 2)
    if pub_rank >= ind_rank:
        return Check("disclosure", "pass",
                     f"'{ind.disclosure}' output fits a '{publication}' product")
    if ind_rank - pub_rank == 1:
        return Check("disclosure", "warn",
                     f"source is '{ind.disclosure}'; only reviewed aggregate figures "
                     "may be published")
    return Check("disclosure", "fail",
                 f"source is '{ind.disclosure}'; cannot be published in a "
                 f"'{publication}' product")


CHECKS = (_check_availability, _check_disaggregation, _check_cadence)


def assess_row(row: dict, indicators: list[Indicator],
               denominators: Denominators | None = None) -> Assessment:
    text = str(row.get("indicator_text", "")).strip()
    publication = str(row.get("publication", "public") or "public").strip().lower()
    baseline_raw = row.get("baseline_year")
    try:
        baseline_year = int(float(baseline_raw)) if baseline_raw not in (None, "", "nan") else None
    except (TypeError, ValueError):
        baseline_year = None

    assessment = Assessment(
        indicator_text=text,
        result_level=str(row.get("result_level", "") or ""),
        unit=str(row.get("unit", "") or ""),
        geography=str(row.get("geography", "") or ""),
        baseline_year=baseline_year,
        publication=publication,
    )

    indicator, score = best_match(text, indicators)
    assessment.match_score = score
    if indicator is None:
        assessment.status = "unmatched"
        assessment.summary = ("No registry entry is close enough; the indicator has no "
                             "identified data trail. Either reword it towards an existing "
                             "source, or budget for a primary collection instrument.")
        assessment.checks = [Check("match", "fail",
                                   f"best score {score:.2f} below threshold {MATCH_THRESHOLD}")]
        return assessment

    assessment.matched_id = indicator.id
    assessment.matched_name = indicator.name
    checks = [
        _check_availability(indicator),
        _check_disaggregation(indicator, disaggregation_list(row.get("disaggregation", "") or text)),
        _check_cadence(indicator, str(row.get("frequency", "") or indicator.frequency)),
        _check_geography_and_baseline(indicator, assessment.geography, baseline_year, denominators),
        _check_disclosure(indicator, publication),
    ]
    assessment.checks = checks

    if any(c.status == "fail" for c in checks):
        assessment.status = "not monitorable"
        assessment.summary = indicator.note or "Hard blocker: the promised data will not exist."
    elif any(c.status == "warn" for c in checks):
        assessment.status = "conditional"
        assessment.summary = (
            "Reportable only with a stated caveat: " +
            "; ".join(c.detail for c in assessment.warns)[:220])
    else:
        assessment.status = "monitorable"
        assessment.summary = f"Backed by {indicator.source_title}."

    return assessment


def audit_logframe(frame: pd.DataFrame, indicators: list[Indicator],
                   denominators: Denominators | None = None) -> list[Assessment]:
    return [assess_row(row, indicators, denominators)
            for row in frame.to_dict(orient="records")]


def summarise(assessments: list[Assessment]) -> dict:
    counts: dict[str, int] = {}
    for assessment in assessments:
        counts[assessment.status] = counts.get(assessment.status, 0) + 1
    total = len(assessments) or 1
    return {
        "total": len(assessments),
        "monitorable": counts.get("monitorable", 0),
        "conditional": counts.get("conditional", 0),
        "not_monitorable": counts.get("not monitorable", 0),
        "unmatched": counts.get("unmatched", 0),
        "monitorable_share": round(counts.get("monitorable", 0) / total, 3),
        "share_at_risk": round((counts.get("unmatched", 0) +
                                counts.get("not monitorable", 0)) / total, 3),
    }


def to_frame(assessments: list[Assessment]) -> pd.DataFrame:
    return pd.DataFrame([a.to_row() for a in assessments])


def to_records(assessments: list[Assessment]) -> list[dict]:
    out = []
    for assessment in assessments:
        record = asdict(assessment)
        record["checks"] = [asdict(c) for c in assessment.checks]
        out.append(record)
    return out
