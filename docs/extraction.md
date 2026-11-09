# Extracting indicators from proposal text

`aadesk extract` reduces narrative proposal text to candidate indicator
statements so they can be checked against the registry. It is a rule-based
first pass and is honest about being one.

## What it does

- strips bullets and numbering, splits blocks into sentences;
- keeps statements of at least 40 characters that contain a measure verb
  (`reach`, `reduce`, `share`, `number`, `days`, `score`, …);
- tags a unit (`percent`, `count`, `days`, `tonnes`, `hectares`);
- tags disaggregation (`sex`, `age_group`, `disability`, `geography`);
- tags a reporting cadence (`monthly`, `quarterly`, `seasonal`, `annual`);
- resolves a country if one of the series' national units is named;
- emits a confidence score based on how many of those were found.

## What it misses, and why that is acceptable

Negation, conditionals, compound indicators ("percentage of households with
access to X *and* Y"), and indicators phrased around an organisation's internal
process rather than an outcome. Precision is roughly "good enough to shortlist
thirty lines out of four pages", which is the point: a human then reviews the
shortlist.

## Adding an LLM pass

The rule layer is deliberately offline by default. Proposals often contain
personal and protection-sensitive details, and sending them to a third-party
API is a data-protection decision, not an engineering convenience.

If an LLM pass is wanted, the contract that keeps it safe:

1. **Redact first.** Strip names, locations below national level, and
   identifying case details before any text leaves the machine.
2. **Ask for structure, not judgement.** The model returns candidate
   statements with unit, geography, disaggregation and cadence. It does not
   decide whether an indicator is monitorable — that stays with the checks
   in `rfcheck`, which are testable.
3. **Log the model, version and prompt** next to each extracted record, so
   a later reviewer can see what produced it.
4. **Keep a human in the loop** for anything that enters a signed framework.

The interface to write against is `extract.extract(text, countries)` returning
a frame with the same columns; swapping the implementation does not touch the
audit.
