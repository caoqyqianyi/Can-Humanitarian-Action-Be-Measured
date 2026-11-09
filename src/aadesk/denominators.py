"""Population denominators from the ISIMIP / IIASA national population series.

The file shipped in data/reference/ is the ISIMIP2a input dataset
`population_histsoc_national_annual` (HYDE methodology), annual 1901–2020 in
thousands of persons, retrieved through aadesk.iiasa with SHA-512 verification.

Two things a denominator layer has to get right, and that proposal annexes
routinely get wrong:
  1. units — the source is in thousands, published indicators are in persons;
  2. vintage — a baseline fixed to 2015 is not comparable with a 2020 reference
     year without saying so out loud.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pandas as pd

from .config import POPULATION_REFERENCE

# The ISIMIP/HYDE national list abbreviates some names ("Syrian Arab Rep.",
# "Congo Dem. Rep."). Aliases map the spellings a proposal is likely to use
# onto the exact string in the series. Without this, fuzzy matching turns
# "Syrian Arab Republic" into "Serbia" — which is precisely the kind of silent
# mis-join that ruins a denominator.
ALIASES = {
    "syria": "Syrian Arab Rep.",
    "syrian arab republic": "Syrian Arab Rep.",
    "democratic republic of the congo": "Congo Dem. Rep.",
    "democratic republic of congo": "Congo Dem. Rep.",
    "dr congo": "Congo Dem. Rep.",
    "drc": "Congo Dem. Rep.",
    "congo dem rep": "Congo Dem. Rep.",
    "congo democratic republic": "Congo Dem. Rep.",
    "ivory coast": "Cote d'Ivoire",
    "cote d ivoire": "Cote d'Ivoire",
    "palestine": "Occupied Palestinian Terr.",
    "state of palestine": "Occupied Palestinian Terr.",
    "occupied palestinian territory": "Occupied Palestinian Terr.",
    "west bank and gaza": "Occupied Palestinian Terr.",
    "north macedonia": "TFYR Macedonia",
    "macedonia": "TFYR Macedonia",
    "burma": "Myanmar",
    "turkiye": "Turkey",
    "russian federation": "Russia",
    "united republic of tanzania": "U.R. Tanzania",
    "tanzania": "U.R. Tanzania",
    "vietnam": "Viet Nam",
    "iran": "Isl. Rep. of Iran",
    "islamic republic of iran": "Isl. Rep. of Iran",
    "lao pdr": "Laos",
    "laos": "Laos",
    "united states": "United States of America",
}


def _norm(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_population(path: Path | str | None = None) -> pd.DataFrame:
    """Return tidy long-format population data in persons.

    Columns: iso_code, country, year, population_thousands, population.
    """
    path = Path(path or POPULATION_REFERENCE)
    wide = pd.read_csv(path, comment="#")
    wide.columns = [str(c).strip() for c in wide.columns]
    wide = wide.rename(columns={wide.columns[0]: "iso_code", wide.columns[1]: "country"})
    year_columns = [c for c in wide.columns if re.fullmatch(r"\d{4}", str(c))]
    long = wide.melt(id_vars=["iso_code", "country"], value_vars=year_columns,
                     var_name="year", value_name="population_thousands")
    long["year"] = long["year"].astype(int)
    long["population_thousands"] = pd.to_numeric(long["population_thousands"],
                                                 errors="coerce")
    long = long.dropna(subset=["population_thousands"])
    long["population"] = long["population_thousands"] * 1000.0
    long["country"] = long["country"].astype(str).str.strip()
    return long.sort_values(["country", "year"]).reset_index(drop=True)


class Denominators:
    """Queryable view over the national population series."""

    def __init__(self, frame: pd.DataFrame | None = None):
        self.frame = frame if frame is not None else load_population()
        self._names = sorted(self.frame["country"].unique())

    # ------------------------------------------------------------------ lookup
    @property
    def countries(self) -> list[str]:
        return list(self._names)

    @property
    def year_range(self) -> tuple[int, int]:
        return int(self.frame["year"].min()), int(self.frame["year"].max())

    def resolve(self, name: str) -> tuple[str | None, float]:
        """Fuzzy-resolve a country name to a row in the series."""
        if not name:
            return None, 0.0
        key = _norm(name)
        key = _norm(ALIASES.get(key, key))
        lookup = {_norm(c): c for c in self._names}
        if key in lookup:
            return lookup[key], 1.0
        # Fallback stays conservative: a 0.85 cutoff keeps "Syrian Arab Republic"
        # away from "Serbia". Anything weaker must be fixed with an alias.
        close = difflib.get_close_matches(key, list(lookup), n=1, cutoff=0.85)
        if close:
            return lookup[close[0]], round(difflib.SequenceMatcher(
                a=key, b=close[0]).ratio(), 3)
        return None, 0.0

    def value(self, name: str, year: int) -> float | None:
        country, _ = self.resolve(name)
        if country is None:
            return None
        rows = self.frame[(self.frame["country"] == country) &
                          (self.frame["year"] == int(year))]
        if rows.empty:
            return None
        return float(rows["population"].iloc[0])

    def series(self, name: str, start: int | None = None, end: int | None = None):
        country, _ = self.resolve(name)
        if country is None:
            return pd.DataFrame(columns=["year", "population"])
        rows = self.frame[self.frame["country"] == country]
        if start is not None:
            rows = rows[rows["year"] >= start]
        if end is not None:
            rows = rows[rows["year"] <= end]
        return rows[["year", "population"]].reset_index(drop=True)

    def covers(self, name: str, year: int) -> bool:
        return self.value(name, year) is not None

    # ------------------------------------------------------------------ analysis
    def drift(self, countries: list[str], baseline_year: int,
              reference_year: int) -> pd.DataFrame:
        """Change in the denominator between a baseline and a reference year.

        A 6 % population increase between baseline and reporting year is
        routinely enough to move a "share of population reached" indicator by
        more than the change the programme is trying to achieve.
        """
        rows = []
        for name in countries:
            resolved, score = self.resolve(name)
            base = self.value(name, baseline_year)
            ref = self.value(name, reference_year)
            rows.append({
                "country_input": name,
                "country_matched": resolved,
                "match_score": score,
                f"population_{baseline_year}": base,
                f"population_{reference_year}": ref,
                "change_persons": (ref - base) if (base and ref) else None,
                "change_pct": ((ref / base - 1) * 100) if (base and ref) else None,
            })
        return pd.DataFrame(rows)

    def summary(self) -> dict:
        first, last = self.year_range
        latest = self.frame[self.frame["year"] == last]
        return {
            "countries": len(self._names),
            "first_year": first,
            "last_year": last,
            "population_latest_billion": round(latest["population"].sum() / 1e9, 2),
            "source": "ISIMIP2a / HYDE national population (hosted by IIASA)",
        }


def format_persons(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "–"
    for scale, suffix in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(value) >= scale:
            return f"{value/scale:.{decimals}f} {suffix}"
    return f"{value:,.0f}"
