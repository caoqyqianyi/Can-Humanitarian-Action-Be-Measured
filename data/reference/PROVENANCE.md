# Data provenance

## Shipped extract

`data/reference/isimip_hyde_national_population_1901_2020.csv`

| Field | Value |
|---|---|
| Dataset | `population_histsoc_national_annual` |
| Dataset id | `018a89a5-80b7-42ff-b05a-396d81d47b4d` |
| Version | `20210526` |
| Portal | https://data.isimip.org |
| Path | `ISIMIP2a/InputData/landuse_humaninfluences/population/HYDE/` |
| File | `population_histsoc_national_annual_1901_2020.csv` |
| Bytes | 338,985 |
| SHA-512 | `4a1e9137811810e0dd19dba6592c4fa9e4106fb3debfca50201894302b6097f038b497beb0f9c7aac4c09ee32943b51228d115544b2110f6ad4b20dcdde5a4c3` |
| Rights | CC BY 4.0 — Attribution 4.0 International (as returned by the portal at retrieval, 2026-11-09) |

Units: **thousands of persons**, annual columns 1901–2020, keyed by numeric
ISO code and country name. `aadesk.denominators` converts to persons and
keeps the raw column so the conversion stays auditable.

Verify locally:

```bash
shasum -a 512 data/reference/isimip_hyde_national_population_1901_2020.csv
```

Re-retrieve with verification:

```bash
aadesk fetch --name population_histsoc_national_annual
```

`aadesk fetch` writes a `.provenance.json` beside every downloaded file
containing the retrieval time, dataset id, version, licence, specifiers and
digest — so a later reader does not have to trust a commit message.

## Catalogue notes

The ISIMIP portal lists 1,001 public datasets at the time of writing, across
simulation rounds ISIMIP2a/2b/3b, covering water, biosphere, agriculture,
health, energy, infrastructure and population inputs. The flood and crop
layers referenced in the registry were checked against the same API; their
catalogue entries are real, their use as national indicators is not yet
implemented (see `docs/limitations.md`).

## Boundary geometry

`data/reference/ne_110m_admin0_world.json`

| Field | Value |
|---|---|
| Source | Natural Earth 110m Cultural Vectors, admin-0 countries |
| Upstream | `nvkelso/natural-earth-vector`, `geojson/ne_110m_admin0_countries.geojson` |
| Rights | Public domain — no attribution required |
| Derived | outer rings only, vertices rounded to 0.1°, Antarctica and everything north of 84°N omitted |
| Features | 176 |
| Built | 2026-11-09 |

The map needs coastlines at render time, and the brief must draw with no
network. The file is therefore derived once and shipped: 176 features, outer
rings only (lakes are filled, which is wrong for a physical map and irrelevant
for a choropleth of national totals). Rounding to 0.1° is about 0.3 px at
1000 px width, so the simplification is invisible at the size the brief
prints.

This is cartographic geometry, not an authoritative boundary representation.
Disputed and de facto boundaries follow Natural Earth's own depiction. Before
any map of this kind is published externally by an agency, it must be
redrawn on that agency's official boundary layer — see `docs/limitations.md`.
