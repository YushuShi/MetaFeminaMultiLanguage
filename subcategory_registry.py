"""Validated registry for the supported female-cancer subcategories.

The CSV is the sole source of display names and lifetime risks.  Stable IDs are
derived deterministically so persisted annotations and UI links do not depend on
row order or presentation labels.
"""
from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


CSV_COLUMNS = (
    "primary_site",
    "cancer_type",
    "estimated_lifetime_probability_us_women_percent",
)
SITE_IDS = {"Breast": "breast", "Uterus": "uterus", "Ovary": "ovary"}
MAJOR_DISEASE_BY_SITE_ID = {
    "breast": "Breast cancer",
    "uterus": "Uterine cancer",
    "ovary": "Ovarian cancer",
}


def stable_id(value: str) -> str:
    """Return a predictable lower-snake-case identifier for a label."""
    identifier = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    if not identifier:
        raise ValueError("A stable ID cannot be empty")
    return identifier


@dataclass(frozen=True)
class Subcategory:
    subcategory_id: str
    major_site_id: str
    primary_site: str
    cancer_type: str
    estimated_lifetime_probability_us_women_percent: float

    def to_dict(self) -> dict:
        return asdict(self)


class SubcategoryRegistry:
    """Lookup API shared by enrichment, plotting, and Flask/UI layers."""

    def __init__(self, subcategories: Iterable[Subcategory]):
        self.subcategories = tuple(subcategories)
        self.by_id = {item.subcategory_id: item for item in self.subcategories}
        if len(self.by_id) != len(self.subcategories):
            raise ValueError("Subcategory IDs must be unique")
        self.by_site = {
            site_id: tuple(item for item in self.subcategories if item.major_site_id == site_id)
            for site_id in MAJOR_DISEASE_BY_SITE_ID
        }

    def for_site(self, major_site_id: str) -> tuple[Subcategory, ...]:
        if major_site_id not in self.by_site:
            raise KeyError(f"Unknown major site ID: {major_site_id}")
        return self.by_site[major_site_id]

    def is_known_subcategory(self, subcategory_id: str, major_site_id: str | None = None) -> bool:
        item = self.by_id.get(subcategory_id)
        return bool(item and (major_site_id is None or item.major_site_id == major_site_id))

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "major_sites": [
                {
                    "major_site_id": site_id,
                    "major_disease": MAJOR_DISEASE_BY_SITE_ID[site_id],
                    "subcategories": [item.to_dict() for item in self.for_site(site_id)],
                }
                for site_id in MAJOR_DISEASE_BY_SITE_ID
            ],
        }


def load_registry(csv_path: str | Path | None = None) -> SubcategoryRegistry:
    """Load and strictly validate ``common_breast_uterine_ovarian_cancer_types.csv``."""
    path = Path(csv_path) if csv_path else Path(__file__).with_name(
        "common_breast_uterine_ovarian_cancer_types.csv"
    )
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise ValueError(f"Unexpected columns in {path}: {reader.fieldnames!r}")
        entries: list[Subcategory] = []
        seen_labels: set[tuple[str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            primary_site = (row.get("primary_site") or "").strip()
            cancer_type = (row.get("cancer_type") or "").strip()
            if primary_site not in SITE_IDS or not cancer_type:
                raise ValueError(f"Invalid site/type at row {row_number}")
            label = (primary_site, cancer_type.casefold())
            if label in seen_labels:
                raise ValueError(f"Duplicate subcategory at row {row_number}: {label}")
            seen_labels.add(label)
            try:
                risk = float(row["estimated_lifetime_probability_us_women_percent"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid lifetime probability at row {row_number}") from exc
            if not 0 < risk <= 100:
                raise ValueError(f"Lifetime probability out of range at row {row_number}")
            site_id = SITE_IDS[primary_site]
            entries.append(
                Subcategory(
                    subcategory_id=f"{site_id}_{stable_id(cancer_type)}",
                    major_site_id=site_id,
                    primary_site=primary_site,
                    cancer_type=cancer_type,
                    estimated_lifetime_probability_us_women_percent=risk,
                )
            )
    if set(item.major_site_id for item in entries) != set(MAJOR_DISEASE_BY_SITE_ID):
        raise ValueError("The registry must contain breast, uterus, and ovary subcategories")
    return SubcategoryRegistry(entries)


REGISTRY = load_registry()
