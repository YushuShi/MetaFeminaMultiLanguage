#!/usr/bin/env python3
"""Regenerate saved web plots from cached study records without new searches."""

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import meta_analysis  # noqa: E402


ANALYSIS_KEYS = ("headline", "summary_html", "plot_url", "funnel_plot_url", "baujat_plot_url")
ELIGIBLE_QUALITY = {"good", "moderate"}
DISEASE_PREVALENCE = {
    "breast cancer": 0.13,
    "ovarian cancer": 0.013,
    "uterine cancer": 0.031,
}


def safe_component(value):
    return re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")


def remove_generated_plots(exposure, disease, outcome):
    folder = ROOT / "static" / safe_component(exposure)
    suffix = (
        f"{safe_component(disease)}_{safe_component(outcome)}_primary.png"
    )
    for prefix in ("forest", "funnel", "baujat"):
        (folder / f"{prefix}_{suffix}").unlink(missing_ok=True)


def analysis_frame(studies, disease):
    frame = pd.DataFrame(studies)
    for column in ("Effect Size", "Lower CI", "Upper CI", "SE", "Cases", "Estimated Cases", "Sample Size"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(
                frame[column].astype(str).str.replace(",", "", regex=False).str.strip(),
                errors="coerce",
            )

    quality = frame.get("Quality Score", pd.Series("", index=frame.index)).fillna("").astype(str).str.lower().str.strip()
    eligible_effect = frame.get("Effect Type", pd.Series("", index=frame.index)).map(
        meta_analysis.is_eligible_effect_type
    )
    cases = frame.get("Cases", pd.Series(float("nan"), index=frame.index))
    estimated_cases = frame.get("Estimated Cases", pd.Series(float("nan"), index=frame.index))
    sample_size = frame.get("Sample Size", pd.Series(float("nan"), index=frame.index))
    prevalence = DISEASE_PREVALENCE[disease.strip().lower()]
    derived_cases = (sample_size * prevalence + 0.5).floordiv(1)
    final_cases = cases.where(cases.notna(), estimated_cases).where(
        cases.notna() | estimated_cases.notna(), derived_cases
    )

    return frame.loc[
        quality.isin(ELIGIBLE_QUALITY)
        & eligible_effect
        & final_cases.gt(50)
    ].copy()


def regenerate(exposure, disease, outcome):
    exposure_dir = ROOT / "Cached_results" / exposure
    pattern = f"{safe_component(disease)}_{safe_component(outcome)}_true_*.json"
    exact_name = re.compile(
        re.escape(f"{safe_component(disease)}_{safe_component(outcome)}_true_")
        + r"(?:all|core)\.json$"
    )
    paths = sorted(path for path in exposure_dir.glob(pattern) if exact_name.match(path.name))
    if not paths:
        raise FileNotFoundError(f"No saved cache matched {exposure}/{pattern}")

    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        frame = pd.DataFrame(payload.get("studies", []))
        frame = meta_analysis.filter_curated_meta_analysis_exclusions(
            frame, disease, exposure, outcome
        )
        studies = frame.to_dict(orient="records")
        payload["studies"] = studies
        eligible = analysis_frame(studies, disease)
        if eligible.empty:
            remove_generated_plots(exposure, disease, outcome)
            for key in ANALYSIS_KEYS:
                payload.pop(key, None)
            payload["error"] = "No relevant evidence was identified in the reviewed sources."
            path.write_text(
                json.dumps(app.sanitize_data(payload), indent=4) + "\n",
                encoding="utf-8",
            )
            print(f"Regenerated {path.relative_to(ROOT)} with no default-eligible studies")
            continue

        result = meta_analysis.perform_meta_analysis(
            eligible,
            disease,
            exposure,
            outcome=outcome,
            exclude_meta=True,
            df_all=pd.DataFrame(studies),
        )
        if result.get("error"):
            raise RuntimeError(f"{path}: {result['error']}")

        payload.pop("error", None)
        for key in ANALYSIS_KEYS:
            payload[key] = result.get(key)
        path.write_text(json.dumps(app.sanitize_data(payload), indent=4) + "\n", encoding="utf-8")
        print(f"Regenerated {path.relative_to(ROOT)} from {len(eligible)} eligible studies")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disease", default="Breast Cancer")
    parser.add_argument("--outcome", default="Incidence")
    parser.add_argument("--exposure", action="append", required=True)
    args = parser.parse_args()

    for exposure in args.exposure:
        regenerate(exposure, args.disease, args.outcome)


if __name__ == "__main__":
    main()
