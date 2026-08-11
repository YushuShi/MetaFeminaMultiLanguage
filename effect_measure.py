"""Convert eligible ratio measures to a common relative-risk scale.

OR conversion uses the baseline-risk correction described by Zhang and Yu.
HR conversion assumes proportional hazards, while IRR conversion assumes a
constant event rate over the selected risk horizon.  Both assumptions yield
the same cumulative-risk transformation once a baseline risk is supplied.
"""

from __future__ import annotations

import math
import re


MAJOR_CANCER_BASELINE_RISKS = {
    "breast": 0.13,
    "ovary": 0.013,
    "uterus": 0.031,
}

RATIO_EFFECT_TYPES = {
    "OR", "RR", "IRR", "HR", "ODDS RATIO", "RISK RATIO", "RELATIVE RISK",
    "INCIDENCE RATE RATIO", "HAZARD RATIO",
}


def normalize_effect_type(effect_type):
    """Return the canonical RR, OR, HR, or IRR label, or ``None``."""
    normalized = re.sub(r"[^A-Z]+", " ", str(effect_type or "").upper()).strip()
    aliases = {
        "RR": "RR",
        "RISK RATIO": "RR",
        "RELATIVE RISK": "RR",
        "OR": "OR",
        "ODDS RATIO": "OR",
        "HR": "HR",
        "HAZARD RATIO": "HR",
        "IRR": "IRR",
        "INCIDENCE RATE RATIO": "IRR",
    }
    return aliases.get(normalized)


def is_eligible_effect_type(effect_type):
    """Return whether a ratio estimate can be converted to the RR scale."""
    return normalize_effect_type(effect_type) is not None


def baseline_risk_for_disease(disease) -> float:
    """Return the configured major-cancer baseline cumulative incidence."""
    normalized = re.sub(r"[^a-z]+", " ", str(disease or "").lower()).strip()
    if "breast" in normalized:
        return MAJOR_CANCER_BASELINE_RISKS["breast"]
    if "ovarian" in normalized or "ovary" in normalized:
        return MAJOR_CANCER_BASELINE_RISKS["ovary"]
    if "uterine" in normalized or "uterus" in normalized or "endometrial" in normalized:
        return MAJOR_CANCER_BASELINE_RISKS["uterus"]
    raise ValueError(f"No baseline cancer risk is configured for {disease!r}.")


def baseline_risk_from_percent(percent) -> float:
    """Convert a registry lifetime-risk percentage to a validated probability."""
    try:
        probability = float(percent) / 100.0
    except (TypeError, ValueError) as exc:
        raise ValueError("A numeric subtype lifetime-risk percentage is required.") from exc
    if not math.isfinite(probability) or not 0 < probability < 1:
        raise ValueError("Subtype lifetime-risk percentage must be between 0 and 100.")
    return probability


def convert_ratio_to_rr(value, effect_type, baseline_risk: float) -> float:
    """Convert an RR/OR/HR/IRR estimate to cumulative relative risk."""
    try:
        estimate = float(value)
        p0 = float(baseline_risk)
    except (TypeError, ValueError) as exc:
        raise ValueError("Effect estimate and baseline risk must be numeric.") from exc
    if not math.isfinite(estimate) or estimate <= 0:
        raise ValueError("Effect estimate must be finite and greater than zero.")
    if not math.isfinite(p0) or not 0 < p0 < 1:
        raise ValueError("Baseline risk must be a probability between zero and one.")

    canonical = normalize_effect_type(effect_type)
    if canonical == "RR":
        return estimate
    if canonical == "OR":
        return estimate / (1.0 - p0 + p0 * estimate)
    if canonical in {"HR", "IRR"}:
        # Numerically stable form of [1 - (1 - p0)^estimate] / p0.
        return -math.expm1(estimate * math.log1p(-p0)) / p0
    raise ValueError(f"Unsupported ratio effect type: {effect_type!r}.")
