"""Rule-based extraction of indicator statements from proposal text.

A first pass, not an oracle. It exists so that a long narrative proposal can be
reduced to candidate indicator statements that can then be checked against the
registry — which is the part that matters. Everything here runs offline with no
model call; docs/extraction.md describes how to swap in an LLM for the
free-text cases this regex layer misses.
"""

from __future__ import annotations

import re

import pandas as pd

BULLET = re.compile(r"^\s*(?:[-–—*•]|\(?[a-z0-9]+\)|\d+\.)\s+", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")
MEASURE_VERBS = re.compile(
    r"\b(increase|decrease|reduce|reduction|improve|reach|reached|provide|provided|"
    r"ensure|maintain|establish|train|support|deliver|delivered|record|monitor|"
    r"share|percentage|number|rate|ratio|days|index|score)\b", re.IGNORECASE)

UNITS = [
    (re.compile(r"(?:%|per cent|percent|percentage)", re.IGNORECASE), "percent"),
    (re.compile(r"\bnumber of\b|\bcount of\b|\bpersons\b|\bpeople\b", re.IGNORECASE), "count"),
    (re.compile(r"\bdays?\b", re.IGNORECASE), "days"),
    (re.compile(r"\btonnes?\b|\bmt\b", re.IGNORECASE), "tonnes"),
    (re.compile(r"\bhectares?\b|\bha\b", re.IGNORECASE), "hectares"),
]

DISAGGREGATION = [
    (re.compile(r"\bsex[- ]disaggregat|by sex|male/female|women|men\b", re.IGNORECASE), "sex"),
    (re.compile(r"\bage\b|\bage group", re.IGNORECASE), "age_group"),
    (re.compile(r"\bdisabilit", re.IGNORECASE), "disability"),
    (re.compile(r"\bdistrict|\bgovernorate|\bprovince|\bregion\b", re.IGNORECASE), "geography"),
]

CADENCE = [
    (re.compile(r"\bmonthly\b|\bper month\b", re.IGNORECASE), "monthly"),
    (re.compile(r"\bquarterly\b|\bper quarter\b", re.IGNORECASE), "quarterly"),
    (re.compile(r"\bseason\b|\bseasonal\b", re.IGNORECASE), "seasonal"),
    (re.compile(r"\bannual\b|\bper year\b|\byearly\b", re.IGNORECASE), "annual"),
    (re.compile(r"\bper activation\b|\bactivation\b", re.IGNORECASE), "per activation"),
]


def candidate_lines(text: str, min_length: int = 40) -> list[str]:
    lines: list[str] = []
    for block in text.splitlines():
        block = BULLET.sub("", block).strip()
        if not block:
            continue
        for piece in SENTENCE_SPLIT.split(block):
            piece = piece.strip(" -–—•*")
            if len(piece) >= min_length and MEASURE_VERBS.search(piece):
                lines.append(piece)
    return lines


def _first_match(patterns, text: str, default: str = "") -> str:
    for pattern, label in patterns:
        if pattern.search(text):
            return label
    return default


def extract(text: str, countries: list[str] | None = None) -> pd.DataFrame:
    rows = []
    for statement in candidate_lines(text):
        geography = ""
        if countries:
            for country in sorted(countries, key=len, reverse=True):
                if re.search(rf"\b{re.escape(country)}\b", statement, re.IGNORECASE):
                    geography = country
                    break
        unit = _first_match(UNITS, statement, "unspecified")
        disagg = [label for pattern, label in DISAGGREGATION if pattern.search(statement)]
        cadence = _first_match(CADENCE, statement, "unspecified")
        confidence = 0.4 + (0.2 if unit != "unspecified" else 0) + \
                     (0.2 if geography else 0) + (0.2 if disagg else 0)
        rows.append({
            "indicator_text": statement,
            "unit": unit,
            "geography": geography,
            "disaggregation": ", ".join(disagg) if disagg else "none",
            "frequency": cadence,
            "confidence": round(min(confidence, 1.0), 2),
        })
    return pd.DataFrame(rows, columns=["indicator_text", "unit", "geography",
                                       "disaggregation", "frequency", "confidence"])
