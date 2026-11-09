# Data protection and disclosure control

> This documents the design rule the code implements. It is not legal advice,
> and it does not replace an organisation's own data-protection policy.

## The risk this addresses

Humanitarian programmes hold data about people in situations of acute
vulnerability — names, locations, household composition, sometimes
protection-related details. The realistic failure mode is not a breached
database. It is a table in a donor annex, built in good faith, that lists
"people reached" by village and date, and in which three of those rows are
single households. Combined with local knowledge, that is identifiable data
published to the internet.

## Tiers

| Tier | Meaning | Example |
|---|---|---|
| `public` | publishable as-is | national population denominators; published displacement statistics |
| `internal` | aggregate may be published after review; record level never | distribution lists, partner financial reporting, access incident logs |
| `restricted` | never published; internal use only | individual registration records, protection case files |

## Rules enforced by `aadesk.disclosure`

1. **Tier ceiling.** An output may not be published at a higher visibility than
   its most sensitive input. `internal` → `public` is permitted only as reviewed
   aggregates; `restricted` → `public` is refused.
2. **Explicit refusal.** `enforce()` returns the list of dropped columns
   alongside the filtered frame, so a pipeline can log what it removed. Silent
   filtering is how a field reappears later.
3. **Small-count suppression.** Counts below five are generalised to `<5`.
   Below that threshold a cell is a person.

## What this module does not do

- It does not detect re-identification through combination (two "public" tables
  joined on location and date). That requires a disclosure review, which is a
  human step.
- It does not encrypt, tokenise or audit-log access. Those belong to
  infrastructure, not to a reporting library.
- It does not decide lawful basis or retention. Consent, purpose limitation and
  retention periods sit with the data controller.

## Why it is in a reporting repository at all

Because the disclosure decision is currently made by whoever assembles the
annex, under deadline, from memory. Encoding it as a check that fails loudly
converts a judgement call into a rule that can be tested — and gives the
analyst something concrete to bring to the review.
