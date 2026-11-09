# Methodology

The audit answers a narrow question well: **if this indicator is written into a
results framework, will the data behind it exist at the geography, cadence and
disaggregation that the framework promises?** It does not attempt to judge
whether the indicator measures the right thing — that is a technical review
question, not a data-availability question, and conflating the two is how
unmonitorable frameworks get signed off.

## How an indicator is matched

Each framework line is normalised (lowercased, punctuation stripped) and scored
against every registry entry:

| Component | Weight | Why |
|---|---|---|
| Token Jaccard overlap with name + keywords | 1.5 × overlap | Cheap, language-tolerant, works across paraphrases |
| Verbatim multi-word keyword phrase | +0.30 | A registry phrase appearing as-is is strong evidence |
| Whole-name string similarity | +0.25 × ratio | Catches near-verbatim rewording |

Best score ≥ 0.45 is accepted. Below that the indicator is reported as
`unmatched` rather than forced onto the closest entry — a wrong match is worse
than no match, because it produces a confident answer about the wrong source.

## The five checks

1. **availability** — is there a documented source with a named custodian?
   `available` passes; `partial` warns ("exists but needs preparation");
   `unavailable` fails.
2. **disaggregation** — the framework's promised splits (sex, age, disability,
   geography, …) against what the source can actually produce. Asking a
   national aggregate for sex-disaggregation is the single most common
   unmonitorable promise.
3. **cadence** — the reporting frequency demanded against the source's
   collection rhythm. Monthly reporting on an annual survey does not
   interpolate into monthly data; it carries values forward and calls them
   measurements.
4. **geography / baseline** — resolved against the population series: does the
   named country exist in the series, and does the baseline year fall inside
   its coverage? A baseline outside coverage fails outright.
5. **disclosure** — the highest visibility an output derived from that source
   may carry (see `docs/data-protection.md`).

A failure on any check makes the indicator **not monitorable**. A warning makes
it **conditional**: reportable, but only with the caveat written down next to
the number. Everything that passes is **monitorable**.

## Why the checks are separated

A framework can be unmonitorable for five different reasons that need five
different fixes: buy a survey round (cadence), change the collection
instrument (disaggregation), write a data-sharing agreement (availability),
move the baseline (geography), or accept an internal-only product (disclosure).
Collapsing these into a single "data availability" verdict loses the remedial
action, which is the only part a programme team can act on.

## Extending the registry

Add an entry to `config/registry/indicators.yml` and its source to
`config/sources.yml`. `aadesk validate` enforces the required fields, unique
ids, and that every declared source exists. The registry is deliberately
curated rather than scraped: a scraper would produce a larger registry and a
worse one.
