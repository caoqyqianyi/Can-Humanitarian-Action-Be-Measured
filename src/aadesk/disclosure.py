"""Disclosure control for outputs built on programme and partner data.

The practical risk is rarely a breached database — it is an aggregate table in a
donor report that, combined with a location and a date, identifies a handful of
people. This module makes that decision explicit and repeatable instead of
leaving it to whoever assembles the annex.

Rules implemented:
  * tiering — an output may not be published at a higher visibility than its
    most sensitive input; internal sources need a review step before publication;
  * small-count suppression — counts below a threshold are generalised.
"""

from __future__ import annotations

from dataclasses import dataclass

LEVELS = {"public": 0, "internal": 1, "restricted": 2}
SMALL_COUNT_THRESHOLD = 5


@dataclass
class Decision:
    subject: str
    classification: str
    publication: str
    outcome: str  # clear | review | blocked
    reason: str

    @property
    def allowed(self) -> bool:
        return self.outcome in {"clear", "review"}


def gate(subject: str, classification: str, publication: str) -> Decision:
    level = LEVELS.get(str(classification).lower(), 2)
    target = LEVELS.get(str(publication).lower(), 0)

    if target >= level:
        return Decision(subject, classification, publication, "clear",
                        f"a '{classification}' source may appear in a "
                        f"'{publication}' product")
    if publication.lower() == "public" and level == LEVELS["internal"]:
        return Decision(subject, classification, publication, "review",
                        "aggregate figures only; requires a disclosure review "
                        "before publication")
    return Decision(subject, classification, publication, "blocked",
                    f"a '{classification}' source may not appear in a "
                    f"'{publication}' product, even aggregated")


def suppress_small_counts(value, threshold: int = SMALL_COUNT_THRESHOLD):
    """Generalise small cell counts.

    Three people reached in a named village on a named date is identifiable;
    three thousand is not.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if 0 < number < threshold:
        return f"<{threshold}"
    return value


def enforce(frame, columns: dict[str, str], publication: str):
    """Return (filtered frame, list of dropped columns).

    Columns absent from `columns` are treated as public. Nothing is silently
    shipped: the caller receives the list of what was removed and why.
    """
    target = LEVELS.get(str(publication).lower(), 0)
    keep, dropped = [], []
    for column in frame.columns:
        classification = columns.get(column, "public")
        if LEVELS.get(classification, 2) <= target:
            keep.append(column)
        else:
            dropped.append((column, classification))
    return frame[keep], dropped
