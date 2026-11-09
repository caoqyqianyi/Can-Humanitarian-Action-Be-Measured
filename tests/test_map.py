"""The map is computed, not fetched: projection, colour scale and coverage."""

from __future__ import annotations

import pytest

from aadesk.denominators import Denominators
from aadesk.mapview import (NO_SERIES, colour_for, coverage, height_for, project,
                            render_choropleth, scale_for)


@pytest.fixture(scope="module")
def denoms() -> Denominators:
    return Denominators()


def test_projection_pins_the_canvas_corners():
    scale = scale_for(1000)
    x0, y0 = project(-170.0, 84.0, scale)
    x1, y1 = project(180.0, -58.0, scale)
    assert (x0, y0) == (6.0, 6.0)
    assert x1 == pytest.approx(994.0, abs=0.2)
    assert y1 == pytest.approx(height_for(1000) - 6.0, abs=0.2)


def test_colour_scale_is_monotonic_and_distinct():
    assert colour_for(None) == NO_SERIES
    light = colour_for(80)
    dark = colour_for(600)
    assert light != dark
    assert colour_for(500) == dark
    assert colour_for(120) != light


def test_choropleth_is_self_contained(denoms):
    svg = render_choropleth(denoms, ["Somalia", "Yemen"])
    assert 'class="map"' in svg
    assert "http" not in svg          # no tiles, no fonts, no external links
    assert '"n":"Somalia"' not in svg  # geometry is inlined as paths, not JSON
    assert svg.count('class="badge"') == 2
    assert "Somalia" in svg and "Yemen" in svg


def test_unknown_country_is_grey_not_guessed(denoms):
    svg = render_choropleth(denoms, ["Atlantis"])
    assert NO_SERIES in svg
    assert svg.count('class="badge"') == 0


def test_coverage_counts_what_the_series_can_actually_colour(denoms):
    matched, drawn = coverage(denoms)
    assert drawn >= 170
    assert matched >= 165
    assert matched < drawn            # a few drawn states have no row, and stay grey
