"""Command line entry point.

    aadesk validate                                  check the registry
    aadesk audit LOGFRAME.csv --outdir output        full audit + brief + Power BI model
    aadesk denominators --country Somalia --year 2020
    aadesk fetch --name population_histsoc_national_annual
    aadesk extract proposal.docx.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import __version__, config
from .denominators import Denominators, format_persons
from .disclosure import gate
from .extract import extract
from .iiasa import ISIMIPClient
from .registry import load_registry
from .report import build_brief, export_powerbi
from .rfcheck import audit_logframe, summarise, to_frame, to_records

WIDTH = 78
STATUS_ORDER = ["monitorable", "conditional", "not monitorable", "unmatched"]


def _line(char: str = "─") -> str:
    return char * WIDTH


def cmd_validate(args: argparse.Namespace) -> int:
    indicators = load_registry(args.registry)
    print(_line())
    print(f"REGISTRY  {len(indicators)} indicators · validated")
    print(_line())
    for indicator in indicators:
        print(f"  {indicator.id:<16} {indicator.availability:<12} "
              f"{indicator.disclosure:<11} {indicator.name[:38]}")
    counts: dict[str, int] = {}
    for indicator in indicators:
        counts[indicator.availability] = counts.get(indicator.availability, 0) + 1
    print(_line())
    print("  availability: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    open_share = counts.get("available", 0) / len(indicators)
    print(f"  open and ready to use: {open_share:.0%} of the registry")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    indicators = load_registry(args.registry)
    denominators = Denominators()
    frame = pd.read_csv(args.logframe, comment="#")
    frame.columns = [c.strip() for c in frame.columns]

    assessments = audit_logframe(frame, indicators, denominators)
    summary = summarise(assessments)

    outdir = config.ensure_dir(args.outdir)
    scorecard = outdir / "scorecard.csv"
    to_frame(assessments).to_csv(scorecard, index=False)

    records = to_records(assessments)
    (outdir / "assessments.json").write_text(
        json.dumps({"summary": summary, "assessments": records}, indent=2),
        encoding="utf-8")

    countries = sorted({str(a.geography) for a in assessments if a.geography})
    baseline = next((a.baseline_year for a in assessments if a.baseline_year), None)
    reference = denominators.year_range[1]

    brief = build_brief(assessments, denominators, countries,
                        outdir / "brief.html",
                        title=args.title, publication=args.publication,
                        summary=summary, baseline_year=baseline,
                        reference_year=reference)
    powerbi = export_powerbi(assessments, denominators, countries, outdir / "powerbi")

    print(_line("═"))
    print(f"AUDIT  {args.title}")
    print(f"       {args.logframe}  →  {outdir}")
    print(_line("═"))
    print(f"  {summary['total']} indicators · {summary['monitorable']} monitorable · "
          f"{summary['conditional']} conditional · "
          f"{summary['not_monitorable'] + summary['unmatched']} with no data trail")
    print(_line())
    print(f"  {'STATUS':<18}{'REGISTRY':<20}INDICATOR")
    print(_line())
    for assessment in sorted(assessments, key=lambda a: STATUS_ORDER.index(a.status)
                             if a.status in STATUS_ORDER else 9):
        text = assessment.indicator_text
        if len(text) > 48:
            text = text[:45] + "…"
        print(f"  {assessment.status:<18}{(assessment.matched_id or '—'):<20}{text}")
    print(_line())
    for assessment in assessments:
        if assessment.status in {"not monitorable", "unmatched"}:
            print(f"  ! {assessment.indicator_text[:60]}")
            for check in assessment.checks:
                if check.status == "fail":
                    print(f"      {check.name}: {check.detail}")
    print(_line())
    print("  disclosure gate")
    for assessment in assessments:
        check = next((c for c in assessment.checks if c.name == "disclosure"), None)
        if check and check.status != "pass":
            print(f"    {assessment.matched_id:<16}{check.status.upper():<7}{check.detail[:48]}")
    print(_line())
    print(f"  scorecard     {scorecard}")
    print(f"  records       {outdir / 'assessments.json'}")
    print(f"  brief         {brief}")
    print(f"  power bi      {len(powerbi)} files in {outdir / 'powerbi'}")
    print(_line())
    return 0


def cmd_denominators(args: argparse.Namespace) -> int:
    denominators = Denominators()
    print(_line())
    print(f"DENOMINATORS  {denominators.summary()['countries']} national units · "
          f"{denominators.year_range[0]}–{denominators.year_range[1]}")
    print(_line())
    for country in args.country:
        resolved, score = denominators.resolve(country)
        if resolved is None:
            print(f"  {country:<24} not found in the series (match {score:.2f})")
            continue
        value = denominators.value(resolved, args.year)
        print(f"  {country:<24} {resolved:<24} {args.year}: "
              f"{format_persons(value)} people  (match {score:.2f})")
    if args.drift:
        drift = denominators.drift(args.country, args.baseline, args.year)
        print(_line())
        for row in drift.itertuples():
            change = getattr(row, "change_pct", None)
            label = "n/a" if change is None else f"{change:+.1f}%"
            print(f"  {str(row.country_matched):<24} {args.baseline}→{args.year}  {label}")
    print(_line())
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    client = ISIMIPClient(cache_dir=args.outdir)
    dataset = client.first(name=args.name)
    print(_line())
    print(f"DATASET  {dataset.name}")
    print(f"  id        {dataset.id}")
    print(f"  version   {dataset.version}")
    print(f"  licence   {dataset.licence_short} — {dataset.licence}")
    print(f"  files     {len(dataset.files)}")
    print(_line())
    for dataset_file in dataset.files:
        path = client.download(dataset, dataset_file, verify=not args.no_verify)
        print(f"  ok  {path.name}  ({path.stat().st_size/1024:.0f} kB)  sha512 verified")
    print(_line())
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    text = Path(args.text).read_text(encoding="utf-8")
    denominators = Denominators()
    frame = extract(text, countries=denominators.countries)
    outdir = config.ensure_dir(args.outdir)
    target = outdir / "candidates.csv"
    frame.to_csv(target, index=False)
    print(_line())
    print(f"EXTRACT  {len(frame)} candidate statements → {target}")
    print(_line())
    for row in frame.itertuples():
        print(f"  [{row.confidence:.2f}] {row.indicator_text[:62]}")
        print(f"         unit={row.unit} · geography={row.geography or '—'} · "
              f"cadence={row.frequency}")
    print(_line())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aadesk", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"aadesk {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate the indicator registry")
    validate.add_argument("--registry", default=None)
    validate.set_defaults(func=cmd_validate)

    audit = sub.add_parser("audit", help="audit a results framework")
    audit.add_argument("logframe")
    audit.add_argument("--outdir", default=str(config.OUTPUT_DIR))
    audit.add_argument("--registry", default=None)
    audit.add_argument("--title", default="Results framework monitorability")
    audit.add_argument("--publication", default="public",
                       choices=["public", "internal", "restricted"])
    audit.set_defaults(func=cmd_audit)

    denom = sub.add_parser("denominators", help="query population denominators")
    denom.add_argument("--country", nargs="+", required=True)
    denom.add_argument("--year", type=int, default=2020)
    denom.add_argument("--drift", action="store_true", help="also show change since --baseline")
    denom.add_argument("--baseline", type=int, default=2015)
    denom.set_defaults(func=cmd_denominators)

    fetch = sub.add_parser("fetch", help="download a dataset from the ISIMIP portal")
    fetch.add_argument("--name", default="population_histsoc_national_annual")
    fetch.add_argument("--outdir", default=str(config.CACHE_DIR))
    fetch.add_argument("--no-verify", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    extraction = sub.add_parser("extract", help="pull candidate indicators from text")
    extraction.add_argument("text")
    extraction.add_argument("--outdir", default=str(config.OUTPUT_DIR))
    extraction.set_defaults(func=cmd_extract)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
