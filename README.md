# aadesk — the anticipatory action data desk

**Check whether a humanitarian results framework can actually be measured — before it is signed — then build the brief from evidence that is licensed, checksum-verified and disclosure-safe.**

![tests](https://img.shields.io/badge/tests-36%20passed-0f6b5c)
![python](https://img.shields.io/badge/python-3.10%2B-14211d)
![licence](https://img.shields.io/badge/code-MIT-14211d)
![data](https://img.shields.io/badge/data-ISIMIP%20%2F%20IIASA-a85e29)

<img src="assets/brief-header.png" alt="The generated brief: Somalia–Yemen multi-country results framework, 13 indicators audited, 1 monitorable, 9 conditional, 3 with no data trail, plus a breakdown of where the caveats come from" width="940">

<sub>The brief the tool actually emits for the example framework — one page, printable, no network required. Screenshot of `output/brief.html`, not a mock-up.</sub>

---

## The problem this is built around

Humanitarian results frameworks are written under deadline, by people who know
the context and not always the data landscape. An indicator like *"share of
targeted households with adequate food consumption, disaggregated by sex, reported
quarterly"* reads as reasonable. It is also three promises that the source cannot
keep: the food-consumption survey runs in rounds, not quarters; the sample is
not powered for sex-disaggregation at district level; and the baseline year
predates the current assessment series.

The cost is not abstract. It surfaces in month 18, as a column of values
carried forward from the last survey round, reported to a donor as if it were
measurement — or as an indicator quietly dropped and never mentioned again.

`aadesk` does three things about this:

1. **Audits the framework** against a curated indicator registry, line by line,
   and says which indicators are monitorable, which are conditional and which
   have no data trail at all — before signature.
2. **Builds the denominator** from open data, so "share of population" indicators
   have an honest base — retrieved from the ISIMIP portal hosted by IIASA,
   with the published SHA-512 checked on every download.
3. **Gates the output**, because the data behind half of these indicators is
   internal: aggregate figures can be published after review, record-level
   data cannot, and small cell counts are generalised.

---

## How it works

<img src="assets/pipeline.png" alt="Pipeline: evidence sources with custodian and licence, a 12-indicator registry, a matcher and five checks, then a per-line verdict; below, the three outputs and the disclosure gate" width="1000">

<sub>Evidence is declared before it is matched, and every output passes the gate on its way out — not afterwards.</sub>

The registry is the only place a claim about data is written down, and it is data,
not prose: each indicator carries its unit, cadence, promised disaggregation, custodian
and disclosure tier. That is what makes the audit mechanical enough to run in CI
against every new framework.

---

## What it looks like

```console
$ aadesk validate
REGISTRY  12 indicators · validated
  POP-DENOM        available    public      National population denominator
  HAZ-FLOOD-EXPO   partial      public      Population in areas exposed to 1-in-100…
  FS-FCS           partial      public      Share of households with adequate food…
  …
  IM-DISABILITY    unavailable  internal    Share of assisted people with disability…
  GEN-DECISION     unavailable  internal    Share of women in partner decision-making…
  availability: available 1, partial 9, unavailable 2
```

```console
$ aadesk audit data/examples/logframe_example.csv --outdir output
══════════════════════════════════════════════════════════════════════════════
AUDIT  Somalia–Yemen multi-country results framework
══════════════════════════════════════════════════════════════════════════════
  13 indicators · 1 monitorable · 9 conditional · 3 with no data trail
──────────────────────────────────────────────────────────────────────────────
  STATUS            REGISTRY            INDICATOR
  monitorable       POP-DENOM           Total population in target districts by year
  conditional       FS-FCS              Share of targeted households with adequate fo…
  conditional       HAZ-FLOOD-EXPO      Number of people living in areas exposed to 1…
  conditional       PROT-DISPLACED      Number of people displaced by conflict in the…
  not monitorable   IM-DISABILITY       Number of beneficiaries with disability statu…
  unmatched         —                   Number of community feedback mechanisms estab…
──────────────────────────────────────────────────────────────────────────────
  disclosure gate
    FS-CASH-REACH   WARN   source is 'internal'; only reviewed aggregate figures may be published
```

The run writes four things: `scorecard.csv`, `assessments.json`,
`brief.html` (a standalone brief with inline SVG charts and maps, no external
assets) and a Power BI star schema in `output/powerbi/`.

The brief is the deliverable most people actually want: one page, printable, no
network required. It is also interactive without a CDN, a build step or a
tile server — the status chips filter the indicator table, hovering a country
gives its growth and its 2020 population, and clicking a series in the legend
hides it. The filters exist only on screen: print rules expand every row and
drop the chips, so the version that reaches a printer or a PDF is the complete
one, and the two can never disagree about a number.

---

## What the audit checks

| Check | Question | Typical failure it catches |
|---|---|---|
| **availability** | Is there a documented source with a named custodian? | "We will report on community feedback mechanisms" — no registry, no system, no data |
| **disaggregation** | Can the source produce the promised splits? | Sex-disaggregation promised from a national aggregate |
| **cadence** | Does collection rhythm support the reporting frequency? | Monthly GAM prevalence from an annual SMART survey |
| **geography / baseline** | Does the named country exist in the series, and is the baseline year inside its coverage? | Baseline 2015 against a series that stops in 2020 |
| **disclosure** | What is the highest visibility an output from this source may carry? | Beneficiary counts from a programme MIS published as a public annex |

A fail makes the indicator **not monitorable**. A warning makes it
**conditional** — reportable, but only with the caveat written next to the number.
Matching is deliberately conservative: below a 0.45 score the line is reported as
**unmatched** rather than forced onto the nearest entry, because a confident answer
about the wrong source is worse than an honest gap.

<img src="assets/brief-table.png" alt="Indicator-by-indicator table: each line carries a status pill (monitorable, conditional) and the specific caveat that stands in the way" width="940">

<sub>One line per indicator. The pill is the verdict; the column beside it names the exact constraint, so it can be fixed rather than argued about.</sub>

Full method, thresholds and known weaknesses: [`docs/methodology.md`](docs/methodology.md).

---

## The IIASA / ISIMIP layer

The population denominators come from the **ISIMIP data portal hosted by IIASA**
(`population_histsoc_national_annual`, version `20210526`, HYDE methodology,
**CC BY 4.0**).

`aadesk.iiasa` is a real client against the portal's REST API
(`https://data.isimip.org/api/v1/`, 1,001 public datasets):

- resolves a dataset by specifiers rather than by guesswork;
- downloads with **SHA-512 verification** against the digest the portal publishes,
  and refuses the file on mismatch;
- writes a `.provenance.json` beside every download recording retrieval time,
  dataset id, version, licence and specifiers — so a later reader does not have
  to trust a commit message;
- captures the licence at retrieval time rather than assuming it.

```console
$ aadesk fetch --name population_histsoc_national_annual
DATASET  population_histsoc_national_annual
  version   20210526
  licence   CC BY 4.0 — Attribution 4.0 International
  ok  population_histsoc_national_annual_1901_2020.csv  (331 kB)  sha512 verified
```

The shipped extract covers **238 national units, 1901–2020, annual**, in thousands
of persons, converted to persons with the raw column kept so the unit conversion
stays auditable. Full digest and retrieval record:
[`data/reference/PROVENANCE.md`](data/reference/PROVENANCE.md).

<img src="assets/brief-map.png" alt="World choropleth of population growth from 1960 to 2020, with the five countries this framework names numbered: Bangladesh +252%, Chad +443%, Ethiopia +409%, Somalia +484%, Yemen +485%" width="940">

<sub>172 of the 176 countries drawn carry a row in the series. Grey means the series has no row — not zero, and not a number the code invented to fill the map. Boundaries are Natural Earth 110m, not an authoritative depiction: see <a href="docs/limitations.md">limitations</a>.</sub>

<img src="assets/brief-chart.png" alt="Indexed national population, 1960 = 100, to 2020 for Bangladesh, Chad, Ethiopia, Somalia and Yemen" width="940">

<sub>Indexing to 1960 puts a 170-million population and a 16-million one on the same axis. Somalia's late-1980s step is visible without needing a caption; the exact figures sit in the baseline table further down the brief.</sub>

**What is catalogued but not yet computed.** The registry also references the
ISIMIP CaMa-Flood 100-year flood-depth layer and the gridded crop-model output.
Both are open and verified in the catalogue; neither is yet a national indicator
here, because that needs an administrative boundary raster, per-cell population
weighting and an explicit exposure threshold. They are recorded as `partial` and
audited as **conditional**, rather than presented as numbers the pipeline has not
earned. That join is the obvious next piece of work — see
[`docs/limitations.md`](docs/limitations.md).

---

## What the example run found

The framework in `data/examples/logframe_example.csv` is **synthetic** — written
to exercise every failure mode, not to describe a real proposal. Across its
13 lines:

- **1** is backed by data available as-is (the population denominator);
- **9** are conditional, and the binding constraint is not missing hazard data
  but *state of preparation*: sources that exist and are licensed still need a
  boundary join, a survey round, or a partner agreement;
- **3** have no data trail. Two are real indicators with no monitorable source
  (disability status, women in partner decision-making); one — community feedback
  mechanisms — has no registry equivalent at all.

Two findings are the kind a proposal team can act on before signature:

- a **monthly** malnutrition prevalence indicator against an annual survey
  (the values would be carried forward, not measured);
- a **quarterly** displacement indicator against annual IDMC publication with
  a publication lag, where stock and flow are also being conflated.

---

## Repository map

```
aadesk/
├── config/
│   ├── registry/indicators.yml     curated registry: definition, source, cadence, disclosure
│   └── sources.yml                 custodians, access conditions, licences
├── data/
│   ├── reference/                  ISIMIP population extract + SHA-512 provenance,
│   │                               Natural Earth 110m boundaries for the map
│   ├── examples/                   synthetic framework used by the demo
│   └── cache/                      downloads (gitignored)
├── src/aadesk/
│   ├── iiasa.py                    ISIMIP portal client: resolve, verify, record provenance
│   ├── denominators.py             units, aliases, coverage, baseline drift
│   ├── registry.py                 schema + validation
│   ├── rfcheck.py                  matching and the five checks
│   ├── disclosure.py               tiering, small-count suppression
│   ├── report.py                   standalone HTML brief, Power BI star schema
│   ├── mapview.py                  inline-SVG world choropleth, no tiles, no JS library
│   ├── extract.py                  rule-based indicator extraction from proposal text
│   └── cli.py
├── docs/                           methodology · data protection · extraction · limitations
├── assets/                         figures in this README (re-renderable sources in assets/src/)
├── tests/                          36 tests, including regression cases
└── output/                         example run: scorecard, brief, Power BI model
```

---

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

aadesk validate
aadesk audit data/examples/logframe_example.csv --outdir output
aadesk denominators --country Somalia --country Yemen --year 2020 --drift --baseline 2015
aadesk fetch          # live download from the ISIMIP portal, checksum verified
aadesk extract proposal.txt
pytest
```

Dependencies are `pandas` and `PyYAML` only. The brief renders with no plotting
library and no external assets.

`make test`, `make audit` and `make brief` do the same three steps; `make pages`
regenerates the brief into `docs/index.html` so GitHub Pages can serve it.

---

## Publishing the brief

The brief is a single self-contained HTML file, so it can be published as-is.

```bash
gh repo create aa-data-desk --public --source=. --push
```

Without the GitHub CLI:

```bash
git remote add origin git@github.com:<your-handle>/aa-data-desk.git
git push -u origin main
```

Then **Settings → Pages → Build and deployment → Deploy from a branch**, branch
`main`, folder `/docs`. The example run is then readable at
`https://<your-handle>.github.io/aa-data-desk/` without anyone cloning the repo.

Replace `qianyi` in `CITATION.cff`, `pyproject.toml` and the link at the bottom of
this file if your handle differs.

---

## The Power BI export

`output/powerbi/` holds four CSVs — two dimensions, two fact tables — plus
`measures.dax` and `model.md`. It is a **model, not a `.pbix`**: a workbook with
your slicer layout in it would be someone else's design, and a binary in git
would be unreadable and unmergeable. The interactivity comes from Power BI
itself once the model is imported, which takes about two minutes:

1. **Get data → Text/CSV**, one file at a time. On the import dialog set *File
   origin* to `65001: Unicode (UTF-8)` — the country names are UTF-8, and a
   wrong origin turns `Côte d'Ivoire` into noise.
2. **Model view**: drag `dim_indicator[indicator_id]` onto
   `fact_assessment[matched_id]`, and `dim_country[country]` onto
   `fact_denominator[country]`. Both are many-to-one, single direction.
3. **Paste the measures** from `measures.dax` — five of them: indicators audited,
   monitorable count, monitorable share, latest population, growth since 1960.
4. A defensible first screen: a status slicer, a *Monitorable share* card, a
   status × geography matrix, and population by year as a line.

Step-by-step, with the field list and the reason for each relationship, is in
[`output/powerbi/model.md`](output/powerbi/model.md).

---

## Design decisions worth defending

- **Unmatched over best-guess.** A forced match produces a confident answer about
  the wrong source. The 0.45 threshold and the `unmatched` status exist so the
  tool can say "I don't know".
- **Checksums, not trust.** A digest recorded at download time is the difference
  between "we used the 2021 series" and "we believe we used the 2021 series".
- **No silent filtering.** `disclosure.enforce()` returns what it dropped. A
  filter that quietly removes a field is how that field reappears two reports
  later.
- **Offline by default.** `extract` is rule-based; the LLM path is documented
  but off, because proposal text often contains protection-sensitive detail and
  sending it to a third-party API is a data-protection decision, not a
  convenience. [`docs/extraction.md`](docs/extraction.md)
- **The audit does not judge indicator quality.** It tests whether data exists
  at the promised geography, cadence and disaggregation. Whether an indicator
  measures what its result statement claims is a technical review question that
  five availability checks cannot substitute for.

---

## Licence

Code: MIT. Data: the shipped extract is the ISIMIP/HYDE national population
series served by the ISIMIP portal hosted by IIASA, **CC BY 4.0** — attribution
required, and dataset rights should be re-checked at the portal before reuse.
See [`LICENSE`](LICENSE) and [`data/reference/PROVENANCE.md`](data/reference/PROVENANCE.md).

Built by [Qianyi Cao](https://github.com/qianyi) — data scientist working on
geospatial and climate data for humanitarian and development contexts.
