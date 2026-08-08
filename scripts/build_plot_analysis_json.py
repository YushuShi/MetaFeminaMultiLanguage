#!/usr/bin/env python3
"""Build plot-ready summary rows directly from saved study caches."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import meta_analysis  # noqa: E402


DISEASES = {"breast": "Breast cancer", "ovarian": "Ovarian cancer", "uterine": "Uterine cancer"}


def summarize_cache(path: Path, disease: str, exposure: str, dietary: bool) -> dict | None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(payload.get("studies", []))
    if frame.empty:
        return None
    frame = meta_analysis.filter_curated_meta_analysis_exclusions(
        frame, disease, exposure, "Incidence"
    )
    if frame.empty:
        return None
    if dietary:
        if "exposure_measurement_type" not in frame:
            return None
        measurement = frame["exposure_measurement_type"].fillna("").astype(str).str.strip().str.lower()
        frame = frame.loc[measurement.eq("dietary_intake")].copy()
    if frame.empty:
        return None
    for column in ("Effect Size", "Lower CI", "Upper CI", "Cases", "Sample Size", "Estimated Cases"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column].astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")
    cases = frame.get("Cases", pd.Series(np.nan, index=frame.index)).fillna(frame.get("Estimated Cases", pd.Series(np.nan, index=frame.index)))
    eligible_effect = frame.get("Effect Type", pd.Series("", index=frame.index)).map(
        meta_analysis.is_eligible_effect_type
    )
    quality = frame.get("Quality Score", pd.Series("Fair", index=frame.index)).fillna("Fair").astype(str).str.strip().str.lower()
    valid = frame.loc[(frame["Effect Size"] > 0) & (frame["Lower CI"] > 0) & (frame["Upper CI"] > 0) & (cases >= 50) & eligible_effect & quality.isin({"good", "moderate"})].copy()
    if valid.empty:
        return None
    result = meta_analysis.perform_meta_analysis(valid, disease, exposure, generate_plots=False, df_all=valid)
    headline = result.get("headline")
    if not headline:
        return None
    sample_sizes = valid.get("Sample Size", pd.Series(0, index=valid.index)).fillna(0)
    case_counts = valid.get("Cases", pd.Series(np.nan, index=valid.index)).fillna(valid.get("Estimated Cases", pd.Series(0, index=valid.index))).fillna(0)
    return {"Exposure": exposure, "number studies": int(len(valid)), "Pooled RR": headline.get("pooled_es"), "lower CI RR": headline.get("ci_low"), "upper CI RR": headline.get("ci_upp"), "lower PI RR": headline.get("pi_low"), "upper PI RR": headline.get("pi_upp"), "I^2 (%)": round(float(headline.get("i2") or 0), 1), "eggers p-value": headline.get("eggers_p"), "total N": int(sample_sizes.sum()), "total Cases": int(case_counts.sum())}


def build() -> dict:
    output = {"combined": {}, "dietary": {}}
    cache_root = REPO_ROOT / "Cached_results"
    for disease_key, disease in DISEASES.items():
        filename = f"{disease.replace(' ', '_').lower()}_incidence_true_all.json"
        for dataset, dietary in (("combined", False), ("dietary", True)):
            rows = []
            for path in sorted(cache_root.glob(f"*/{filename}")):
                if path.parent.name == "multivitamin":
                    continue
                try:
                    row = summarize_cache(path, disease, path.parent.name, dietary)
                except Exception as exc:
                    print(f"Skipped {path}: {exc}", file=sys.stderr)
                    continue
                if row:
                    rows.append(row)
            output[dataset][disease_key] = sorted(rows, key=lambda row: row["Pooled RR"])
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
