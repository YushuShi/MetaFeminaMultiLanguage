#!/usr/bin/env python3
"""Add derived p-values where a saved estimate has a 95% CI but no p-value."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import meta_analysis  # noqa: E402


def has_numeric_p_value(text: object) -> bool:
    cleaned = re.sub(r"<[^>]+>", "", str(text or ""))
    return bool(re.search(r"\d", cleaned))


def add_missing_p_values(cache_root: Path, write: bool = False) -> dict[str, int]:
    changed_files = 0
    changed_records = 0
    for path in sorted(cache_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        studies = payload.get("studies", []) if isinstance(payload, dict) else []
        file_changed = False
        for study in studies:
            if not isinstance(study, dict) or study.get("P Value") not in (None, ""):
                continue
            supporting = study.get("extraction_supporting_text")
            if not isinstance(supporting, dict):
                supporting = {}
                study["extraction_supporting_text"] = supporting
            existing_text = supporting.get("p_value")
            if has_numeric_p_value(existing_text):
                continue
            p_value = meta_analysis.p_value_from_effect_ci(
                study.get("Effect Size"),
                study.get("Lower CI"),
                study.get("Upper CI"),
                study.get("Effect Type"),
            )
            if p_value is None:
                continue
            formatted = meta_analysis.format_computed_p_value(p_value)
            prefix = str(existing_text or "").strip()
            computed_text = (
                "Computed from the reported effect and 95% CI using a normal "
                f"approximation: {formatted}."
            )
            supporting["p_value"] = f"{prefix} {computed_text}".strip()
            study["P Value"] = p_value
            changed_records += 1
            file_changed = True
        if file_changed:
            changed_files += 1
            if write:
                path.write_text(
                    json.dumps(payload, ensure_ascii=True, indent=4) + "\n",
                    encoding="utf-8",
                )
    return {"changed_files": changed_files, "changed_records": changed_records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=REPO_ROOT / "Cached_results")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(add_missing_p_values(args.cache_root, write=args.write), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
