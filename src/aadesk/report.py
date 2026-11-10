"""Standalone HTML brief and Power BI export.

No plotting library and no external assets: the charts are inline SVG written
here, so a brief can be opened from an e-mail attachment, printed to PDF for an
annex, or committed to a repository and read on a machine with no network.
"""

from __future__ import annotations

import html
import json
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
OCHRE = "#a05a1e"
BRICK = "#8b2a33"
TEAL_FILL = "#1c7a52"
AMBER_FILL = "#e3a01f"
CRIMSON_FILL = "#a52a3a"
SLATE = "#5f6b66"
SERIES = ["#0f6b5c", "#a85e29", "#3f6b8f", "#6b7a3f", "#7a4a5c", "#8a6a2f"]

STATUS_COLOR = {
    "monitorable": TEAL,
    "conditional": OCHRE,
    "not monitorable": BRICK,
    "unmatched": SLATE,
}

# Sort order for the table, worst last: a reader sorts by severity, not alphabet.
STATUS_RANK = {"monitorable": 0, "conditional": 1, "not monitorable": 2, "unmatched": 3}


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

    colours = {label: SERIES[i % len(SERIES)] for i, label in enumerate(frames)}
    for index, (label, frame) in enumerate(frames.items()):
        color = colours[label]
        points = " ".join(f'{x_of(int(row.year)):.1f},{y_of(float(row.value)):.1f}'
                          for row in frame.itertuples())
        parts.append(f'<polyline id="series-{index}" data-i="{index}" points="{points}" '
                     f'fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round"/>')
        last = frame.iloc[-1]
        parts.append(f'<circle id="dot-{index}" cx="{x_of(int(last.year)):.1f}" '
                     f'cy="{y_of(float(last.value)):.1f}" r="3.4" fill="{color}"/>')

    # Hover bands carry their own values, so reading a year needs no lookup table
    # and no second copy of the data in the page.
    by_year: dict[int, dict[str, list]] = {}
    for label, frame in frames.items():
        for row in frame.itertuples():
            by_year.setdefault(int(row.year), {})[label] = [
                colours[label], round(float(row.value), 1)]

    span = plot_w / max(1, len(years) - 1)
    parts.append(f'<line class="guide" x1="0" x2="0" y1="{top}" y2="{top + plot_h}" '
                 f'stroke="#b9b2a2" stroke-width="1" style="display:none"/>')
    for year, values in sorted(by_year.items()):
        payload = json.dumps(values, separators=(",", ":")).replace("'", "&#39;")
        parts.append(f'<rect class="hb" x="{x_of(year) - span / 2:.1f}" y="{top}" '
                     f'width="{span:.1f}" height="{plot_h}" fill="transparent" '
                     f'data-y="{year}" data-v=\'{payload}\'/>')

    parts.append("</svg>")

    legend = "".join(
        f'<span class="legend" data-i="{i}" onclick="aadeskSeries(this)" '
        f'role="button" tabindex="0" title="Toggle this series">'
        f'<i style="background:{SERIES[i % len(SERIES)]}"></i>{_esc(label)}</span>'
        for i, label in enumerate(frames))
    return (f'<div class="chart-wrap" id="chart">{"".join(parts)}'
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


CSS = """
:root{--ink:#14211d;--paper:#fbfaf6;--card:#fff;--teal:#0f6b5c;--ochre:#a05a1e;
      --brick:#8b2a33;--slate:#5f6b66;--rule:#e2ddd2;--hair:#efeae0;
      --green:#1c7a52;--amber:#e3a01f;--crimson:#a52a3a;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
     font:15px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue",Arial,sans-serif;
     -webkit-font-smoothing:antialiased;}
.sheet{max-width:1060px;margin:0 auto;padding:0 40px 64px;}
.serif{font-family:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;}

/* masthead */
.top{display:flex;align-items:baseline;justify-content:space-between;gap:20px;
     padding:44px 0 12px;border-bottom:2px solid var(--ink);}
.brand{font-size:12px;letter-spacing:.24em;text-transform:uppercase;font-weight:700;}
.brand span{color:var(--slate);font-weight:400;letter-spacing:.12em;}
.issue{font-size:11px;color:var(--slate);letter-spacing:.05em;font-variant-numeric:tabular-nums;}
h1{font-family:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;
   font-weight:600;font-size:46px;line-height:1.08;letter-spacing:-.018em;
   margin:34px 0 0;}
.standfirst{font-family:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;
            font-size:20px;line-height:1.44;color:#273731;margin:20px 0 0;}
.standfirst.sub{font-size:16.5px;color:#43514b;margin-top:12px;}
.dateline{display:flex;flex-wrap:wrap;gap:10px 26px;margin:26px 0 0;
          font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--slate);}
.dateline b{color:var(--ink);font-weight:600;}

/* section nav */
nav{position:sticky;top:0;z-index:9;background:var(--paper);
    border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin-top:34px;
    display:flex;flex-wrap:nowrap;overflow-x:auto;}
nav a{display:flex;align-items:baseline;gap:8px;padding:12px 15px 10px;white-space:nowrap;
      font-size:12px;font-weight:650;letter-spacing:.005em;color:var(--ink);
      text-decoration:none;border-right:1px solid var(--hair);
      border-bottom:3px solid transparent;}
nav a b{font-size:9.5px;font-weight:700;letter-spacing:.08em;color:var(--ochre);
        font-variant-numeric:tabular-nums;}
nav a:hover{background:var(--card);border-bottom-color:var(--ochre);}
nav a.is-current{background:var(--ink);color:var(--paper);border-bottom-color:var(--ink);}
nav a.is-current b{color:var(--amber);}

/* sections */
section{padding-top:46px;scroll-margin-top:56px;}
.shead{display:flex;align-items:baseline;justify-content:space-between;gap:14px;
       flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:10px;margin-bottom:22px;}
.shead h2{margin:0;font-family:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;
          font-size:22px;font-weight:600;letter-spacing:-.01em;display:flex;align-items:baseline;gap:13px;}
.sno{font-size:10.5px;letter-spacing:.12em;color:var(--slate);font-variant-numeric:tabular-nums;}
.dek{margin:0 0 18px;color:var(--slate);font-size:13px;}

/* kpis */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--rule);
      border-bottom:1px solid var(--rule);}
.kpi{padding:22px 20px 20px;border-right:1px solid var(--hair);}
.kpi:last-child{border-right:0;}
.kpi .n{font-family:ui-serif,Georgia,"Iowan Old Style",serif;font-size:40px;line-height:1;
        letter-spacing:-.02em;font-variant-numeric:tabular-nums;}
.kpi .k{font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:var(--slate);
        margin-top:10px;}
.kpi.good .n{color:var(--teal);} .kpi.warn .n{color:var(--ochre);} .kpi.bad .n{color:var(--brick);}
.band{display:flex;height:14px;margin:24px 0 0;}
.band i{display:block;height:100%;box-shadow:inset -2px 0 0 var(--paper);}
.bandkey{display:flex;flex-wrap:wrap;gap:10px 24px;margin-top:11px;font-size:11.5px;color:var(--slate);}
.bandkey span::before{content:"";display:inline-block;width:11px;height:11px;margin-right:8px;
                      background:var(--c);vertical-align:-1px;}
.bandkey b{color:var(--ink);font-variant-numeric:tabular-nums;margin-right:3px;}

/* table */
.tbl{width:100%;border-collapse:collapse;font-size:13.5px;}
.tbl th{text-align:left;font-size:10.5px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;
        color:var(--slate);padding:9px 10px;border-bottom:1px solid var(--rule);
        cursor:pointer;user-select:none;white-space:nowrap;}
.tbl th.num{text-align:right;}
.tbl th:hover{color:var(--ink);}
.tbl th[data-dir="asc"]::after{content:" ↑";color:var(--ink);}
.tbl th[data-dir="desc"]::after{content:" ↓";color:var(--ink);}
.tbl td{padding:12px 10px;border-bottom:1px solid var(--hair);vertical-align:top;}
.tbl td code{white-space:nowrap;}
.tbl tbody tr:hover{background:var(--card);}
.tbl .num{text-align:right;font-variant-numeric:tabular-nums;}
.w40{width:40%;} .w35{width:33%;}
.lvl{display:inline-block;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;
     color:var(--slate);border:1px solid var(--rule);padding:1px 5px;margin-right:8px;
     vertical-align:1px;}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:11px;letter-spacing:.02em;
      padding:3px 9px;border:1px solid var(--c);color:var(--c);white-space:nowrap;
      background:color-mix(in srgb,var(--c) 7%,white);}
.pill::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--c);}
.flags{margin:0;padding:0;list-style:none;font-size:12.5px;color:#41514b;}
.flags li{position:relative;padding-left:11px;margin-bottom:5px;}
.flags li::before{content:"";position:absolute;left:0;top:7px;width:1px;height:11px;background:var(--ochre);}

/* chips */
.chips{display:flex;gap:6px;flex-wrap:wrap;}
.chip{font:inherit;font-size:11px;letter-spacing:.02em;padding:4px 11px;
      border:1px solid var(--rule);background:var(--card);color:var(--slate);cursor:pointer;
      border-radius:0;}
.chip:hover{border-color:var(--slate);color:var(--ink);}
.chip.is-on{border-color:var(--ink);background:var(--ink);color:var(--paper);}

/* chart + map cards */
.card{background:var(--card);border:1px solid var(--rule);}
.chart-wrap{padding:16px 14px 8px;}
.chart{width:100%;height:auto;display:block;}
.tick{font-size:10.5px;fill:#8a938e;}
.legend-row{display:flex;flex-wrap:wrap;gap:16px;padding:8px 14px 12px;}
.legend{font-size:11.5px;color:var(--slate);display:inline-flex;align-items:center;gap:7px;
        cursor:pointer;}
.legend i{width:15px;height:2.5px;display:inline-block;}
.legend:hover{color:var(--ink);}
.map-wrap{background:var(--card);border:1px solid var(--rule);padding:14px 16px 12px;}
.map{width:100%;height:auto;display:block;}
.geo{cursor:default;} .geo:hover{filter:brightness(.94);}
.badge{font-size:10px;font-weight:600;fill:#fff;}
.swatch{font-size:11.5px;color:var(--slate);display:inline-flex;align-items:center;gap:7px;}
.swatch i{width:11px;height:11px;display:inline-block;}
.map-key{list-style:none;margin:14px 0 0;padding:0;display:flex;flex-wrap:wrap;
         gap:10px 26px;font-size:12.5px;}
.map-key li{display:inline-flex;align-items:baseline;gap:7px;}
.badge-n{display:inline-block;width:16px;height:16px;line-height:16px;text-align:center;
         background:var(--ink);color:#fff;font-size:9.5px;font-weight:600;border-radius:50%;}
.badge-v{color:var(--ochre);font-variant-numeric:tabular-nums;}
.badge-p{color:var(--slate);}
.map-hint,.hint{font-size:11px;color:var(--slate);margin:10px 0 0;}

/* causes */
ul.causes{list-style:none;margin:0;padding:0;}
ul.causes li{display:grid;grid-template-columns:140px 1fr 34px;align-items:center;gap:14px;
             padding:7px 0;font-size:13px;border-bottom:1px solid var(--hair);}
ul.causes li:last-child{border-bottom:0;}
.cause-name{color:var(--ink);}
.cause-bar{height:8px;background:var(--hair);}
.cause-bar i{display:block;height:100%;}
.cause-count{text-align:right;font-variant-numeric:tabular-nums;color:var(--slate);}

/* disclosure */
ul.decisions{list-style:none;margin:0;padding:0;font-size:13px;}
ul.decisions li{padding:8px 0;border-bottom:1px solid var(--hair);}
ul.decisions li:last-child{border-bottom:0;}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:9px;vertical-align:1px;}
.note{background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--teal);
      padding:15px 18px;font-size:12.5px;margin-top:16px;color:#3d4b45;}

/* pipeline */
.flow{display:grid;grid-template-columns:1fr 26px 1fr 26px 1fr 26px 1fr;margin:4px 0 0;}
.fstage{background:var(--card);border:1px solid var(--rule);border-top:3px solid var(--ink);
        padding:14px 14px 16px;}
.fno{font-size:9.5px;letter-spacing:.14em;font-weight:700;color:var(--ochre);}
.fstage h3{margin:7px 0 6px;font-size:12.5px;font-weight:650;letter-spacing:-.005em;}
.fstage p{margin:0;font-size:11.5px;line-height:1.5;color:var(--slate);}
.farrow{display:flex;align-items:center;justify-content:center;color:var(--ochre);font-size:16px;}
.fout{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--rule);
      margin-top:10px;background:var(--card);}
.fout div{padding:12px 14px;border-right:1px solid var(--hair);font-size:11.5px;color:var(--slate);}
.fout div:last-child{border-right:0;}
.fout b{display:block;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink);
        margin-bottom:4px;}

footer{margin-top:26px;font-size:11.5px;line-height:1.65;color:var(--slate);}
footer p{margin:0 0 7px;}
footer b{color:var(--ink);font-weight:600;}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
     background:var(--hair);padding:1px 5px;}
a{color:var(--teal);}

/* tooltip */
#tip{position:fixed;display:none;pointer-events:none;z-index:20;max-width:280px;
     background:var(--ink);color:#fff;font-size:11.5px;line-height:1.55;padding:8px 10px;}
#tip b{display:block;font-size:11px;letter-spacing:.1em;margin-bottom:4px;opacity:.75;}
.tdot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;}

@media (max-width:820px){
  .sheet{padding:0 20px 48px;}
  h1{font-size:30px;} .standfirst{font-size:18px;}
  .kpis{grid-template-columns:repeat(2,1fr);}
  .kpi:nth-child(2){border-right:0;}
  .kpi:nth-child(1),.kpi:nth-child(2){border-bottom:1px solid var(--hair);}
  .flow{grid-template-columns:1fr;}
  .farrow{height:22px;} .fout{grid-template-columns:1fr;}
  .fout div{border-right:0;border-bottom:1px solid var(--hair);}
}
@media print{
  body{background:#fff;font-size:11px;}
  .sheet{max-width:none;padding:0;}
  nav,.chips,#tip,.map-hint,.hint{display:none!important;}
  #s3 .dek{display:none;}
  tr[hidden]{display:table-row!important;}
  .tbl th{position:static;cursor:default;}
  section{padding-top:20px;}
  .shead{break-after:avoid;}
  .card,.map-wrap,.flow,.fout,ul.decisions li{break-inside:avoid;}
  .flow{grid-template-columns:1fr 22px 1fr 22px 1fr 22px 1fr;margin-top:14px;}
  .fstage{break-inside:avoid;}
  .fout{grid-template-columns:repeat(3,1fr);}
  h1{font-size:28px;} .standfirst{font-size:15px;color:#000;}
  a{color:inherit;text-decoration:none;}
  @page{margin:16mm;}
}
"""

JS = """
var START = document.body.getAttribute("data-start") || "";
var END = document.body.getAttribute("data-end") || "";

function aadeskFilter(mode) {
  var rows = document.querySelectorAll("#s3 tbody tr");
  for (var i = 0; i < rows.length; i++) {
    var s = rows[i].getAttribute("data-status") || "";
    var keep = mode === "all" || s === mode ||
               (mode === "none" && (s === "not monitorable" || s === "unmatched"));
    rows[i].hidden = !keep;
  }
  var chips = document.querySelectorAll(".chip");
  for (var j = 0; j < chips.length; j++) {
    chips[j].classList.toggle("is-on", chips[j].getAttribute("data-f") === mode);
  }
}

function aadeskSeries(el) {
  var i = el.getAttribute("data-i");
  var line = document.getElementById("series-" + i);
  var dot = document.getElementById("dot-" + i);
  if (!line) return;
  var off = line.style.display === "none";
  line.style.display = off ? "" : "none";
  if (dot) dot.style.display = off ? "" : "none";
  el.style.opacity = off ? "1" : "0.45";
}

function aadeskSort(th, kind) {
  var table = th.closest("table");
  var body = table.tBodies[0];
  var rows = Array.prototype.slice.call(body.rows);
  var col = Array.prototype.indexOf.call(th.parentNode.children, th);
  var asc = th.getAttribute("data-dir") !== "asc";
  var heads = table.tHead.rows[0].cells;
  for (var h = 0; h < heads.length; h++) heads[h].removeAttribute("data-dir");

  rows.sort(function (a, b) {
    var x = a.cells[col], y = b.cells[col];
    if (kind === "num") {
      var nx = parseFloat(x.getAttribute("data-v"));
      var ny = parseFloat(y.getAttribute("data-v"));
      if (isNaN(nx)) nx = Infinity;
      if (isNaN(ny)) ny = Infinity;
      return asc ? nx - ny : ny - nx;
    }
    if (kind === "status") {
      var sx = parseInt(x.getAttribute("data-v") || "9", 10);
      var sy = parseInt(y.getAttribute("data-v") || "9", 10);
      return asc ? sx - sy : sy - sx;
    }
    var tx = x.textContent.trim().toLowerCase();
    var ty = y.textContent.trim().toLowerCase();
    return asc ? (tx < ty ? -1 : tx > ty ? 1 : 0) : (tx > ty ? -1 : tx < ty ? 1 : 0);
  });
  for (var i = 0; i < rows.length; i++) body.appendChild(rows[i]);
  th.setAttribute("data-dir", asc ? "asc" : "desc");
}

(function () {
  var tip = document.getElementById("tip");
  var chart = document.getElementById("chart");
  if (chart) {
    var guide = chart.querySelector(".guide");
    chart.addEventListener("mouseout", function (e) {
      if (e.relatedTarget && chart.contains(e.relatedTarget)) return;
      tip.style.display = "none";
      if (guide) guide.style.display = "none";
    });
    chart.addEventListener("mousemove", function (e) {
      var band = e.target.closest(".hb");
      if (!band) {
        tip.style.display = "none";
        if (guide) guide.style.display = "none";
        return;
      }
      var data = JSON.parse(band.getAttribute("data-v"));
      var html = "<b>" + band.getAttribute("data-y") + "</b>";
      for (var name in data) {
        html += '<span class="tdot" style="background:' + data[name][0] + '"></span>' +
                name + " &nbsp;" + Math.round(data[name][1]);
      }
      tip.innerHTML = html;
      tip.style.display = "block";
      var left = Math.min(e.clientX + 16, window.innerWidth - tip.offsetWidth - 8);
      var top = Math.min(e.clientY + 18, window.innerHeight - tip.offsetHeight - 8);
      tip.style.left = Math.max(8, left) + "px";
      tip.style.top = Math.max(8, top) + "px";
      if (guide) {
        var cx = parseFloat(band.getAttribute("x")) +
                 parseFloat(band.getAttribute("width")) / 2;
        guide.setAttribute("x1", cx);
        guide.setAttribute("x2", cx);
        guide.style.display = "block";
      }
    });
  }
  var geos = document.querySelectorAll(".geo");
  for (var i = 0; i < geos.length; i++) {
    geos[i].addEventListener("mousemove", function (e) {
      var v = this.getAttribute("data-v");
      if (!v) { tip.style.display = "none"; return; }
      tip.textContent = this.getAttribute("data-n") + " \u00b7 " + v +
                        " since " + START + " \u00b7 " + this.getAttribute("data-p") +
                        " in " + END;
      tip.style.display = "block";
      var left = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      tip.style.left = left + "px";
      tip.style.top = (e.clientY + 16) + "px";
    });
  }

  /* contents bar: mark the section in view */
  var links = document.querySelectorAll("nav a");
  var ids = [];
  for (var k = 0; k < links.length; k++) ids.push(links[k].getAttribute("href").slice(1));
  function markCurrent() {
    var at = window.scrollY + 150, best = 0;
    for (var m = 0; m < ids.length; m++) {
      var sec = document.getElementById(ids[m]);
      if (sec && sec.offsetTop <= at) best = m;
    }
    for (var n = 0; n < links.length; n++) {
      if (n === best) links[n].classList.add("is-current");
      else links[n].classList.remove("is-current");
    }
  }
  window.addEventListener("scroll", markCurrent, { passive: true });
  window.addEventListener("resize", markCurrent);
  markCurrent();
})();
"""


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
                f"<td class='num' data-v='{'null' if before is None else before}'>{format_persons(before)}</td>"
                f"<td class='num' data-v='{'null' if after is None else after}'>{format_persons(after)}</td>"
                f"<td class='num' data-v='{'null' if change is None else change}'>{change_text}</td>"
                f"<td class='num' data-v='{'null' if growth is None else growth}'>{growth_text}</td>"
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
            f"<td data-v=\'{STATUS_RANK.get(assessment.status, 9)}\'>{_pills(assessment)}</td>"
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
        f"{ok} of {total} indicators {'is' if ok == 1 else 'are'} backed by data that "
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
<style>{CSS}</style>
</head>
<body data-start="{series_start}" data-end="{series_end}">
<div class="sheet">

  <div class="top">
    <div class="brand">Aadesk <span>&middot; results framework audit</span></div>
    <div class="issue">{generated}</div>
  </div>

  <h1>{_esc(title)}</h1>
  <p class="standfirst">{_esc(headline)}</p>
  {f'<p class="standfirst sub">{_esc(second_lead)}</p>' if second_lead else ''}

  <div class="dateline">
    <span><b>{total}</b> indicators</span>
    <span>registry <b>v1</b></span>
    <span>intended output <b>{_esc(publication)}</b></span>
    <span>baseline <b>{baseline_year or '—'}</b> &rarr; reporting <b>{reference_year or '—'}</b></span>
  </div>

  <nav aria-label="Contents">
    <a href="#s1"><b>01</b>Verdict</a>
    <a href="#s2"><b>02</b>Caveats</a>
    <a href="#s3"><b>03</b>Line by line</a>
    <a href="#s4"><b>04</b>Denominators</a>
    <a href="#s5"><b>05</b>Map</a>
    <a href="#s6"><b>06</b>Baseline</a>
    <a href="#s7"><b>07</b>Disclosure</a>
    <a href="#s8"><b>08</b>Method</a>
  </nav>

  <section id="s1">
    <div class="shead"><h2><span class="sno">01</span>The verdict, before signature</h2></div>
    <div class="kpis">
      <div class="kpi"><div class="n">{total}</div><div class="k">indicators audited</div></div>
      <div class="kpi good"><div class="n">{ok}</div><div class="k">monitorable as written</div></div>
      <div class="kpi warn"><div class="n">{caution}</div><div class="k">conditional</div></div>
      <div class="kpi bad"><div class="n">{blocked}</div><div class="k">no data trail</div></div>
    </div>
    <div class="band">
      <i style="width:{ok / max(total, 1) * 100:.2f}%;background:{TEAL_FILL}"></i>
      <i style="width:{caution / max(total, 1) * 100:.2f}%;background:{AMBER_FILL}"></i>
      <i style="width:{blocked / max(total, 1) * 100:.2f}%;background:{CRIMSON_FILL}"></i>
    </div>
    <div class="bandkey">
      <span style="--c:{TEAL_FILL}"><b>{ok}</b>monitorable as written</span>
      <span style="--c:{AMBER_FILL}"><b>{caution}</b>reportable with a caveat</span>
      <span style="--c:{CRIMSON_FILL}"><b>{blocked}</b>needs reformulation or a collection instrument</span>
    </div>
  </section>

  <section id="s2">
    <div class="shead"><h2><span class="sno">02</span>Where the caveats come from</h2></div>
    <p class="dek">Count of indicators flagged by each check. The bar length is the count;
      the colour says whether the check stopped the indicator or merely qualified it.</p>
    <ul class="causes">{causes}</ul>
  </section>

  <section id="s3">
    <div class="shead">
      <h2><span class="sno">03</span>Indicator by indicator</h2>
      {chips}
    </div>
    <p class="dek">Click a column heading to sort. The pill is the verdict; the column beside
      it names the exact constraint, so it can be fixed rather than argued about.</p>
    <table class="tbl">
      <thead><tr>
        <th data-sort="text">Indicator</th>
        <th data-sort="text">Registry</th>
        <th data-sort="status">Status</th>
        <th data-sort="text">What stands in the way</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>

  <section id="s4">
    <div class="shead"><h2><span class="sno">04</span>Denominators, over time</h2></div>
    <p class="dek">Index of national population, 1960 = 100, to {series_end}. Source: ISIMIP2a /
      HYDE national population, hosted by IIASA, retrieved with checksum verification.
      Hover a year for the values; click a legend entry to hide the series.</p>
    {chart}
  </section>

  <section id="s5">
    <div class="shead"><h2><span class="sno">05</span>Where those denominators sit</h2></div>
    <p class="dek">{covered} of the {drawn} countries drawn carry a row in the series; the rest
      are grey, not guessed. Growth since {series_start}, from the same checksum-verified file.</p>
    {map_html}
  </section>

  <section id="s6">
    <div class="shead"><h2><span class="sno">06</span>Why the baseline year matters</h2></div>
    <p class="dek">A denominator that moves by several percent between baseline and reporting
      year moves any “share of population” indicator with it, independently of programme effect.</p>
    <table class="tbl">
      <thead><tr>
        <th data-sort="text">Country</th>
        <th class="num" data-sort="num">Population {baseline_year or reference_year}</th>
        <th class="num" data-sort="num">Population {reference_year}</th>
        <th class="num" data-sort="num">Change</th>
        <th class="num" data-sort="num">Since {series_start}</th>
      </tr></thead>
      <tbody>{drift_rows}</tbody>
    </table>
  </section>

  <section id="s7">
    <div class="shead"><h2><span class="sno">07</span>Disclosure gate</h2></div>
    <ul class="decisions">{decisions}</ul>
    <div class="note">Outputs derived from programme systems are aggregated before publication and
      cell counts below five are generalised. The gate refuses record-level fields outright
      rather than relying on reviewer memory.</div>
  </section>

  <section id="s8">
    <div class="shead"><h2><span class="sno">08</span>How this brief was produced</h2></div>
    <p class="dek">Four stages, no manual step in the middle. The population series behind sections
      four and five is fetched, checksummed and cached by the first stage; everything after it
      reads from disk.</p>
    <div class="flow">
      <div class="fstage"><div class="fno">STAGE 01</div><h3>Evidence, declared</h3>
        <p>Custodian, access condition and licence are written into <code>sources.yml</code> before
          a single indicator is matched. The download records its own provenance and digest.</p></div>
      <div class="farrow" aria-hidden="true">&rarr;</div>
      <div class="fstage"><div class="fno">STAGE 02</div><h3>Registry, as data</h3>
        <p>Each known indicator carries its unit, cadence, promised disaggregations and disclosure
          tier in YAML — a file CI validates, not a paragraph in a guideline.</p></div>
      <div class="farrow" aria-hidden="true">&rarr;</div>
      <div class="fstage"><div class="fno">STAGE 03</div><h3>Match, then five checks</h3>
        <p>Token and phrase matching with a 0.45 floor; then availability, disaggregation, cadence,
          geography and baseline, and disclosure. A weak match is refused, never guessed.</p></div>
      <div class="farrow" aria-hidden="true">&rarr;</div>
      <div class="fstage"><div class="fno">STAGE 04</div><h3>Verdict, per line</h3>
        <p>Monitorable as written, reportable with one named caveat, or no data trail. The top
          cause is printed so the fix is obvious.</p></div>
    </div>
    <div class="fout">
      <div><b>This page</b><code>brief.html</code> — one file, no network, prints complete</div>
      <div><b>Scorecard</b><code>scorecard.csv</code> — one row per indicator, for a reviewer</div>
      <div><b>Reporting</b><code>powerbi/</code> — star schema and five DAX measures</div>
    </div>
    <p class="hint">The disclosure gate runs before any of the three is written: an internal source
      stays aggregate, and cell counts below five are generalised.</p>
  </section>

  <footer>
    <p><b>Provenance.</b> Population series: ISIMIP2a input dataset
      <code>population_histsoc_national_annual</code>, version 20210526, retrieved from
      data.isimip.org under CC BY 4.0; SHA-512 verified against the digest the portal publishes.
      Boundaries: Natural Earth 110m, public domain, reduced to 176 outer rings. Indicator
      registry: <code>config/registry/indicators.yml</code>, {len(assessments)} assessments this run.</p>
    <p><b>Limitations.</b> The audit tests whether data exists and is usable; it does not test
      whether an indicator measures what its result statement claims. Gridded hazard layers
      (flood, crop) are catalogued and licensed but need an administrative boundary raster
      before they become national indicators.</p>
    <p>Generated by aadesk · the example framework is illustrative and does not describe a real
      proposal.</p>
  </footer>
</div>
<div id="tip"></div>
<script>{JS}</script>
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
