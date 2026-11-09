"""Denominator layer: units, aliases, coverage."""

import pandas as pd

from aadesk.denominators import Denominators, format_persons, load_population


def test_population_is_converted_to_persons():
    frame = load_population()
    row = frame[(frame["country"] == "Somalia") & (frame["year"] == 2020)].iloc[0]
    assert row["population_thousands"] < 100_000
    assert row["population"] == row["population_thousands"] * 1000


def test_series_covers_expected_years():
    denominators = Denominators()
    first, last = denominators.year_range
    assert first == 1901
    assert last == 2020
    assert len(denominators.countries) > 100


def test_exact_and_aliased_country_resolution():
    denominators = Denominators()
    assert denominators.resolve("Somalia")[0] == "Somalia"
    assert denominators.resolve("Ivory Coast")[0] == "Cote d'Ivoire"
    assert denominators.resolve("Syrian Arab Republic")[0] == "Syrian Arab Rep."
    assert denominators.resolve("Democratic Republic of the Congo")[0] == "Congo Dem. Rep."


def test_similar_names_do_not_collapse():
    denominators = Denominators()
    # The old fuzzy cutoff turned this into "Serbia"; the alias must win.
    assert denominators.resolve("Syrian Arab Republic")[0] != "Serbia"
    assert denominators.resolve("Niger")[0] == "Niger"
    assert denominators.resolve("Nigeria")[0] == "Nigeria"


def test_unknown_country_is_not_silently_guessed():
    denominators = Denominators()
    country, score = denominators.resolve("Atlantis")
    assert country is None
    assert score == 0.0


def test_drift_reports_change():
    denominators = Denominators()
    drift = denominators.drift(["Somalia"], 2019, 2020)
    assert list(drift["country_matched"]) == ["Somalia"]
    assert drift["change_pct"].iloc[0] > 0


def test_format_persons_scales():
    assert format_persons(16_100_000) == "16.1 m"
    assert format_persons(None) == "–"
