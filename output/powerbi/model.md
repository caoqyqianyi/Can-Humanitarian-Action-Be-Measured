# Star schema

- `fact_assessment` — one row per audited indicator (grain: indicator in framework)
- `fact_denominator` — population by country-year (grain: country, year)
- `dim_indicator` — registry attributes for matched indicators
- `dim_country` — country attributes and coverage

Join `fact_assessment.matched_id` → `dim_indicator.indicator_id`;
`fact_denominator.country` → `dim_country.country`.
