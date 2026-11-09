"""Choropleth in inline SVG — no tiles, no mapping library, no network.

Boundaries are Natural Earth 110m admin-0 (public domain), reduced to outer
rings and rounded to 0.1 degree at build time. The brief has to survive being
printed, e-mailed as an attachment and opened on a machine with no connectivity,
so a tile server or a JS mapping library would break exactly the moment the
document matters.

The map answers the question the chart cannot: *where* the denominators sit, and
which of those countries the series actually covers.
"""

from __future__ import annotations

import html as _html
import json
from functools import lru_cache

from .config import BOUNDARY_FILE
from .denominators import Denominators, format_persons

LON_MIN, LON_MAX = -170.0, 180.0
LAT_MIN, LAT_MAX = -58.0, 84.0
PAD = 6

NO_SERIES = "#c8ccc6"
RAMPS = (
    (100.0, "#ecdcc4", "under +100%"),
    (200.0, "#e0c3a5", "+100 to 200%"),
    (300.0, "#c8935f", "+200 to 300%"),
    (500.0, "#a3622f", "+300 to 500%"),
    (None, "#7d4118", "+500% or more"),
)


def colour_for(value: float | None) -> str:
    """Sequential ramp on growth since 1960; grey means the series has no row."""
    if value is None:
        return NO_SERIES
    for ceiling, colour, _ in RAMPS:
        if ceiling is None or value < ceiling:
            return colour
    return NO_SERIES


@lru_cache(maxsize=1)
def load_features() -> list[dict]:
    with open(BOUNDARY_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def scale_for(width: int) -> float:
    return (width - 2 * PAD) / (LON_MAX - LON_MIN)


def height_for(width: int) -> int:
    return round((LAT_MAX - LAT_MIN) * scale_for(width) + 2 * PAD)


def project(lon: float, lat: float, scale: float) -> tuple[float, float]:
    """Plate carrée. Distortion is the price of a projection a reader recognises."""
    return (round(PAD + (lon - LON_MIN) * scale, 1),
            round(PAD + (LAT_MAX - lat) * scale, 1))


def _ring_path(ring: list[list[float]], scale: float) -> str:
    points = [project(lon, lat, scale) for lon, lat in ring]
    return "M" + "L".join(f"{x},{y}" for x, y in points) + "Z"


def _feature_path(feature: dict, scale: float) -> str:
    return "".join(_ring_path(ring, scale) for ring in feature["r"])


def _label_anchor(feature: dict, scale: float) -> tuple[float, float]:
    """Centre of the largest ring's bounding box, which beats an area centroid."""
    rings = feature["r"]
    biggest = max(rings, key=lambda r: (max(p[0] for p in r) - min(p[0] for p in r))
                  * (max(p[1] for p in r) - min(p[1] for p in r)))
    xs = [p[0] for p in biggest]
    ys = [p[1] for p in biggest]
    return project((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, scale)


def growth_table(denominators: Denominators, start: int = 1960,
                 end: int | None = None) -> dict[str, tuple[float, float]]:
    """country -> (growth per cent since start, population at end)."""
    end = end or denominators.year_range[1]
    out: dict[str, tuple[float, float]] = {}
    for country in denominators.countries:
        first = denominators.value(country, start)
        last = denominators.value(country, end)
        if not first or not last:
            continue
        out[country] = ((last / first - 1) * 100, last)
    return out


def coverage(denominators: Denominators) -> tuple[int, int]:
    """(countries drawn that have a row in the series, countries drawn)."""
    features = load_features()
    matched = sum(1 for f in features if denominators.resolve(f["n"])[0])
    return matched, len(features)


def render_choropleth(denominators: Denominators, focus: list[str] | None = None,
                      width: int = 1000, start: int = 1960) -> str:
    """World map of population growth since `start`, with the framework's own
    countries marked and numbered. Returns an HTML block: SVG plus legend plus
    a key for the numbered countries."""
    focus = focus or []
    scale = scale_for(width)
    height = height_for(width)
    values = growth_table(denominators, start)
    end = denominators.year_range[1]

    resolved_focus = []
    for name in focus:
        country, _ = denominators.resolve(name)
        if country and country not in resolved_focus:
            resolved_focus.append(country)

    shapes: list[str] = []
    outline: list[str] = []
    for feature in load_features():
        country, _ = denominators.resolve(feature["n"])
        value = values.get(country, (None, None))[0] if country else None
        population = values.get(country, (None, None))[1] if country else None
        fill = colour_for(value)
        path = _feature_path(feature, scale)
        if country in resolved_focus:
            outline.append(f'<path d="{path}" fill="{fill}" stroke="#14211d" '
                           f'stroke-width="1.1" class="geo" '
                           f'data-n="{_html.escape(feature["n"])}" '
                           f'data-v="{"" if value is None else f"{value:+.0f}%"}" '
                           f'data-p="{"" if population is None else format_persons(population)}"/>')
            continue
        title = _html.escape(feature["n"])
        if value is not None:
            title += f" — {value:+.0f}% since {start}"
        shapes.append(f'<path d="{path}" fill="{fill}" stroke="#fbfaf6" stroke-width="0.7" '
                      f'class="geo" data-n="{_html.escape(feature["n"])}" '
                      f'data-v="{"" if value is None else f"{value:+.0f}%"}" '
                      f'data-p="{"" if population is None else format_persons(population)}"/>')

    badges: list[str] = []
    placed: list[tuple[float, float]] = []
    for index, country in enumerate(resolved_focus, start=1):
        feature = next((f for f in load_features()
                        if denominators.resolve(f["n"])[0] == country), None)
        if feature is None:
            continue
        x, y = _label_anchor(feature, scale)
        # Neighbours crowd at world scale (Ethiopia / Somalia / Yemen); push the
        # later badge clear rather than letting two dots merge into one.
        while any((abs(x - px) < 13 and abs(y - py) < 13) for px, py in placed):
            x, y = x + 13, y - 11
        placed.append((x, y))
        badges.append(f'<circle cx="{x}" cy="{y}" r="6.5" fill="#14211d" opacity="0.92"/>'
                      f'<text x="{x}" y="{y + 3.1}" text-anchor="middle" class="badge">{index}</text>')

    legend = "".join(
        f'<span class="swatch"><i style="background:{colour}"></i>{_html.escape(label)}</span>'
        for _, colour, label in RAMPS)
    legend += (f'<span class="swatch"><i style="background:{NO_SERIES}"></i>'
               f'no row in the series</span>')

    key = ""
    rows = []
    for index, country in enumerate(resolved_focus, start=1):
        value, population = values.get(country, (None, None))
        if value is None:
            continue
        rows.append(f'<li><span class="badge-n">{index}</span>'
                    f'<b>{_html.escape(country)}</b>'
                    f'<span class="badge-v">{value:+.0f}% since {start}</span>'
                    f'<span class="badge-p">{format_persons(population)} in {end}</span></li>')
    if rows:
        key = f'<ul class="map-key">{"".join(rows)}</ul>'

    svg = (f'<svg viewBox="0 0 {width} {height}" role="img" class="map" '
           f'aria-label="World map of population growth since {start}, with the '
           f'countries named in this framework marked">'
           f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f5f0e4"/>'
           f'<g>{"".join(shapes)}</g><g>{"".join(outline)}</g>'
           f'<g pointer-events="none">{"".join(badges)}</g></svg>')

    return (f'<div class="map-wrap">{svg}'
            f'<div class="legend-row map-legend">{legend}</div>'
            f'{key}'
            f'<p class="map-hint">Hover a country for its growth since {start} '
            f'and its {end} population.</p></div>')
