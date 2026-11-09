"""Loading and validating the indicator registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import REGISTRY_FILE, SOURCES_FILE, load_yaml

REQUIRED_INDICATOR_FIELDS = (
    "id", "name", "definition", "unit", "geography", "frequency",
    "disaggregation", "baseline", "availability", "source", "disclosure",
    "keywords",
)
VALID_AVAILABILITY = {"available", "partial", "unavailable"}
VALID_DISCLOSURE = {"public", "internal", "restricted"}


class RegistryError(ValueError):
    """Raised when the registry is structurally invalid."""


@dataclass
class Indicator:
    id: str
    name: str
    definition: str
    unit: str
    geography: str
    frequency: str
    disaggregation: list[str]
    baseline: str
    availability: str
    disclosure: str
    keywords: list[str]
    source_id: str
    source_title: str = ""
    source_custodian: str = ""
    source_url: str = ""
    source_access: str = ""
    source_licence: str = ""
    note: str = ""
    computed_by: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def searchable_text(self) -> str:
        return " ".join([self.name, *self.keywords])

    @property
    def has_open_source(self) -> bool:
        return self.availability == "available" and self.source_access in {"open", "mixed"}


def load_registry(path: Path | str | None = None,
                  sources_path: Path | str | None = None) -> list[Indicator]:
    path = Path(path or REGISTRY_FILE)
    sources = load_yaml(sources_path or SOURCES_FILE).get("sources", {})
    payload = load_yaml(path)
    raw_indicators = payload.get("indicators", [])

    errors: list[str] = []
    seen: set[str] = set()
    indicators: list[Indicator] = []

    for index, raw in enumerate(raw_indicators):
        label = raw.get("id") or f"#{index}"
        for key in REQUIRED_INDICATOR_FIELDS:
            if key not in raw:
                errors.append(f"{label}: missing required field '{key}'")
        if raw.get("id") in seen:
            errors.append(f"{label}: duplicate id")
        seen.add(raw.get("id"))

        if raw.get("availability") not in VALID_AVAILABILITY:
            errors.append(f"{label}: availability must be one of {VALID_AVAILABILITY}")
        if raw.get("disclosure") not in VALID_DISCLOSURE:
            errors.append(f"{label}: disclosure must be one of {VALID_DISCLOSURE}")

        source = raw.get("source") or {}
        source_id = source.get("id", "")
        source_meta = sources.get(source_id, {}) if source_id else {}
        if source_id and source_id != "none" and source_id not in sources:
            errors.append(f"{label}: source '{source_id}' not declared in sources.yml")

        indicators.append(Indicator(
            id=raw.get("id", ""),
            name=raw.get("name", ""),
            definition=(raw.get("definition") or "").strip(),
            unit=raw.get("unit", ""),
            geography=raw.get("geography", ""),
            frequency=raw.get("frequency", ""),
            disaggregation=list(raw.get("disaggregation") or []),
            baseline=raw.get("baseline", ""),
            availability=raw.get("availability", ""),
            disclosure=raw.get("disclosure", ""),
            keywords=list(raw.get("keywords") or []),
            source_id=source_id,
            source_title=source.get("title") or source_meta.get("title", ""),
            source_custodian=source.get("custodian") or source_meta.get("custodian", ""),
            source_url=source.get("url") or source_meta.get("url", ""),
            source_access=source.get("access") or source_meta.get("access", ""),
            source_licence=source.get("licence") or source_meta.get("licence", ""),
            note=(raw.get("note") or "").strip(),
            computed_by=raw.get("computed_by", ""),
            raw=raw,
        ))

    if errors:
        raise RegistryError("Registry validation failed:\n  - " + "\n  - ".join(errors))
    return indicators


def by_id(indicators: list[Indicator]) -> dict[str, Indicator]:
    return {indicator.id: indicator for indicator in indicators}
