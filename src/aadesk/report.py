"""Standalone HTML brief and Power BI export.

No plotting library and no external assets: the charts are inline SVG written
here, so a brief can be opened from an e-mail attachment, printed to PDF for an
annex, or committed to a repository and read on a machine with no network.
"""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ensure_dir
from .denominators import Denominators, format_persons
from .disclosure import gate
from .mapview import coverage, render_choropleth
from .rfcheck import Assessment

INK = "#14211d"
PAPER = "#fbfaf6"
TEAL = "#0f6b5c"
OCHRE = "#a85e29"
BRICK = "#9c3b2e"
SLATE = "#5f6b66"
SERIES = ["#0f6b5c", "#a85e29", "#3f6b8f", "#6b7a3f", "#7a4a5c", "#8a6a2f"]

STATUS_COLOR = {
    "monitorable": TEAL,
    "conditional": OCHRE,
    "not monitorable": BRICK,
    "unmatched": SLATE,
}


def _esc(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return html.escape(str(value))


def _line_chart(series: dict[str, pd.DataFrame], width: int = 960, height: int = 320,
                start: int = 1960, index_base: bool = True) -> str:
    """Multi-series line chart in inline SVG.

    Values are indexed to the first year in the window (1960 = 100) so that a
    170-million population and a 16-million one can be compared for pace rather
    than for size, which is what a denominator argument is actually about.
    """
    left, right, top, bottom = 64, 16, 18, 44
    plot_w, plot_h = width - left - right, height - top - bottom
    frames: dict[str, pd.DataFrame] = {}
    for label, frame in series.items():
        frame = frame[frame["year"] >= start].copy()
        if frame.empty:
            continue
        if index_base:
            base = float(frame["population"].iloc[0]) or 1.0
            frame["value"] = frame["population"] / base * 100.0
        else:
            frame["value"] = frame["population"]
        frames[label] = frame

    years = sorted({int(y) for frame in frames.values() for y in frame["year"]})
    if not years:
        return ""
    y_max = max(float(frame["value"].max()) for frame in frames.values())

    def x_of(year: float) -> float:
        return left + (year - years[0]) / max(1, years[-1] - years[0]) * plot_w

    def y_of(value: float) -> float:
        return top + plot_h - (value / y_max) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Population denominators by country, indexed" class="chart">']

    for tick in range(0, 5):
        value = y_max * tick / 4
        y = y_of(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" '
                     f'stroke="#e2ddd2" stroke-width="1"/>')
        label = f"{value:,.0f}" if index_base else f"{value/1e6:,.0f}m"
        parts.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" '
                     f'class="tick">{label}</text>')

    step = max(1, (years[-1] - years[0]) // 5)
    for year in range(years[0], years[-1] + 1, step):
        parts.append(f'<text x="{x_of(year):.1f}" y="{height-16}" text-anchor="middle" '
                     f'class="tick">{year}</text>')

    for index, (label, frame) in enumerate(frames.items()):
        color = SERIES[index % len(SERIES)]
        points = " ".join(f'{x_of(int(row.year)):.1f},{y_of(float(row.value)):.1f}'
                          for row in frame.itertuples())
        parts.append(f'<polyline id="series-{index}" data-i="{index}" points="{points}" '
                     f'fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round"/>')
        last = frame.iloc[-1]
        parts.append(f'<circle cx="{x_of(int(last.year)):.1f}" '
                     f'cy="{y_of(float(last.value)):.1f}" r="3.4" fill="{color}"/>')

    parts.append("</svg>")

    legend = "".join(
        f'<span class="legend" data-i="{i}" onclick="aadeskSeries(this)" '
        f'role="button" tabindex="0" title="Toggle this series">'
        f'<i style="background:{SERIES[i % len(SERIES)]}"></i>{_esc(label)}</span>'
        for i, label in enumerate(frames))
    return (f'<div class="chart-wrap">{"".join(parts)}'
            f'<div class="legend-row">{legend}</div></div>')


def _pills(assessment: Assessment) -> str:
    colour = STATUS_COLOR.get(assessment.status, SLATE)
    return (f'<span class="pill" style="--c:{colour}">'
            f'{_esc(assessment.status)}</span>')


def _flag_lines(assessment: Assessment, limit: int = 3) -> str:
    rows = []
    for check in assessment.checks:
        if check.status == "pass":
            continue
        rows.append(f'<li><b>{_esc(check.name)}</b> — {_esc(check.detail)}</li>')
    if not rows:
        return '<span class="muted">no caveats</span>'
    return "<ul class='flags'>" + "".join(rows[:limit]) + "</ul>"


def build_brief(assessments: list[Assessment], denominators: Denominators,
                countries: list[str], out_path: Path | str,
                title: str = "Results framework monitorability",
                publication: str = "public",
                summary: dict | None = None,
                baseline_year: int | None = None,
                reference_year: int | None = None) -> Path:
    generated = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    counts = summary or {}
    total = counts.get("total", len(assessments))
    ok = counts.get("monitorable", 0)
    caution = counts.get("conditional", 0)
    blocked = counts.get("not_monitorable", 0) + counts.get("unmatched", 0)

    # Series for the chart: countries actually named in the framework.
    series = {}
    for country in countries:
        frame = denominators.series(country, start=1960)
        if not frame.empty:
            resolved, _ = denominators.resolve(country)
            series[resolved or country] = frame

    chart = _line_chart(series) if series else "<p class='muted'>No country resolvable.</p>"
    map_html = render_choropleth(denominators, countries) if countries else ""
    covered, drawn = coverage(denominators)
    series_start, series_end = 1960, denominators.year_range[1]

    chips = (
        '<div class="chips">'
        f'<button class="chip is-on" data-f="all" onclick="aadeskFilter(\'all\')">'
        f'All {total}</button>'
        f'<button class="chip" data-f="monitorable" onclick="aadeskFilter(\'monitorable\')">'
        f'Monitorable {ok}</button>'
        f'<button class="chip" data-f="conditional" onclick="aadeskFilter(\'conditional\')">'
        f'Conditional {caution}</button>'
        f'<button class="chip" data-f="none" onclick="aadeskFilter(\'none\')">'
        f'No data trail {blocked}</button>'
        '</div>'
    )

    # Denominator drift table.
    drift_rows = ""
    baseline = baseline_year or reference_year
    if reference_year and countries:
        drift = denominators.drift(countries, baseline, reference_year)
        for row in drift.itertuples():
            change = getattr(row, "change_pct", None)
            before = getattr(row, f"population_{baseline}", None)
            after = getattr(row, f"population_{reference_year}", None)
            change_text = "–" if change is None else f"{change:+.1f}%"
            since = denominators.value(row.country_matched, 1960)
            growth = ((after / since) - 1) * 100 if (since and after) else None
            growth_text = "–" if growth is None else f"{growth:+.0f}%"
            drift_rows += (
                "<tr>"
                f"<td>{_esc(row.country_matched or row.country_input)}</td>"
                f"<td class='num'>{format_persons(before)}</td>"
                f"<td class='num'>{format_persons(after)}</td>"
                f"<td class='num'>{change_text}</td>"
                f"<td class='num'>{growth_text}</td>"
                "</tr>"
            )

    # Where the caveats come from.
    warn_counts = Counter(c.name for a in assessments for c in a.checks if c.status == "warn")
    fail_counts = Counter(c.name for a in assessments for c in a.checks if c.status == "fail")
    merged = warn_counts + fail_counts
    causes = ""
    if merged:
        ceiling = max(merged.values())
        for name, count in merged.most_common():
            share = count / ceiling * 100
            colour = BRICK if fail_counts.get(name, 0) > warn_counts.get(name, 0) else OCHRE
            causes += (
                "<li>"
                f"<span class='cause-name'>{_esc(name)}</span>"
                f"<span class='cause-bar'><i style='width:{share:.0f}%;background:{colour}'></i></span>"
                f"<span class='cause-count'>{count}</span>"
                "</li>"
            )

    # Indicator table.
    rows = ""
    for assessment in assessments:
        rows += (
            f"<tr data-status='{_esc(assessment.status)}'>"
            f"<td class='w40'><span class='lvl'>{_esc(assessment.result_level)}</span>"
            f"{_esc(assessment.indicator_text)}</td>"
            f"<td><code>{_esc(assessment.matched_id or '—')}</code></td>"
            f"<td>{_pills(assessment)}</td>"
            f"<td class='w35'>{_flag_lines(assessment)}</td>"
            "</tr>"
        )

    # Disclosure decisions.
    decisions = ""
    for assessment in assessments:
        if not assessment.matched_id:
            continue
        matched = next((c for c in assessment.checks if c.name == "disclosure"), None)
        if matched is None:
            continue
        colour = {"pass": TEAL, "warn": OCHRE, "fail": BRICK}[matched.status]
        decisions += (f"<li><span class='dot' style='background:{colour}'></span>"
                      f"<b>{_esc(assessment.matched_id)}</b> {_esc(matched.detail)}</li>")

    headline = (
        f"{ok} of {total} indicator{'s are' if total != 1 else ' is'} backed by data that "
        f"exists at the promised geography, cadence and disaggregation. {caution} more are "
        f"reportable only with a stated caveat, and {blocked} have no identified data trail "
        f"and will need either reformulation or a funded collection instrument."
    )
    partial_count = warn_counts.get("availability", 0)
    second_lead = ""
    if partial_count:
        second_lead = (
            f"The binding constraint is not the absence of hazard data: {partial_count} "
            "indicators sit on sources that exist, are documented and are licensed, yet need "
            "a join to administrative boundaries, a survey round, or a partner agreement before "
            "they can be reported on a schedule."
        )

    template = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
  :root {{ --ink:{INK}; --paper:{PAPER}; --teal:{TEAL}; --ochre:{OCHRE};
           --brick:{BRICK}; --slate:{SLATE}; --rule:#ded8cb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
          font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue",Arial,sans-serif;
          font-size:15px; line-height:1.55; }}
  .sheet {{ max-width:1040px; margin:0 auto; padding:56px 40px 72px; }}
  .eyebrow {{ font-size:11px; letter-spacing:.14em; text-transform:uppercase;
              color:var(--teal); font-weight:600; }}
  h1 {{ font-size:34px; line-height:1.2; margin:10px 0 8px; letter-spacing:-.02em; }}
  .meta {{ color:var(--slate); font-size:13px; }}
  .rule {{ height:2px; background:var(--ink); margin:26px 0 0; }}
  .lead {{ font-size:16px; max-width:74ch; margin:26px 0 0; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
           background:var(--rule); border:1px solid var(--rule); margin:34px 0 0; }}
  .kpi {{ background:#fff; padding:18px 18px 16px; }}
  .kpi .n {{ font-size:30px; font-weight:650; letter-spacing:-.02em; line-height:1.1; }}
  .kpi .k {{ font-size:11px; letter-spacing:.09em; text-transform:uppercase;
             color:var(--slate); margin-top:8px; }}
  .kpi.good .n {{ color:var(--teal); }} .kpi.warn .n {{ color:var(--ochre); }}
  .kpi.bad .n {{ color:var(--brick); }}
  h2 {{ font-size:13px; letter-spacing:.1em; text-transform:uppercase; margin:44px 0 12px;
        padding-bottom:7px; border-bottom:1px solid var(--rule); }}
  table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
  th {{ text-align:left; font-weight:600; font-size:11px; letter-spacing:.07em;
        text-transform:uppercase; color:var(--slate); padding:8px 10px;
        border-bottom:1px solid var(--rule); }}
  td {{ padding:11px 10px; border-bottom:1px solid #eee9df; vertical-align:top; }}
  .w40 {{ width:40%; }} .w35 {{ width:33%; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px;
          background:#f1eee6; padding:1px 5px; border-radius:3px; }}
  .lvl {{ display:inline-block; font-size:10px; letter-spacing:.06em; text-transform:uppercase;
          color:var(--slate); border:1px solid var(--rule); border-radius:2px;
          padding:0 4px; margin-right:7px; vertical-align:1px; }}
  .pill {{ display:inline-block; font-size:11.5px; padding:2px 9px; border-radius:11px;
           color:var(--c); border:1px solid var(--c); white-space:nowrap;
           background:color-mix(in srgb, var(--c) 8%, white); }}
  .flags {{ margin:0; padding-left:15px; font-size:12.5px; color:#43504b; }}
  .flags li {{ margin:0 0 4px; }}
  .flags b {{ color:var(--ink); font-weight:600; }}
  .muted {{ color:var(--slate); font-size:12.5px; }}
  .chart-wrap {{ background:#fff; border:1px solid var(--rule); padding:10px 6px 6px; }}
  .chart {{ width:100%; height:auto; display:block; }}
  .tick {{ font-size:10.5px; fill:#8a938e; }}
  .legend-row {{ display:flex; flex-wrap:wrap; gap:14px; padding:4px 14px 10px; }}
  .legend {{ font-size:11.5px; color:var(--slate); display:inline-flex; align-items:center; gap:6px; }}
  .legend i {{ width:14px; height:2.5px; display:inline-block; }}
  .legend {{ cursor:pointer; }}
  .chips {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .chip {{ font:inherit; font-size:11.5px; letter-spacing:0; text-transform:none;
           padding:3px 10px; border:1px solid var(--rule); border-radius:11px;
           background:#fff; color:var(--slate); cursor:pointer; }}
  .chip.is-on {{ border-color:var(--ink); color:var(--ink); }}
  h2.split {{ display:flex; align-items:center; justify-content:space-between;
              gap:14px; flex-wrap:wrap; }}
  .map-wrap {{ background:#fff; border:1px solid var(--rule); padding:10px 12px 8px; }}
  .map {{ width:100%; height:auto; display:block; }}
  .geo {{ cursor:default; }}
  .geo:hover {{ filter:brightness(0.93); }}
  .badge {{ font-size:10px; font-weight:600; fill:#fff; }}
  .swatch {{ font-size:11.5px; color:var(--slate); display:inline-flex;
             align-items:center; gap:6px; }}
  .swatch i {{ width:11px; height:11px; display:inline-block; border-radius:2px; }}
  .map-key {{ list-style:none; margin:12px 0 0; padding:0; display:flex;
              flex-wrap:wrap; gap:8px 22px; font-size:12.5px; }}
  .map-key li {{ display:inline-flex; align-items:baseline; gap:7px; }}
  .badge-n {{ display:inline-block; width:15px; height:15px; line-height:15px;
              border-radius:50%; background:var(--ink); color:#fff; font-size:9.5px;
              text-align:center; font-weight:600; }}
  .badge-v {{ color:var(--ochre); font-variant-numeric:tabular-nums; }}
  .badge-p {{ color:var(--slate); }}
  .map-hint {{ font-size:11px; color:var(--slate); margin:10px 0 0; }}
  #tip {{ position:fixed; display:none; pointer-events:none; background:var(--ink);
          color:#fff; font-size:11.5px; padding:5px 8px; border-radius:2px;
          z-index:20; white-space:nowrap; }}
  ul.decisions {{ list-style:none; margin:0; padding:0; font-size:13px; }}
  ul.decisions li {{ padding:7px 0; border-bottom:1px solid #eee9df; }}
  ul.causes {{ list-style:none; margin:0; padding:0; }}
  ul.causes li {{ display:grid; grid-template-columns:132px 1fr 34px; align-items:center;
                  gap:12px; padding:5px 0; font-size:13px; }}
  .cause-name {{ color:var(--ink); }}
  .cause-bar {{ height:7px; background:#eee9df; border-radius:1px; overflow:hidden; }}
  .cause-bar i {{ display:block; height:100%; }}
  .cause-count {{ text-align:right; font-variant-numeric:tabular-nums; color:var(--slate); }}
  .dot {{ display:inline-block; width:7px; height:7px; border-radius:50%;
          margin-right:9px; vertical-align:1px; }}
  .note {{ background:#fff; border:1px solid var(--rule); border-left:3px solid var(--teal);
           padding:16px 18px; font-size:13px; margin-top:14px; }}
  footer {{ margin-top:52px; padding-top:16px; border-top:1px solid var(--rule);
            font-size:11.5px; color:var(--slate); }}
  footer p {{ margin:0 0 6px; }}
  @media print {{ body {{ background:#fff; }} .sheet {{ padding:0; }}
                  tr[hidden] {{ display:table-row !important; }}
                  .chips, #tip {{ display:none !important; }} }}
</style>
</head>
<body>
<div class="sheet">
  <div class="eyebrow">Anticipatory action data desk</div>
  <h1>{_esc(title)}</h1>
  <div class="meta">Audit of {total} indicators against the humanitarian indicator registry ·
    publication target: {_esc(publication)} · generated {generated}</div>
  <div class="rule"></div>

  <p class="lead">{_esc(headline)}</p>
  {f'<p class="lead">{_esc(second_lead)}</p>' if second_lead else ''}

  <div class="kpis">
    <div class="kpi"><div class="n">{total}</div><div class="k">indicators audited</div></div>
    <div class="kpi good"><div class="n">{ok}</div><div class="k">monitorable as written</div></div>
    <div class="kpi warn"><div class="n">{caution}</div><div class="k">conditional</div></div>
    <div class="kpi bad"><div class="n">{blocked}</div><div class="k">no data trail</div></div>
  </div>

  <h2>Where the caveats come from</h2>
  <ul class="causes">{causes}</ul>
  <p class="muted" style="margin-top:6px">Count of indicators flagged by each check.
    Amber: reportable with a stated caveat. Red: a hard blocker.</p>

  <h2 class="split">Indicator by indicator {chips}</h2>
  <table>
    <thead><tr><th>Indicator</th><th>Registry</th><th>Status</th><th>What stands in the way</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <h2>Denominators, from the ISIMIP national series</h2>
  <p class="muted" style="margin-top:0">Index of national population, 1960 = 100, to 2020.
    Source: ISIMIP2a / HYDE national population, hosted by IIASA, retrieved with checksum verification.</p>
  {chart}

  <h2>Where those denominators sit</h2>
  <p class="muted" style="margin-top:0">{covered} of the {drawn} countries drawn carry a
    row in the series; the rest are grey, not guessed. Growth since {series_start}, from
    the same checksum-verified file.</p>
  {map_html}

  <h2>Why the baseline year matters</h2>
  <table>
    <thead><tr><th>Country</th><th class="num">Population {baseline_year or reference_year}</th>
      <th class="num">Population {reference_year}</th><th class="num">Change</th>
      <th class="num">Since 1960</th></tr></thead>
    <tbody>{drift_rows}</tbody>
  </table>
  <p class="muted">A denominator that moves by several percent between baseline and reporting
    year moves any “share of population” indicator with it, independently of programme effect.</p>

  <h2>Disclosure gate</h2>
  <ul class="decisions">{decisions}</ul>
  <div class="note">Outputs derived from programme systems are aggregated before publication and
    cell counts below five are generalised. The gate refuses record-level fields outright rather
    than relying on reviewer memory.</div>

  <footer>
    <p><b>Provenance.</b> Population series: ISIMIP2a input dataset
      <code>population_histsoc_national_annual</code>, version 20210526, retrieved from
      data.isimip.org; SHA-512 verified against the digest published by the portal.
      Indicator registry: config/registry/indicators.yml, {len(assessments)} assessments this run.</p>
    <p><b>Limitations.</b> The audit tests whether data exists and is usable; it does not test
      whether an indicator measures what its result statement claims. Gridded hazard layers
      (flood, crop) are catalogued and licensed but require an administrative boundary raster
      before they become national indicators.</p>
    <p>Generated by aadesk. Example framework is illustrative and does not describe a real proposal.</p>
  </footer>
</div>
<div id="tip"></div>
<script>
function aadeskFilter(mode) {{
  var rows = document.querySelectorAll("tbody tr");
  for (var i = 0; i < rows.length; i++) {{
    var s = rows[i].getAttribute("data-status") || "";
    var keep = mode === "all" || s === mode ||
               (mode === "none" && (s === "not monitorable" || s === "unmatched"));
    rows[i].hidden = !keep;
  }}
  var chips = document.querySelectorAll(".chip");
  for (var j = 0; j < chips.length; j++) {{
    chips[j].classList.toggle("is-on", chips[j].getAttribute("data-f") === mode);
  }}
}}
function aadeskSeries(el) {{
  var line = document.getElementById("series-" + el.getAttribute("data-i"));
  if (!line) return;
  var off = line.style.display === "none";
  line.style.display = off ? "" : "none";
  el.style.opacity = off ? "1" : "0.4";
}}
(function () {{
  var tip = document.getElementById("tip");
  var geos = document.querySelectorAll(".geo");
  for (var i = 0; i < geos.length; i++) {{
    geos[i].addEventListener("mousemove", function (e) {{
      var v = this.getAttribute("data-v");
      if (!v) {{ tip.style.display = "none"; return; }}
      tip.textContent = this.getAttribute("data-n") + " \u00b7 " + v + " since {series_start}" +
                        " \u00b7 " + this.getAttribute("data-p") + " in {series_end}";
      tip.style.display = "block";
      var left = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      tip.style.left = left + "px";
      tip.style.top = (e.clientY + 16) + "px";
    }});
    geos[i].addEventListener("mouseleave", function () {{ tip.style.display = "none"; }});
  }}
}})();
</script>
</body>
</html>
"""
    out_path = Path(out_path)
    ensure_dir(out_path.parent)
    out_path.write_text(template, encoding="utf-8")
    return out_path


def export_powerbi(assessments: list[Assessment], denominators: Denominators,
                   countries: list[str], out_dir: Path | str) -> dict[str, Path]:
    """Star schema: two dimensions, two facts, ready for Power BI / Fabric."""
    out_dir = ensure_dir(out_dir)
    written: dict[str, Path] = {}

    registry_rows = []
    for assessment in assessments:
        if assessment.matched_id and assessment.matched_id not in {r["indicator_id"] for r in registry_rows}:
            registry_rows.append({
                "indicator_id": assessment.matched_id,
                "indicator_name": assessment.matched_name,
                "availability": next((c.detail for c in assessment.checks
                                      if c.name == "availability"), ""),
                "disclosure": next((c.detail for c in assessment.checks
                                    if c.name == "disclosure"), ""),
            })
    frame = pd.DataFrame(registry_rows)
    written["dim_indicator"] = out_dir / "dim_indicator.csv"
    frame.to_csv(written["dim_indicator"], index=False)

    country_rows = []
    for name in countries:
        resolved, score = denominators.resolve(name)
        if not resolved:
            continue
        latest = denominators.value(resolved, denominators.year_range[1])
        country_rows.append({
            "country": resolved,
            "iso_code": int(denominators.frame.loc[
                denominators.frame["country"] == resolved, "iso_code"].iloc[0]),
            "first_year": denominators.year_range[0],
            "last_year": denominators.year_range[1],
            "population_latest": round(latest or 0),
            "match_score": score,
        })
    written["dim_country"] = out_dir / "dim_country.csv"
    pd.DataFrame(country_rows).to_csv(written["dim_country"], index=False)

    fact_assessment = pd.DataFrame([a.to_row() for a in assessments])
    written["fact_assessment"] = out_dir / "fact_assessment.csv"
    fact_assessment.to_csv(written["fact_assessment"], index=False)

    fact_denominator = denominators.frame[denominators.frame["country"].isin(
        [denominators.resolve(c)[0] for c in countries if denominators.resolve(c)[0]])]
    fact_denominator = fact_denominator[fact_denominator["year"] >= 1960]
    written["fact_denominator"] = out_dir / "fact_denominator.csv"
    fact_denominator[["country", "year", "population"]].to_csv(
        written["fact_denominator"], index=False)

    measures = out_dir / "measures.dax"
    measures.write_text(
        "// Paste each line into Model view → New measure (Power BI Desktop).\n"
        "Indicators audited = COUNTROWS ( fact_assessment )\n"
        "\n"
        "Monitorable = CALCULATE ( COUNTROWS ( fact_assessment ), "
        "fact_assessment[status] = \"monitorable\" )\n"
        "\n"
        "Monitorable share = DIVIDE ( [Monitorable], [Indicators audited] )\n"
        "\n"
        "Latest denominator year = MAX ( fact_denominator[year] )\n"
        "\n"
        "Population latest = CALCULATE ( SUM ( fact_denominator[population] ), "
        "fact_denominator[year] = [Latest denominator year] )\n"
        "\n"
        "Growth since 1960 = DIVIDE ( [Population latest], "
        "CALCULATE ( SUM ( fact_denominator[population] ), fact_denominator[year] = 1960 ) ) - 1\n",
        encoding="utf-8")
    written["measures"] = measures

    model = out_dir / "model.md"
    model.write_text(
        "# Star schema\n\n"
        "- `fact_assessment` — one row per audited indicator (grain: indicator in framework)\n"
        "- `fact_denominator` — population by country-year (grain: country, year)\n"
        "- `dim_indicator` — registry attributes for matched indicators\n"
        "- `dim_country` — country attributes and coverage\n\n"
        "Join `fact_assessment.matched_id` → `dim_indicator.indicator_id`;\n"
        "`fact_denominator.country` → `dim_country.country`.\n\n"
        "## Opening it in Power BI Desktop\n\n"
        "These are plain CSVs, not a `.pbix`. They are inert until imported —\n"
        "the interactivity (slicers, cross-filtering, drill-down) is what Power BI\n"
        "adds, not what is shipped here.\n\n"
        "1. **Get data ▸ Text/CSV**, `fact_assessment.csv`. In the dialog set\n"
        "   *File origin* to **65001: Unicode (UTF-8)** — the default locale mangles\n"
        "   accented names — then **Load**. Repeat for the other three files.\n"
        "2. **Model view**: drag `dim_indicator[indicator_id]` onto\n"
        "   `fact_assessment[matched_id]`, and `dim_country[country]` onto\n"
        "   `fact_denominator[country]`. Both should be many-to-one, single direction.\n"
        "3. **Model view ▸ New measure**: paste the measures from `measures.dax`,\n"
        "   one at a time.\n"
        "4. A first page that answers the donor question: a **slicer** on\n"
        "   `fact_assessment[status]`, a **card** with `[Monitorable share]`, a\n"
        "   **matrix** of `status` against `geography`, and a **line chart** of\n"
        "   `population` by `year` with `dim_country[country]` as legend.\n"
        "5. **File ▸ Save as** `.pbix` if you want the report itself versioned.\n",
        encoding="utf-8")
    written["model"] = model
    return written


def disclosure_report(assessments: list[Assessment], publication: str) -> list[str]:
    lines = []
    for assessment in assessments:
        if not assessment.matched_id:
            continue
        check = next((c for c in assessment.checks if c.name == "disclosure"), None)
        if check is None:
            continue
        lines.append(f"{assessment.matched_id}: {check.status.upper()} — {check.detail}")
    return lines
