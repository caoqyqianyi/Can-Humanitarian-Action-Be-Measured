# Star schema

- `fact_assessment` — one row per audited indicator (grain: indicator in framework)
- `fact_denominator` — population by country-year (grain: country, year)
- `dim_indicator` — registry attributes for matched indicators
- `dim_country` — country attributes and coverage

Join `fact_assessment.matched_id` → `dim_indicator.indicator_id`;
`fact_denominator.country` → `dim_country.country`.

## Opening it in Power BI Desktop

These are plain CSVs, not a `.pbix`. They are inert until imported —
the interactivity (slicers, cross-filtering, drill-down) is what Power BI
adds, not what is shipped here.

1. **Get data ▸ Text/CSV**, `fact_assessment.csv`. In the dialog set
   *File origin* to **65001: Unicode (UTF-8)** — the default locale mangles
   accented names — then **Load**. Repeat for the other three files.
2. **Model view**: drag `dim_indicator[indicator_id]` onto
   `fact_assessment[matched_id]`, and `dim_country[country]` onto
   `fact_denominator[country]`. Both should be many-to-one, single direction.
3. **Model view ▸ New measure**: paste the measures from `measures.dax`,
   one at a time.
4. A first page that answers the donor question: a **slicer** on
   `fact_assessment[status]`, a **card** with `[Monitorable share]`, a
   **matrix** of `status` against `geography`, and a **line chart** of
   `population` by `year` with `dim_country[country]` as legend.
5. **File ▸ Save as** `.pbix` if you want the report itself versioned.
