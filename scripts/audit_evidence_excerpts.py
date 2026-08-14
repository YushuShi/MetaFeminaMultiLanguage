#!/usr/bin/env python3
"""Audit the evidence excerpts shown by the default MetaFemina UI.

The application resolves one saved cache per disease/exposure pair: a
``*_true_core.json`` cache when present, otherwise ``*_true_all.json``.  This
script deliberately follows that same rule so dormant cache variants do not
inflate the user-facing count.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / "Cached_results"
DISEASES = ("breast_cancer", "ovarian_cancer", "uterine_cancer")


def _numeric(value: Any) -> bool:
    try:
        return math.isfinite(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return False


def _present(value: Any) -> bool:
    return bool(str(value or "").strip())


@dataclass(frozen=True)
class EvidenceGap:
    exposure: str
    disease: str
    cache_path: Path
    pmid: str
    missing_fields: tuple[str, ...]


def preferred_cache(exposure_dir: Path, disease: str) -> Path | None:
    core = exposure_dir / f"{disease}_incidence_true_core.json"
    fallback = exposure_dir / f"{disease}_incidence_true_all.json"
    if core.is_file():
        return core
    return fallback if fallback.is_file() else None


def scan_preferred_caches(cache_root: Path = CACHE_ROOT) -> list[EvidenceGap]:
    gaps: list[EvidenceGap] = []
    for exposure_dir in sorted(path for path in cache_root.iterdir() if path.is_dir()):
        for disease in DISEASES:
            cache_path = preferred_cache(exposure_dir, disease)
            if cache_path is None:
                continue
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            for study in payload.get("studies", []):
                support = study.get("extraction_supporting_text")
                support = support if isinstance(support, dict) else {}
                missing: list[str] = []
                if _numeric(study.get("Sample Size")) and not _present(support.get("sample_size")):
                    missing.append("sample_size")
                if _numeric(study.get("Effect Size")) and not _present(support.get("effect_size")):
                    missing.append("effect_size")
                if missing:
                    gaps.append(EvidenceGap(
                        exposure=exposure_dir.name,
                        disease=disease,
                        cache_path=cache_path,
                        pmid=str(study.get("PMID") or ""),
                        missing_fields=tuple(missing),
                    ))
    return gaps


def _summary(gaps: Iterable[EvidenceGap]) -> dict[str, Any]:
    rows = list(gaps)
    return {
        "affected_exposure_count": len({row.exposure for row in rows}),
        "affected_row_count": len(rows),
        "affected_pmid_count": len({row.pmid for row in rows}),
        "affected_exposures": sorted({row.exposure for row in rows}),
        "rows": [
            {
                "exposure": row.exposure,
                "disease": row.disease,
                "cache": str(row.cache_path.relative_to(ROOT)),
                "pmid": row.pmid,
                "missing_fields": list(row.missing_fields),
            }
            for row in rows
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--fail-on-gaps", action="store_true")
    args = parser.parse_args()

    summary = _summary(scan_preferred_caches())
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"{summary['affected_exposure_count']} affected exposures; "
            f"{summary['affected_row_count']} rows; "
            f"{summary['affected_pmid_count']} unique PMIDs"
        )
        for exposure in summary["affected_exposures"]:
            print(f"- {exposure}")
    return 1 if args.fail_on_gaps and summary["affected_row_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
