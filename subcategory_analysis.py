"""Offline analysis and plotting for annotated cancer subcategories.

This module deliberately does not import the live analysis pipeline or call any
external service.  It consumes the saved enrichment annotations, preserves the
major-cancer caches, and writes a separate, reproducible output tree.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import forestplot
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle


MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_ANNOTATIONS = MODULE_DIR / "data" / "subcategory_annotations.json"
DEFAULT_RESULTS_ROOT = MODULE_DIR / "data" / "subcategory_results"
DEFAULT_PLOT_ROOT = MODULE_DIR / "Plot" / "subcategories"
DEFAULT_REGISTRY_CSV = MODULE_DIR / "common_breast_uterine_ovarian_cancer_types.csv"
DEFAULT_CACHE_ROOT = MODULE_DIR / "Cached_results"
SCHEMA_VERSION = "1.0"
FORMAL_EGGER_MIN_STUDIES = 10
TERRA_INPUT_USD_PER_MILLION = 2.0
ELIGIBLE_EFFECT_TYPES = {
    "OR", "RR", "IRR", "HR", "ODDS RATIO", "RISK RATIO", "RELATIVE RISK",
    "INCIDENCE RATE RATIO", "HAZARD RATIO",
}
SUMMARY_PLOT_LOCALES = ("zh-CN", "zh-TW", "nl", "ko")
SUMMARY_TRANSLATIONS = MODULE_DIR / "static" / "i18n-translations.json"

_SUMMARY_TRANSLATION_LOOKUP: dict[str, dict[str, str]] | None = None
_SUMMARY_FONT_FAMILIES: dict[str, str | None] = {}

EXPOSURE_GROUP_ORDER = (
    "Carotenoids",
    "Vitamins A, C, D, E, K",
    "Minerals & Trace Elements",
    "Polyphenols & Flavonoids",
    "Fruits & Vegetables",
    "Fermented Foods & Probiotics",
    "Fatty Acids & Lipids",
    "Herbal & Botanical",
    "Other",
)
EXPOSURE_GROUPS = {
    "alcohol": "Other",
    "beta_carotene": "Carotenoids",
    "black_cohosh": "Herbal & Botanical",
    "caffeine": "Other",
    "calcium": "Minerals & Trace Elements",
    "dairy": "Other",
    "fish_oil": "Fatty Acids & Lipids",
    "green_tea": "Polyphenols & Flavonoids",
    "lactobacillus": "Fermented Foods & Probiotics",
    "legumes": "Fruits & Vegetables",
    "mediterranean_diet": "Other",
    "molybdenum": "Minerals & Trace Elements",
    "potassium": "Minerals & Trace Elements",
    "tea": "Polyphenols & Flavonoids",
    "vitamin_c": "Vitamins A, C, D, E, K",
    "vitamin_d": "Vitamins A, C, D, E, K",
}
EXPOSURE_GROUP_COLORS = {
    "Carotenoids": "#E55300",
    "Vitamins A, C, D, E, K": "#C79000",
    "Minerals & Trace Elements": "#007C7C",
    "Polyphenols & Flavonoids": "#6A0DAD",
    "Fruits & Vegetables": "#2E7D32",
    "Fermented Foods & Probiotics": "#00838F",
    "Fatty Acids & Lipids": "#B5001F",
    "Herbal & Botanical": "#00695C",
    "Other": "#37474F",
}
EXPOSURE_GROUP_BACKGROUNDS = {
    "Carotenoids": "#FDEEE6",
    "Vitamins A, C, D, E, K": "#FBF6E0",
    "Minerals & Trace Elements": "#DFF2F2",
    "Polyphenols & Flavonoids": "#F2E8FB",
    "Fruits & Vegetables": "#E6F4E6",
    "Fermented Foods & Probiotics": "#E0F7FA",
    "Fatty Acids & Lipids": "#FBEAED",
    "Herbal & Botanical": "#E0F2EF",
    "Other": "#ECEFF1",
}


def slugify(value: Any) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return value or "unknown"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=_json_default)
    path.write_text(text + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _as_float(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _cached_study_metadata(cache_root: Path) -> dict[str, dict[str, Any]]:
    """Index publication metadata already saved in MetaFemina's caches.

    This is deliberately local-only: subtype builds must not make literature
    calls just to recover bibliographic fields that the platform already has.
    """
    indexed: dict[str, dict[str, Any]] = {}
    ranks: dict[str, tuple[int, int, int]] = {}
    if not cache_root.is_dir():
        return indexed
    for path in sorted(cache_root.rglob("*.json")):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        studies = payload.get("studies", []) if isinstance(payload, dict) else []
        for study in studies:
            if not isinstance(study, dict):
                continue
            pmid = str(_first(study, "PMID", "pmid") or "").strip()
            if not pmid:
                continue
            candidate = {
                "Study": _first(study, "Study", "study"),
                "Authors": _first(study, "Authors", "authors"),
                "Journal": _first(study, "Journal", "journal"),
                "Year": _first(study, "Year", "year", "publication_year"),
                "Reference": _first(study, "Reference", "reference", "Title", "title"),
                "exposure_measurement_type": _first(
                    study, "exposure_measurement_type"
                ),
                "exposure_measurement_supporting_text": _first(
                    study, "exposure_measurement_supporting_text"
                ),
                "Quality Score": _first(study, "Quality Score", "quality_score"),
                "Quality %": _first(study, "Quality %", "quality_percent"),
                "JBI": study.get("JBI") if isinstance(study.get("JBI"), dict) else {},
                "Sample Size": _first(study, "Sample Size", "sample_size"),
                "Cases": _first(study, "Cases", "cases", "Estimated Cases"),
            }
            completeness = sum(value not in (None, "") for value in candidate.values())
            # PMID-only entries provide the bibliographic fallback.
            pmid_rank = (0, 0, completeness)
            if pmid_rank > ranks.get(pmid, (-1, -1, -1)):
                indexed[pmid] = candidate
                ranks[pmid] = pmid_rank

            filename = path.stem.lower()
            major_site_id = None
            for prefix, site_id in (
                ("breast_cancer_", "breast"),
                ("ovarian_cancer_", "ovary"),
                ("uterine_cancer_", "uterus"),
            ):
                if filename.startswith(prefix):
                    major_site_id = site_id
                    break
            if not major_site_id:
                continue
            context_key = f"{pmid}|{major_site_id}|{slugify(path.parent.name)}"
            # Match the main-page lookup order: core before all, then the
            # untagged/default-model cache before model-specific fallbacks.
            core_priority = int("_true_core" in filename)
            default_model_priority = int(bool(re.search(r"_true_(?:core|all)$", filename)))
            context_rank = (core_priority, default_model_priority, completeness)
            if context_rank > ranks.get(context_key, (-1, -1, -1)):
                indexed[context_key] = candidate
                ranks[context_key] = context_rank
    return indexed


def _study_label(metadata: dict[str, Any], source: dict[str, Any], pmid: str) -> str:
    authors = str(_first(metadata, "Authors", "authors") or "").strip(" ,")
    year = str(_first(metadata, "Year", "year", "publication_year") or "").strip()
    if authors:
        first_author = authors.split(",", 1)[0].strip()
        author_label = f"{first_author} et al." if "," in authors else first_author
    else:
        saved_label = str(
            _first(metadata, "Study", "study") or _first(source, "Study", "study") or ""
        ).strip()
        match = re.match(r"^(.+?)(?:\s*\((\d{4})\))(?:\s*\[PMID:\s*\d+\])?$", saved_label)
        if match:
            author_label = match.group(1).strip()
            year = year or match.group(2)
        else:
            author_label = "Author unavailable"
    year_label = f" ({year})" if year else ""
    return f"{author_label}{year_label} [PMID: {pmid}]"


def _registry_records(registry_csv: Path = DEFAULT_REGISTRY_CSV) -> list[dict[str, Any]]:
    """Load taxonomy via the shared registry module, never a duplicate table.

    The registry implementation is intentionally allowed a small API evolution
    window while the enrichment and analysis changes land together.  It must
    return CSV-backed records; a clear error is raised otherwise.
    """
    try:
        import subcategory_registry as registry  # provided by the registry task
    except ImportError as exc:  # pragma: no cover - integration error, not data error
        raise RuntimeError("The CSV-backed subcategory_registry module is required.") from exc

    for name in ("load_registry", "get_registry", "load_subcategory_registry"):
        loader = getattr(registry, name, None)
        if callable(loader):
            try:
                records = loader(registry_csv)
            except TypeError:
                records = loader()
            if hasattr(records, "subcategories"):
                records = [item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in records.subcategories]
            elif hasattr(records, "to_dict"):
                registry_data = records.to_dict()
                major_sites = registry_data.get("major_sites", []) if isinstance(registry_data, dict) else []
                records = [subcategory for site in major_sites for subcategory in site.get("subcategories", [])]
            elif isinstance(records, dict):
                records = records.get("subcategories") or records.get("categories") or records.get("records")
            if isinstance(records, list):
                return [dict(item) for item in records]

    records_attr = getattr(registry, "SUBCATEGORY_REGISTRY", None)
    if isinstance(records_attr, list):
        return [dict(item) for item in records_attr]
    raise RuntimeError("subcategory_registry exposes no supported CSV-backed registry loader.")


def _normalize_registry(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for raw in records:
        major = str(_first(raw, "major_site_id", "primary_site_id", "primary_site", "site") or "").lower()
        category_id = _first(raw, "subcategory_id", "category_id", "id", "stable_id")
        label = _first(raw, "label", "cancer_type", "name", "subcategory")
        if not category_id and major and label:
            category_id = f"{major}.{slugify(label)}"
        if not category_id or not major or not label:
            continue
        category_id = str(category_id)
        category_slug = _first(raw, "subcategory_slug", "slug")
        if not category_slug:
            category_slug = category_id.split(".")[-1]
            major_prefix = f"{major}_"
            if str(category_slug).startswith(major_prefix):
                category_slug = str(category_slug)[len(major_prefix):]
        risk = _as_float(_first(raw, "estimated_lifetime_probability_us_women_percent", "lifetime_risk_percent"))
        normalized[category_id] = {
            "subcategory_id": category_id,
            "major_site_id": major,
            "subcategory_slug": slugify(category_slug),
            "label": str(label),
            # Taxonomy metadata only. It is never used by the pooling code.
            "estimated_lifetime_probability_us_women_percent": risk,
        }
    if not normalized:
        raise RuntimeError("The subcategory registry yielded no valid records.")
    return normalized


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if any(key in value for key in ("context_id", "subcategory_outcomes", "major_outcomes")):
            return [value]
        answer = []
        for key, item in value.items():
            if isinstance(item, dict):
                copied = dict(item)
                copied.setdefault("context_id", key)
                answer.append(copied)
        return answer
    return []


def _context_id(item: dict[str, Any]) -> str | None:
    value = _first(item, "context_id", "source_context_id", "id")
    return str(value) if value not in (None, "") else None


def _extract_contexts(payload: Any, annotations_path: Path) -> dict[str, dict[str, Any]]:
    """Collect explicitly saved contexts from the annotation payload/companions."""
    containers: list[Any] = []
    if isinstance(payload, dict):
        containers.extend(payload.get(key) for key in ("contexts", "context_index", "saved_contexts", "sources", "saved_sources"))
    for sibling in (annotations_path.with_name("subcategory_contexts.json"), annotations_path.with_name("subcategory_sources.json")):
        if sibling.is_file():
            sibling_payload = _read_json(sibling)
            if isinstance(sibling_payload, dict):
                containers.extend(sibling_payload.get(key) for key in ("contexts", "context_index", "saved_contexts"))
                # The source index is keyed by PMID and owns the title/PMCID,
                # while its `contexts` list supplies the relationship.
                source_index = sibling_payload.get("sources", {})
                if isinstance(source_index, dict):
                    for pmid, source in source_index.items():
                        if not isinstance(source, dict):
                            continue
                        for context_id in source.get("contexts", []):
                            containers.append({
                                "context_id": context_id,
                                "pmid": source.get("pmid", pmid),
                                "title": source.get("title"),
                                "pmcid": source.get("pmcid"),
                            })
            else:
                containers.append(sibling_payload)

    contexts: dict[str, dict[str, Any]] = {}
    for container in containers:
        for context in _items(container):
            context_id = _context_id(context)
            if context_id:
                # Merge rather than overwrite: context_index contributes the
                # effect/exposure, source index contributes publication info.
                contexts[context_id] = {**contexts.get(context_id, {}), **context}
    return contexts


def _active_source_hashes(payload: Any, annotations_path: Path) -> set[str]:
    hashes: set[str] = set()
    candidates = [payload] if isinstance(payload, dict) else []
    sibling = annotations_path.with_name("subcategory_sources.json")
    if sibling.is_file():
        candidates.append(_read_json(sibling))
    for candidate in candidates:
        sources = candidate.get("sources", {}) if isinstance(candidate, dict) else {}
        context_index = candidate.get("context_index", {}) if isinstance(candidate, dict) else {}
        active_context_ids = set(context_index) if isinstance(context_index, dict) else set()
        if isinstance(sources, dict):
            for source in sources.values():
                source_contexts = source.get("contexts", []) if isinstance(source, dict) else []
                is_active = not active_context_ids or any(
                    str(context_id) in active_context_ids for context_id in source_contexts
                )
                if isinstance(source, dict) and source.get("source_hash") and is_active:
                    hashes.add(str(source["source_hash"]))
    return hashes


def _extract_annotations(payload: Any, active_source_hashes: set[str] | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _items(payload)
    if not isinstance(payload, dict):
        return []
    events = payload.get("events")
    if isinstance(events, list):
        # The ledger is append-only.  The last complete event for a saved
        # source is authoritative (a Luna review supersedes its Terra pass).
        latest: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        for event in events:
            if not isinstance(event, dict) or event.get("status") != "complete" or not isinstance(event.get("result"), dict):
                continue
            if active_source_hashes and str(event.get("source_hash") or "") not in active_source_hashes:
                continue
            result = dict(event["result"])
            pmid = str(result.get("pmid") or event.get("pmid") or "")
            source_hash = str(event.get("source_hash") or pmid)
            created_at = str(event.get("created_at") or "")
            key = (pmid, source_hash)
            if key not in latest or created_at >= latest[key][0]:
                result["_ledger_event"] = {key: event.get(key) for key in ("event_id", "created_at", "stage", "model", "source_hash", "usage")}
                latest[key] = (created_at, result)
        return [latest[key][1] for key in sorted(latest)]
    for key in ("annotations", "records", "items", "studies"):
        if key in payload:
            return _items(payload[key])
    return _items(payload)


def _major_outcomes(annotation: dict[str, Any]) -> list[dict[str, Any]]:
    major = annotation.get("major_outcomes")
    if isinstance(major, list):
        return _items(major)
    if isinstance(major, dict):
        result = []
        for key, value in major.items():
            if not isinstance(value, dict):
                continue
            copied = dict(value)
            copied.setdefault("major_site_id", key)
            result.append(copied)
        return result
    return []


def _subtype_outcomes(major_outcome: dict[str, Any]) -> list[dict[str, Any]]:
    return _items(major_outcome.get("subcategory_outcomes"))


def _estimate_items(annotation: dict[str, Any], subtype: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explicit estimate entries; do not synthesize a major estimate."""
    estimates = subtype.get("estimates")
    if isinstance(estimates, list):
        return [item for item in estimates if isinstance(item, dict)]
    # Backwards-compatible support for a direct subtype `effect_estimate`.
    # This still remains subtype-specific because it is nested below the
    # subtype outcome, never copied from a major-cancer cache row.
    if isinstance(subtype.get("effect_estimate"), dict):
        estimate = dict(subtype["effect_estimate"])
        estimate.setdefault("context_id", _context_id(annotation))
        return [estimate]
    return []


def _study_source(context: dict[str, Any]) -> dict[str, Any]:
    for key in ("study", "study_data", "source_study", "saved_study", "record"):
        candidate = context.get(key)
        if isinstance(candidate, dict):
            return candidate
    return context


def _exposure(context: dict[str, Any], annotation: dict[str, Any], source: dict[str, Any]) -> str | None:
    for mapping in (context, annotation, source):
        value = _first(mapping, "exposure", "exposure_name", "canonical_exposure", "exposure_id")
        if value not in (None, ""):
            return str(value)
    return None


def _estimate(outcome: dict[str, Any]) -> dict[str, Any] | None:
    candidate = outcome.get("effect_estimate")
    if not isinstance(candidate, dict):
        candidate = outcome.get("estimate") if isinstance(outcome.get("estimate"), dict) else outcome
    effect = _as_float(_first(candidate, "effect_size", "Effect Size", "effect", "estimate"))
    lower = _as_float(_first(candidate, "lower_ci", "Lower CI", "ci_low", "lower"))
    upper = _as_float(_first(candidate, "upper_ci", "Upper CI", "ci_upp", "upper"))
    if (
        effect is None or lower is None or upper is None
        or effect <= 0 or lower <= 0 or upper <= 0
        or lower > effect or effect > upper
    ):
        return None
    effect_type = re.sub(
        r"[^A-Z]+", " ",
        str(_first(candidate, "effect_type", "Effect Type", "measure") or "").upper(),
    ).strip()
    if effect_type not in ELIGIBLE_EFFECT_TYPES:
        return None
    return {
        "effect_size": effect,
        "lower_ci": lower,
        "upper_ci": upper,
        "effect_type": effect_type,
        "se": _as_float(_first(candidate, "se", "SE", "standard_error")),
        "comparison_type": _first(candidate, "comparison_type", "comparison"),
        "cases": _as_float(_first(candidate, "cases", "Cases")),
        "sample_size": _as_float(_first(candidate, "sample_size", "Sample Size", "participants", "Participants")),
    }


def extract_eligible_rows(
    annotations_path: Path,
    registry: dict[str, dict[str, Any]],
    study_metadata: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return subtype estimate rows and explicit skips from saved annotations.

    A context must be in the saved context/source inventory.  In particular, a
    generic major-cancer estimate is never silently promoted to a subtype.
    """
    payload = _read_json(annotations_path)
    contexts = _extract_contexts(payload, annotations_path)
    active_source_hashes = _active_source_hashes(payload, annotations_path)
    study_metadata = study_metadata or {}
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for annotation in _extract_annotations(payload, active_source_hashes):
        for major in _major_outcomes(annotation):
            major_id = str(_first(major, "major_site_id", "major_id", "site") or "").lower()
            for subtype in _subtype_outcomes(major):
                category_id = _first(subtype, "subcategory_id", "category_id", "id")
                status = str(subtype.get("status") or "")
                if status != "reported_separate_estimate":
                    continue
                if not category_id or str(category_id) not in registry:
                    skipped.append({"context_id": _context_id(annotation), "reason": "unknown_subcategory_id", "subcategory_id": category_id})
                    continue
                category = registry[str(category_id)]
                if major_id and major_id != category["major_site_id"]:
                    skipped.append({"context_id": _context_id(annotation), "reason": "major_subcategory_mismatch", "subcategory_id": category_id})
                    continue
                estimates = _estimate_items(annotation, subtype)
                if not estimates:
                    skipped.append({"context_id": _context_id(annotation), "reason": "invalid_or_missing_subtype_estimate", "subcategory_id": category_id})
                for estimate_item in estimates:
                    context_id = _context_id(estimate_item) or _context_id(annotation)
                    if not context_id or context_id not in contexts:
                        skipped.append({"context_id": context_id, "reason": "unknown_context_id", "subcategory_id": category_id})
                        continue
                    context = contexts[context_id]
                    source = _study_source(context)
                    exposure = _exposure(context, annotation, source)
                    if not exposure:
                        skipped.append({"context_id": context_id, "reason": "missing_exposure", "subcategory_id": category_id})
                        continue
                    estimate = _estimate(estimate_item)
                    if not estimate:
                        skipped.append({"context_id": context_id, "reason": "invalid_or_missing_subtype_estimate", "subcategory_id": category_id})
                        continue
                    pmid = str(_first(source, "PMID", "pmid") or "").strip()
                    metadata = {
                        **study_metadata.get(pmid, {}),
                        **study_metadata.get(
                            f"{pmid}|{category['major_site_id']}|{slugify(exposure)}", {}
                        ),
                    }
                    reference = _first(metadata, "Reference", "reference") or _first(
                        source, "Reference", "reference", "title", "Title"
                    )
                    quality_score = str(
                        _first(metadata, "Quality Score", "quality_score")
                        or _first(source, "Quality Score", "quality_score")
                        or ""
                    ).strip()
                    if quality_score.lower() not in {"good", "moderate"}:
                        skipped.append({
                            "context_id": context_id,
                            "reason": "jbi_below_moderate",
                            "subcategory_id": category_id,
                            "quality_score": quality_score or None,
                        })
                        continue
                    if estimate.get("sample_size") is None:
                        estimate["sample_size"] = _as_float(
                            _first(metadata, "Sample Size", "sample_size")
                        )
                    if estimate.get("cases") is None:
                        estimate["cases"] = _as_float(
                            _first(metadata, "Cases", "cases", "Estimated Cases")
                        )
                    rows.append({
                        "context_id": context_id,
                        "exposure": exposure,
                        "study": _study_label(metadata, source, pmid) if pmid else "Author unavailable",
                        "pmid": pmid or None,
                        "authors": _first(metadata, "Authors", "authors"),
                        "journal": _first(metadata, "Journal", "journal"),
                        "year": _first(metadata, "Year", "year", "publication_year"),
                        "quality_score": quality_score,
                        "quality_percent": _first(metadata, "Quality %", "quality_percent"),
                        "jbi": metadata.get("JBI") if isinstance(metadata.get("JBI"), dict) else {},
                        "exposure_measurement_type": _first(
                            metadata, "exposure_measurement_type"
                        ) or "unclear",
                        "exposure_measurement_supporting_text": _first(
                            metadata, "exposure_measurement_supporting_text"
                        ) or "",
                        "reference": reference,
                        "major_site_id": category["major_site_id"],
                        "subcategory_id": category["subcategory_id"],
                        "subcategory_slug": category["subcategory_slug"],
                        "subcategory_label": category["label"],
                        "lifetime_risk_percent": category["estimated_lifetime_probability_us_women_percent"],
                        "evidence_source": (
                            subtype.get("evidence_source")
                            or annotation.get("_ledger_event", {}).get("stage")
                        ),
                        "evidence_locator": (
                            subtype.get("evidence_locator")
                            or estimate_item.get("supporting_text")
                            or subtype.get("evidence_text")
                        ),
                        "outcome_definition": subtype.get("outcome_definition"),
                        **estimate,
                    })
    rows.sort(key=lambda row: (row["major_site_id"], row["subcategory_slug"], slugify(row["exposure"]), row["context_id"]))
    return rows, skipped


def _pool(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n_studies": 0, "pooled_es": None, "ci_low": None, "ci_upp": None, "i2": None, "tau2": None, "q": None, "eggers_p": None, "eggers_intercept": None}
    y = np.asarray([math.log(row["effect_size"]) for row in rows], dtype=float)
    se = np.asarray([(math.log(row["upper_ci"]) - math.log(row["lower_ci"])) / 3.92 for row in rows], dtype=float)
    if np.any(se <= 0) or not np.all(np.isfinite(se)):
        raise ValueError("Eligible subtype estimate has an invalid confidence interval width.")
    variances = se ** 2
    weights = 1.0 / variances
    fixed = float(np.sum(weights * y) / np.sum(weights))
    q = float(np.sum(weights * (y - fixed) ** 2))
    df = n - 1
    c = float(np.sum(weights) - np.sum(weights ** 2) / np.sum(weights)) if n > 1 else 0.0
    tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
    random_weights = 1.0 / (variances + tau2)
    pooled_log = float(np.sum(random_weights * y) / np.sum(random_weights))
    pooled_se = math.sqrt(float(1.0 / np.sum(random_weights)))
    low, high = pooled_log - 1.96 * pooled_se, pooled_log + 1.96 * pooled_se
    i2 = max(0.0, ((q - df) / q) * 100.0) if q > 0 and n > 1 else 0.0
    intercept = pvalue = None
    if n >= 3:
        try:
            model = sm.OLS(y / se, sm.add_constant(1.0 / se)).fit()
            intercept = float(model.params[0])
            pvalue = float(model.pvalues[0])
        except Exception:
            pass
    return {
        "n_studies": n,
        "pooled_es": math.exp(pooled_log),
        "ci_low": math.exp(low),
        "ci_upp": math.exp(high),
        "i2": i2,
        "tau2": tau2,
        "q": q,
        "eggers_p": pvalue,
        "eggers_intercept": intercept,
    }


def _leave_one_out(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run sensitivity analysis only within one subtype/exposure result set."""
    if len(rows) < 3:
        return []
    results = []
    for index, row in enumerate(rows):
        subset = rows[:index] + rows[index + 1:]
        pooled = _pool(subset)
        results.append({
            "omitted": row["study"],
            "pooled_es": pooled["pooled_es"],
            "ci_low": pooled["ci_low"],
            "ci_upp": pooled["ci_upp"],
            "is_significant": pooled["ci_low"] > 1 or pooled["ci_upp"] < 1,
        })
    return results


def _plot_path_url(path: Path) -> str:
    try:
        return path.relative_to(MODULE_DIR).as_posix()
    except ValueError:
        # Unit/integration callers may deliberately select an external output
        # root; retain an exact path rather than inventing a misleading URL.
        return str(path)


def _save_placeholder(path: Path, title: str, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axis("off")
    ax.set_title(title, fontweight="bold")
    ax.text(0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center", wrap=True)
    fig.savefig(path, bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def _forest_plot(path: Path, title: str, rows: list[dict[str, Any]], pooled: dict[str, Any]) -> bool:
    if not rows:
        _save_placeholder(path, title, "No eligible subtype-specific estimates were available.")
        return False
    ordered = sorted(rows, key=lambda row: (row["effect_size"], row["study"]))
    records = []
    for row in ordered:
        study = re.sub(r"\s+", " ", str(row["study"])).strip()
        if len(study) > 92:
            study = study[:89].rstrip() + "..."
        records.append({
            "label": study,
            "est": math.log(row["effect_size"]),
            "lb": math.log(row["lower_ci"]),
            "ub": math.log(row["upper_ci"]),
            "Est. RR (95% CI)": (
                f"{row['effect_size']:.2f} ({row['lower_ci']:.2f}, {row['upper_ci']:.2f})"
            ),
        })
    frame = pd.DataFrame.from_records(records)
    n_studies = len(frame)
    dynamic_height = min(18, max(3.8, 0.35 * n_studies + 3.1))
    font_size = 10 if n_studies < 15 else 8 if n_studies < 30 else 6 if n_studies < 60 else 5
    with plt.rc_context({"font.size": font_size}):
        forest_ax = forestplot.forestplot(
            frame,
            estimate="est",
            ll="lb",
            hl="ub",
            varlabel="label",
            rightannote=["Est. RR (95% CI)"],
            right_annoteheaders=["Est. RR (95% CI)"],
            xlabel="Log Relative Risk (95% CI)",
            title=title,
            flush=True,
            color_alt_rows=True,
            figsize=(12, dynamic_height),
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    forest_ax.figure.savefig(path, bbox_inches="tight", metadata={"Date": None})
    plt.close(forest_ax.figure)
    return True


def _funnel_plot(path: Path, title: str, rows: list[dict[str, Any]], pooled: dict[str, Any]) -> tuple[bool, str | None]:
    if not rows:
        _save_placeholder(path, title, "No eligible subtype-specific estimates were available.")
        return False, "no_eligible_studies"
    fig, ax = plt.subplots(figsize=(8, 6))
    x = np.asarray([math.log(row["effect_size"]) for row in rows])
    se = np.asarray([(math.log(row["upper_ci"]) - math.log(row["lower_ci"])) / 3.92 for row in rows])
    ax.scatter(x, se, color="#215a8e", edgecolor="black", alpha=0.75)
    pooled_log = math.log(pooled["pooled_es"])
    ax.axvline(pooled_log, color="#9b1c31", linestyle="--", label="Pooled effect")
    sequence = np.linspace(0, max(se) * 1.1, 100)
    ax.plot(pooled_log - 1.96 * sequence, sequence, "k--", alpha=0.35)
    ax.plot(pooled_log + 1.96 * sequence, sequence, "k--", alpha=0.35)
    ax.set_ylim(max(sequence), 0)
    ax.set_xlabel("Log effect estimate")
    ax.set_ylabel("Standard error")
    if len(rows) >= FORMAL_EGGER_MIN_STUDIES:
        suffix = (
            f"Egger's p={pooled['eggers_p']:.3g}"
            if pooled["eggers_p"] is not None
            else "Egger's test unavailable"
        )
        ax.set_title(f"{title}\n{suffix}")
    else:
        ax.set_title(title)
    ax.grid(alpha=0.2)
    ax.legend(loc="best")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    return True, None if len(rows) >= FORMAL_EGGER_MIN_STUDIES else "egger_requires_10_studies"


def _baujat_plot(path: Path, title: str, rows: list[dict[str, Any]], pooled: dict[str, Any]) -> tuple[bool, str | None]:
    if len(rows) < 3:
        _save_placeholder(path, title, f"Baujat diagnostic requires at least 3 studies; {len(rows)} eligible study/studies available.")
        return False, "baujat_requires_3_studies"
    y = np.asarray([math.log(row["effect_size"]) for row in rows])
    variances = np.asarray([((math.log(row["upper_ci"]) - math.log(row["lower_ci"])) / 3.92) ** 2 for row in rows])
    pooled_log = math.log(pooled["pooled_es"])
    q_contribution = (y - pooled_log) ** 2 / variances
    influence = []
    for index in range(len(rows)):
        subset = rows[:index] + rows[index + 1:]
        subset_pooled = _pool(subset)
        influence.append((pooled_log - math.log(subset_pooled["pooled_es"])) ** 2)
    fig, ax = plt.subplots(figsize=(10, 7), constrained_layout=True)
    ax.scatter(q_contribution, influence, color="#215a8e", edgecolor="black", alpha=0.75)
    x_mid = (float(np.min(q_contribution)) + float(np.max(q_contribution))) / 2
    y_mid = (float(np.min(influence)) + float(np.max(influence))) / 2
    for index, row in enumerate(rows):
        right_side = q_contribution[index] > x_mid
        upper_side = influence[index] > y_mid
        ax.annotate(
            str(row["study"]),
            (q_contribution[index], influence[index]),
            xytext=(-4 if right_side else 4, -4 if upper_side else 4),
            textcoords="offset points",
            ha="right" if right_side else "left",
            va="top" if upper_side else "bottom",
            fontsize=7,
            annotation_clip=False,
        )
    ax.set_xlabel("Contribution to heterogeneity (Q)")
    ax.set_ylabel("Influence on pooled log effect")
    ax.set_title(title)
    ax.grid(alpha=0.2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    return True, None


def _availability(rows: list[dict[str, Any]], funnel_reason: str | None, baujat_reason: str | None) -> dict[str, Any]:
    n = len(rows)
    return {
        "eligible_study_count": n,
        "forest": {"available": n >= 1, "reason": None if n else "forest_requires_1_study"},
        "funnel": {"available": n >= 1, "reason": funnel_reason},
        "baujat": {"available": n >= 3, "reason": baujat_reason},
        "formal_egger": {"available": n >= FORMAL_EGGER_MIN_STUDIES, "reason": None if n >= FORMAL_EGGER_MIN_STUDIES else "egger_requires_10_studies"},
    }


def _compact_study(row: dict[str, Any]) -> dict[str, Any]:
    compact = {key: row.get(key) for key in (
        "context_id", "study", "pmid", "authors", "journal", "year", "reference",
        "effect_size", "lower_ci", "upper_ci", "effect_type", "se", "comparison_type",
        "cases", "sample_size", "exposure_measurement_type",
        "exposure_measurement_supporting_text", "evidence_source", "evidence_locator",
        "outcome_definition", "quality_score", "quality_percent", "jbi",
    )}
    # Preserve the existing frontend contract while retaining normalized keys
    # for machine-readable reuse.
    compact.update({
        "Study": row.get("study"),
        "PMID": row.get("pmid"),
        "Authors": row.get("authors"),
        "Journal": row.get("journal"),
        "Year": row.get("year"),
        "Reference": row.get("reference"),
        "Link": f"https://pubmed.ncbi.nlm.nih.gov/{row.get('pmid')}/" if row.get("pmid") else "",
        "Effect Size": row.get("effect_size"),
        "Lower CI": row.get("lower_ci"),
        "Upper CI": row.get("upper_ci"),
        "Effect Type": row.get("effect_type"),
        "Cases": row.get("cases"),
        "Sample Size": row.get("sample_size"),
        "Participants": row.get("sample_size"),
        "Quality Score": row.get("quality_score"),
        "Quality %": row.get("quality_percent"),
        "JBI": row.get("jbi") or {},
        "exposure_measurement_type": row.get("exposure_measurement_type"),
        "exposure_measurement_supporting_text": row.get(
            "exposure_measurement_supporting_text"
        ),
        "extraction_supporting_text": {
            "effect_size": row.get("evidence_locator") or "",
            "confidence_interval": row.get("evidence_locator") or "",
            "outcome_definition": row.get("outcome_definition") or "",
        },
    })
    return compact


def _input_fingerprint(rows: list[dict[str, Any]]) -> str:
    stable = [{key: row.get(key) for key in sorted(row) if key != "lifetime_risk_percent"} for row in rows]
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=_json_default).encode("utf-8")).hexdigest()


def _classification_audit(payload: Any, annotations_path: Path) -> dict[str, Any]:
    """Summarize current-source coverage and token use without counting stale runs."""
    active_hashes = _active_source_hashes(payload, annotations_path)
    events = payload.get("events", []) if isinstance(payload, dict) else []
    latest: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
    for event in events:
        if not isinstance(event, dict) or event.get("status") != "complete":
            continue
        source_hash = str(event.get("source_hash") or "")
        if active_hashes and source_hash not in active_hashes:
            continue
        key = (str(event.get("pmid") or ""), str(event.get("stage") or ""), source_hash)
        created_at = str(event.get("created_at") or "")
        if key not in latest or created_at >= latest[key][0]:
            latest[key] = (created_at, event)

    by_stage: dict[str, dict[str, Any]] = {}
    classified_pmids: set[str] = set()
    for (pmid, stage, _), (_, event) in latest.items():
        classified_pmids.add(pmid)
        usage = event.get("usage", {}) if isinstance(event.get("usage"), dict) else {}
        stats = by_stage.setdefault(stage, {
            "complete_article_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "gateway_reported_cost_usd": 0.0,
        })
        stats["complete_article_count"] += 1
        for key in ("input_tokens", "output_tokens", "reasoning_tokens"):
            stats[key] += int(usage.get(key) or 0)
        stats["gateway_reported_cost_usd"] += float(usage.get("gateway_reported_cost_usd") or 0.0)
    if "terra" in by_stage:
        by_stage["terra"]["input_price_usd_per_million_tokens"] = TERRA_INPUT_USD_PER_MILLION
        by_stage["terra"]["input_cost_usd"] = (
            by_stage["terra"]["input_tokens"] * TERRA_INPUT_USD_PER_MILLION / 1_000_000
        )
    return {
        "active_saved_article_count": len({
            str(source.get("pmid") or pmid)
            for pmid, source in (
                _read_json(annotations_path.with_name("subcategory_sources.json")).get("sources", {}).items()
                if annotations_path.with_name("subcategory_sources.json").is_file() else []
            )
            if isinstance(source, dict) and str(source.get("source_hash") or "") in active_hashes
        }),
        "classified_article_count": len(classified_pmids),
        "by_stage": by_stage,
    }


def _prune_stale_generated_files(root: Path, expected: set[Path]) -> None:
    """Remove only obsolete files inside an explicitly generated output root."""
    if not root.exists():
        return
    expected_resolved = {path.resolve() for path in expected}
    for path in root.rglob("*"):
        if path.is_file() and path.resolve() not in expected_resolved:
            path.unlink()


def _result_payload(category: dict[str, Any], exposure: str, rows: list[dict[str, Any]], plot_paths: dict[str, Path], pooled: dict[str, Any], skipped_count: int) -> dict[str, Any]:
    forest_ok = bool(rows)
    funnel_ok, funnel_reason = (forest_ok, None if len(rows) >= FORMAL_EGGER_MIN_STUDIES else "egger_requires_10_studies")
    baujat_ok, baujat_reason = (len(rows) >= 3, None if len(rows) >= 3 else "baujat_requires_3_studies")
    headline = dict(pooled)
    headline["loo_results"] = _leave_one_out(rows)
    if pooled.get("pooled_es") is not None:
        direction = "lower" if pooled["pooled_es"] < 1 else "higher"
        headline.update({
            "interpretation": (
                f"The pooled subtype-specific estimate is {pooled['pooled_es']:.2f}, "
                f"indicating a {direction} relative association for this exposure."
            ),
            "funnel_interpretation": (
                f"Formal Egger's testing requires at least {FORMAL_EGGER_MIN_STUDIES} eligible studies."
                if len(rows) < FORMAL_EGGER_MIN_STUDIES
                else (
                    f"Egger's test p-value: {pooled['eggers_p']:.3g}."
                    if pooled.get("eggers_p") is not None
                    else "Egger's test could not be estimated from the available studies."
                )
            ),
            "results_interpretation": (
                f"This saved analysis contains {len(rows)} separately reported "
                f"{category['label']} estimate{'s' if len(rows) != 1 else ''}."
            ),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "major_site_id": category["major_site_id"],
            "subcategory_id": category["subcategory_id"],
            "subcategory_slug": category["subcategory_slug"],
            "subcategory_label": category["label"],
            # Metadata only; not a pooling input or an aggregate total.
            "estimated_lifetime_probability_us_women_percent": category["estimated_lifetime_probability_us_women_percent"],
        },
        "exposure": exposure,
        "studies": [_compact_study(row) for row in rows],
        "headline": headline,
        "availability": _availability(rows, funnel_reason, baujat_reason),
        "plot_urls": {name: _plot_path_url(path) for name, path in plot_paths.items()},
        "plot_url": _plot_path_url(plot_paths["forest"]),
        "funnel_plot_url": _plot_path_url(plot_paths["funnel"]),
        "baujat_plot_url": _plot_path_url(plot_paths["baujat"]),
        "input_fingerprint": _input_fingerprint(rows),
        "skipped_annotation_count_for_build": skipped_count,
    }


def _summary_total(studies: list[dict[str, Any]], key: str) -> int | None:
    values = []
    for study in studies:
        value = _as_float(study.get(key))
        if value is not None and value >= 0:
            values.append(value)
    return int(round(sum(values))) if values else None


def _pretty_exposure(value: str) -> str:
    label = re.sub(r"[_-]+", " ", str(value)).title()
    return label.replace("Bcaas", "BCAAs").replace("Beta Carotene", "beta-Carotene")


def _summary_translation_lookup() -> dict[str, dict[str, str]]:
    """Index display translations without changing canonical exposure values."""
    global _SUMMARY_TRANSLATION_LOOKUP
    if _SUMMARY_TRANSLATION_LOOKUP is not None:
        return _SUMMARY_TRANSLATION_LOOKUP
    lookup: dict[str, dict[str, str]] = {}
    try:
        catalog = _read_json(SUMMARY_TRANSLATIONS)
    except (OSError, json.JSONDecodeError):
        catalog = {}
    if isinstance(catalog, dict):
        for source, translations in catalog.items():
            if not isinstance(translations, dict):
                continue
            localized = {
                locale: str(translations.get(locale) or "").strip()
                for locale in SUMMARY_PLOT_LOCALES
            }
            lookup[slugify(source)] = localized
    _SUMMARY_TRANSLATION_LOOKUP = lookup
    return lookup


def _localized_exposure(value: str, locale: str | None = None) -> str:
    if locale not in SUMMARY_PLOT_LOCALES:
        return _pretty_exposure(value)
    translation = _summary_translation_lookup().get(slugify(value), {}).get(locale)
    if not translation:
        raise ValueError(
            f"Missing Summary exposure translation for {value!r} (locale {locale})."
        )
    return translation


def _summary_font_family(locale: str | None) -> str | None:
    """Choose an installed CJK font for localized exposure labels when possible."""
    if locale not in ("zh-CN", "zh-TW", "ko"):
        return None
    if locale in _SUMMARY_FONT_FAMILIES:
        return _SUMMARY_FONT_FAMILIES[locale]
    candidates = {
        "zh-CN": (
            "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "PingFang SC",
            "Microsoft YaHei", "SimHei", "Arial Unicode MS", "Noto Sans CJK TC",
            "Noto Sans CJK JP",
        ),
        "zh-TW": (
            "Noto Sans CJK TC", "Noto Sans TC", "Source Han Sans TC", "PingFang TC",
            "Microsoft JhengHei", "Heiti TC", "Arial Unicode MS", "Noto Sans CJK SC",
            "Noto Sans CJK JP",
        ),
        "ko": (
            "Noto Sans CJK KR", "Noto Sans KR", "Source Han Sans K", "Apple SD Gothic Neo",
            "Malgun Gothic", "Arial Unicode MS", "Noto Sans CJK JP",
        ),
    }
    installed = {
        font.name.casefold(): font.name
        for font in sorted(font_manager.fontManager.ttflist, key=lambda item: (item.name, item.fname))
    }
    family = next(
        (installed[name.casefold()] for name in candidates[locale] if name.casefold() in installed),
        None,
    )
    if family is None:
        # Distribution-specific family names sometimes add a style suffix.
        markers = (
            "noto sans cjk", "noto sans sc", "noto sans tc", "noto sans kr",
            "source han sans", "pingfang", "apple sd gothic", "malgun gothic",
        )
        family = next(
            (name for key, name in installed.items() if any(marker in key for marker in markers)),
            None,
        )
    _SUMMARY_FONT_FAMILIES[locale] = family
    return family


def _localized_summary_plot_paths(plot_paths: dict[str, Path], locale: str) -> dict[str, Path]:
    return {
        name: path.parent / "locales" / locale / path.name
        for name, path in plot_paths.items()
    }


def _summary_forest_height(total_rows: int) -> float:
    """Return a bounded figure height proportional to displayed plot rows."""
    height_mm = max(105.0, min(420.0, 80.0 + 12.0 * total_rows))
    return height_mm / 25.4


def _cross_exposure_forest(
    path: Path,
    title: str,
    entries: list[dict[str, Any]],
    direction: str,
    cancer_label: str,
    locale: str | None = None,
) -> None:
    if not entries:
        _save_placeholder(path, title, "No exposure met the eligibility rule for this summary panel.")
        return
    prepared = []
    for entry in entries:
        exposure_slug = slugify(entry["exposure"])
        group = EXPOSURE_GROUPS.get(exposure_slug, "Other")
        studies = entry.get("studies", [])
        headline = entry["headline"]
        prepared.append({
            "entry": entry,
            "exposure": _localized_exposure(entry["exposure"], locale),
            "group": group,
            "n_studies": int(headline["n_studies"]),
            "total_n": _summary_total(studies, "sample_size"),
            "cases": _summary_total(studies, "cases"),
            "effect": float(headline["pooled_es"]),
            "low": float(headline["ci_low"]),
            "high": float(headline["ci_upp"]),
        })
    group_rank = {group: index for index, group in enumerate(EXPOSURE_GROUP_ORDER)}
    prepared.sort(key=lambda item: (group_rank.get(item["group"], 999), item["effect"], item["exposure"]))

    plot_rows: list[dict[str, Any]] = []
    row_number = 1
    groups_present = []
    for group in EXPOSURE_GROUP_ORDER:
        group_items = [item for item in prepared if item["group"] == group]
        if not group_items:
            continue
        groups_present.append(group)
        plot_rows.append({
            "kind": "group",
            "group": group,
            "group_label": _localized_exposure(group, locale),
            "y": row_number,
        })
        row_number += 1
        for item in group_items:
            plot_rows.append({**item, "kind": "exposure", "y": row_number})
            row_number += 1
    total_rows = row_number - 1
    exposure_font = _summary_font_family(locale)
    exposure_font_args = {"fontfamily": exposure_font} if exposure_font else {}

    fig, (table_ax, forest_ax) = plt.subplots(
        1,
        2,
        figsize=(11.69, _summary_forest_height(total_rows)),
        gridspec_kw={"width_ratios": [1.55, 1]},
    )
    fig.subplots_adjust(left=0.035, right=0.985, top=0.91, bottom=0.18, wspace=0.01)
    fig.suptitle(title, fontsize=13, fontweight="bold", color="#1A1A2E", y=0.965)

    table_ax.set_xlim(-0.05, 4.8)
    table_ax.set_ylim(total_rows + 0.6, -0.65)
    table_ax.axis("off")
    for row in plot_rows:
        group = row["group"]
        alpha = 0.70 if row["kind"] == "group" else 0.30
        table_ax.add_patch(Rectangle(
            (-0.05, row["y"] - 0.5), 4.8, 1.0,
            facecolor=EXPOSURE_GROUP_BACKGROUNDS[group], alpha=alpha, linewidth=0,
        ))
        if row["kind"] == "group":
            table_ax.text(0.0, row["y"], row["group_label"].upper(), ha="left", va="center",
                          fontsize=8.5, fontweight="bold", fontstyle="italic",
                          color=EXPOSURE_GROUP_COLORS[group], **exposure_font_args)
            continue
        color = EXPOSURE_GROUP_COLORS[group]
        table_ax.text(0.15, row["y"], row["exposure"], ha="left", va="center",
                      fontsize=9, fontweight="bold", color=color, **exposure_font_args)
        table_ax.text(1.2, row["y"], str(row["n_studies"]), ha="center", va="center", fontsize=8.5, color=color)
        table_ax.text(2.4, row["y"], f"{row['total_n']:,}" if row["total_n"] is not None else "-",
                      ha="right", va="center", fontsize=8.5, color=color)
        table_ax.text(3.5, row["y"], f"{row['cases']:,}" if row["cases"] is not None else "-",
                      ha="right", va="center", fontsize=8.5, color=color)
        table_ax.text(4.7, row["y"], f"{row['effect']:.2f} ({row['low']:.2f}-{row['high']:.2f})",
                      ha="right", va="center", fontsize=8.2, fontstyle="italic", color=color)
    for y_line in np.arange(0.5, total_rows + 0.6, 1):
        table_ax.axhline(y_line, color="white", linewidth=0.6)
    table_ax.add_patch(Rectangle((-0.05, -0.60), 4.8, 1.1, facecolor="#1A1A2E", alpha=0.93, linewidth=0))
    for x, label, align in ((0.0, "Exposure", "left"), (1.2, "# of studies", "center"),
                            (2.4, "Sample size", "right"), (3.5, "Cases", "right"),
                            (4.7, "Pooled RR (95% CI)", "right")):
        table_ax.text(x, 0, label, ha=align, va="center", fontsize=9.2, fontweight="bold", color="white")

    x_min, x_max = (0.15, 2.2) if direction == "Protective" else (0.15, 4.5)
    forest_ax.set_xscale("log")
    forest_ax.set_xlim(x_min, x_max)
    forest_ax.set_ylim(total_rows + 0.6, -0.65)
    for row in plot_rows:
        group = row["group"]
        alpha = 0.65 if row["kind"] == "group" else 0.28
        forest_ax.add_patch(Rectangle(
            (x_min, row["y"] - 0.5), x_max - x_min, 1.0,
            facecolor=EXPOSURE_GROUP_BACKGROUNDS[group], alpha=alpha, linewidth=0,
        ))
    ticks = [value for value in (0.2, 0.25, 0.5, 1, 2, 4) if x_min <= value <= x_max]
    for tick in ticks:
        if tick != 1:
            forest_ax.axvline(tick, color="#BDBDBD", linewidth=0.5, linestyle=":", zorder=1)
    forest_ax.axvline(1, color="#1A1A2E", linewidth=0.9, linestyle="--", zorder=2)
    for y_line in np.arange(0.5, total_rows + 0.6, 1):
        forest_ax.axhline(y_line, color="white", linewidth=0.6, zorder=1)
    for row in (item for item in plot_rows if item["kind"] == "exposure"):
        color = EXPOSURE_GROUP_COLORS[row["group"]]
        low, high = max(row["low"], x_min), min(row["high"], x_max)
        forest_ax.plot([low, high], [row["y"], row["y"]], color=color, linewidth=1.6,
                       solid_capstyle="round", zorder=3)
        if row["low"] >= x_min:
            forest_ax.plot([row["low"], row["low"]], [row["y"] - 0.18, row["y"] + 0.18],
                           color=color, linewidth=1.0, zorder=3)
        if row["high"] <= x_max:
            forest_ax.plot([row["high"], row["high"]], [row["y"] - 0.18, row["y"] + 0.18],
                           color=color, linewidth=1.0, zorder=3)
        significant = row["high"] < 1 or row["low"] > 1
        forest_ax.scatter(
            row["effect"], row["y"], marker="D",
            s=36 + min(row["n_studies"], 15) * 9,
            facecolor=color, edgecolor="#CC0000" if significant else color,
            linewidth=1.2 if significant else 0.5,
            alpha=1.0 if significant else 0.38, zorder=4,
        )
    forest_ax.add_patch(Rectangle((x_min, -0.60), x_max - x_min, 1.1,
                                  facecolor="#1A1A2E", alpha=0.93, linewidth=0, zorder=5))
    forest_ax.text(1, 0, "Effect size", ha="center", va="center", fontsize=9.2,
                   fontweight="bold", color="white", zorder=6)
    forest_ax.set_xticks(ticks)
    forest_ax.set_xticklabels([str(tick) for tick in ticks], fontsize=9, fontweight="bold", color="#37474F")
    forest_ax.minorticks_off()
    forest_ax.set_yticks([])
    forest_ax.set_xlabel("Pooled RR", fontsize=10, color="#37474F")
    for spine_name in ("top", "right", "left"):
        forest_ax.spines[spine_name].set_visible(False)
    forest_ax.spines["bottom"].set_color("#B0BEC5")

    handles = [Line2D([0], [0], marker="s", linestyle="", markersize=7,
                      markerfacecolor=EXPOSURE_GROUP_COLORS[group], markeredgecolor="none",
                      label=_localized_exposure(group, locale))
               for group in groups_present]
    legend = fig.legend(
        handles=handles, loc="lower left", bbox_to_anchor=(0.035, 0.085),
        ncol=min(4, len(handles)), frameon=False, title="Exposure group",
        fontsize=8, title_fontsize=9,
    )
    if exposure_font:
        for label in legend.get_texts():
            label.set_fontfamily(exposure_font)
        legend.get_title().set_fontfamily(exposure_font)
    side = (
        f"RR < 1 = inversely associated with {cancer_label} risk."
        if direction == "Protective"
        else f"RR > 1 = positively associated with {cancer_label} risk."
    )
    fig.text(
        0.04, 0.035,
        side + "  |  diamond = pooled RR (size proportional to # of studies)  |  "
        "red outline = statistically significant (95% CI excludes 1.0)  |  faded = non-significant",
        ha="left", va="bottom", fontsize=7.2, color="#607D8B", fontstyle="italic",
    )
    fig.patch.set_facecolor("white")
    fig.add_artist(Rectangle((0.005, 0.005), 0.99, 0.99, transform=fig.transFigure,
                             fill=False, edgecolor="#B0BEC5", linewidth=0.8))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def _diagnostic_plot(
    path: Path,
    title: str,
    entries: list[dict[str, Any]],
    x_key: str,
    x_label: str,
    locale: str | None = None,
) -> None:
    usable = [
        entry for entry in entries
        if entry["headline"].get(x_key) is not None
        and entry["headline"].get("i2") is not None
        and entry["headline"]["i2"] > 0
    ]
    if not usable:
        _save_placeholder(path, title, "No exposure had sufficient eligible studies for this diagnostic.")
        return
    fig, ax = plt.subplots(figsize=(8, 6))
    x = [entry["headline"][x_key] for entry in usable]
    y = [entry["headline"]["i2"] for entry in usable]
    ax.scatter(x, y, color="#215a8e", edgecolor="black", alpha=0.75)
    x_mid = (min(x) + max(x)) / 2 if len(x) > 1 else x[0]
    label_offsets = (5, 15, 25, -10)
    exposure_font = _summary_font_family(locale)
    exposure_font_args = {"fontfamily": exposure_font} if exposure_font else {}
    for index, entry in enumerate(sorted(
        usable, key=lambda item: (item["headline"]["i2"], item["headline"][x_key], item["exposure"])
    )):
        x_value = entry["headline"][x_key]
        y_value = entry["headline"]["i2"]
        right_side = x_value > x_mid
        ax.annotate(
            _localized_exposure(entry["exposure"], locale)[:28],
            (x_value, y_value),
            xytext=(-4 if right_side else 4, label_offsets[index % len(label_offsets)]),
            textcoords="offset points",
            ha="right" if right_side else "left",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            **exposure_font_args,
        )
    ax.set_xlabel(x_label, fontsize=13, fontweight="bold")
    ax.set_ylabel("I² (%)", fontsize=13, fontweight="bold")
    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.tick_params(axis="both", labelsize=12)
    for tick_label in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        tick_label.set_fontweight("bold")
    ax.grid(alpha=0.2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def _render_summary_plot_set(
    plot_paths: dict[str, Path],
    category: dict[str, Any],
    protective: list[dict[str, Any]],
    harmful: list[dict[str, Any]],
    diagnostic_eligible: list[dict[str, Any]],
    egger_heterogeneity_eligible: list[dict[str, Any]],
    locale: str | None = None,
) -> None:
    _cross_exposure_forest(
        plot_paths["forest_protective"],
        f"Exposures inversely associated with {category['label']} risk",
        protective,
        "Protective",
        category["label"],
        locale=locale,
    )
    _cross_exposure_forest(
        plot_paths["forest_harmful"],
        f"Exposures positively associated with {category['label']} risk",
        harmful,
        "Harmful",
        category["label"],
        locale=locale,
    )
    _diagnostic_plot(
        plot_paths["effect_heterogeneity"],
        "Effect estimate vs heterogeneity",
        diagnostic_eligible,
        "pooled_es",
        "Pooled effect estimate",
        locale=locale,
    )
    _diagnostic_plot(
        plot_paths["egger_heterogeneity"],
        "Egger's p-value vs heterogeneity",
        egger_heterogeneity_eligible,
        "eggers_p",
        "Egger's p-value",
        locale=locale,
    )


def _summary_outputs(category: dict[str, Any], entries: list[dict[str, Any]], plot_root: Path) -> dict[str, Any]:
    folder = plot_root / category["major_site_id"] / category["subcategory_slug"]
    plot_paths = {
        "forest_protective": folder / "forest_protective.pdf",
        "forest_harmful": folder / "forest_harmful.pdf",
        "effect_heterogeneity": folder / "effect_size_vs_i2.pdf",
        "egger_heterogeneity": folder / "egger_vs_i2.pdf",
    }
    eligible = [entry for entry in entries if entry["headline"].get("pooled_es") is not None]
    diagnostic_eligible = [
        entry for entry in eligible
        if entry["headline"].get("n_studies", 0) >= 3
        and entry["headline"].get("i2") is not None
        and entry["headline"]["i2"] > 0
    ]
    forest_eligible = [entry for entry in eligible if entry["headline"].get("n_studies", 0) > 1]
    protective = [entry for entry in forest_eligible if entry["headline"]["pooled_es"] < 1]
    harmful = [entry for entry in forest_eligible if entry["headline"]["pooled_es"] >= 1]
    egger_heterogeneity_eligible = [
        entry for entry in diagnostic_eligible
        if entry["headline"].get("eggers_p") is not None
    ]
    formal_egger = [entry for entry in eligible if entry["availability"]["formal_egger"]["available"]]
    # Direction uses the pooled point estimate. This mirrors the summary's
    # visual grouping and does not assert statistical significance.
    _render_summary_plot_set(
        plot_paths,
        category,
        protective,
        harmful,
        diagnostic_eligible,
        egger_heterogeneity_eligible,
    )
    for locale in SUMMARY_PLOT_LOCALES:
        _render_summary_plot_set(
            _localized_summary_plot_paths(plot_paths, locale),
            category,
            protective,
            harmful,
            diagnostic_eligible,
            egger_heterogeneity_eligible,
            locale=locale,
        )
    plot_metadata = {
        "forest-protective": {"path": _plot_path_url(plot_paths["forest_protective"]), "filename": plot_paths["forest_protective"].name, "available": bool(protective), "reason": None if protective else "no_protective_eligible_exposures"},
        "forest-harmful": {"path": _plot_path_url(plot_paths["forest_harmful"]), "filename": plot_paths["forest_harmful"].name, "available": bool(harmful), "reason": None if harmful else "no_harmful_eligible_exposures"},
        "effect-heterogeneity": {"path": _plot_path_url(plot_paths["effect_heterogeneity"]), "filename": plot_paths["effect_heterogeneity"].name, "available": len(diagnostic_eligible) >= 2, "reason": None if len(diagnostic_eligible) >= 2 else "requires_2_eligible_exposures"},
        "egger-heterogeneity": {"path": _plot_path_url(plot_paths["egger_heterogeneity"]), "filename": plot_paths["egger_heterogeneity"].name, "available": len(egger_heterogeneity_eligible) >= 2, "reason": None if len(egger_heterogeneity_eligible) >= 2 else "requires_2_eligible_exposures"},
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope": {key: category[key] for key in ("major_site_id", "subcategory_id", "subcategory_slug", "label", "estimated_lifetime_probability_us_women_percent")},
        "exposure_count": len(entries),
        "eligible_exposure_count": len(eligible),
        "formal_egger_exposure_count": len(formal_egger),
        "plots": plot_metadata,
        "exposures": [{"exposure": entry["exposure"], "headline": entry["headline"], "availability": entry["availability"]} for entry in sorted(entries, key=lambda item: slugify(item["exposure"]))],
        "notes": [
            "Lifetime-risk percent is taxonomy metadata only and is not pooled or aggregated.",
            "Protective/harmful grouping is by the pooled point estimate relative to 1.0.",
            "Summary forest plots follow the broad-cancer format and require at least 2 studies per exposure.",
            "Cross-exposure heterogeneity plots require at least 3 studies and I² greater than 0% per exposure.",
            f"Formal per-exposure Egger interpretation requires at least {FORMAL_EGGER_MIN_STUDIES} studies.",
        ],
    }
    _write_json(folder / "summary_manifest.json", manifest)
    return manifest


def build_subcategory_outputs(
    annotations_path: Path | str = DEFAULT_ANNOTATIONS,
    results_root: Path | str = DEFAULT_RESULTS_ROOT,
    plot_root: Path | str = DEFAULT_PLOT_ROOT,
    registry_csv: Path | str = DEFAULT_REGISTRY_CSV,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
) -> dict[str, Any]:
    """Build isolated subtype results and plots from saved annotation data.

    The function is deliberately idempotent: paths, ordering, numeric
    calculations, and JSON serialisation are deterministic.  It is also safe
    to rerun after a partial build because every artifact is independently
    recreated and failures are represented in result metadata rather than by
    emitting empty/broken images.
    """
    annotations_path, results_root, plot_root, registry_csv, cache_root = map(
        Path, (annotations_path, results_root, plot_root, registry_csv, cache_root)
    )
    if not annotations_path.is_file():
        raise FileNotFoundError(f"Saved subtype annotations were not found: {annotations_path}")
    registry = _normalize_registry(_registry_records(registry_csv))
    rows, skipped = extract_eligible_rows(
        annotations_path, registry, _cached_study_metadata(cache_root)
    )
    by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[(row["major_site_id"], row["subcategory_id"], row["exposure"])].append(row)

    # Include every registry subtype represented in an annotation, including
    # those with zero eligible estimates, so availability is explicit.
    represented: set[tuple[str, str]] = set()
    requested_groups: set[tuple[str, str, str]] = set()
    payload = _read_json(annotations_path)
    contexts = _extract_contexts(payload, annotations_path)
    active_source_hashes = _active_source_hashes(payload, annotations_path)
    for annotation in _extract_annotations(payload, active_source_hashes):
        for major in _major_outcomes(annotation):
            for subtype in _subtype_outcomes(major):
                category_id = str(_first(subtype, "subcategory_id", "category_id", "id") or "")
                if category_id in registry:
                    represented.add((registry[category_id]["major_site_id"], category_id))
                    for estimate_item in _estimate_items(annotation, subtype):
                        context_id = _context_id(estimate_item) or _context_id(annotation)
                        context = contexts.get(context_id or "")
                        source = _study_source(context) if context else {}
                        exposure = _exposure(context or {}, annotation, source)
                        if context and exposure:
                            requested_groups.add((registry[category_id]["major_site_id"], category_id, exposure))
    category_entries: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    expected_result_files: set[Path] = set()
    expected_plot_files: set[Path] = set()
    for major, category_id, exposure in sorted(requested_groups | set(by_group), key=lambda item: (item[0], registry[item[1]]["subcategory_slug"], slugify(item[2]))):
        category = registry[category_id]
        group_rows = by_group.get((major, category_id, exposure), [])
        pooled = _pool(group_rows)
        base = plot_root / major / category["subcategory_slug"]
        exposure_slug = slugify(exposure)
        plot_paths = {"forest": base / f"{exposure_slug}_forest.png", "funnel": base / f"{exposure_slug}_funnel.png", "baujat": base / f"{exposure_slug}_baujat.png"}
        _forest_plot(plot_paths["forest"], f"Forest plot: {category['label']} vs {exposure}", group_rows, pooled)
        _, funnel_reason = _funnel_plot(plot_paths["funnel"], f"Funnel plot: {category['label']} vs {exposure}", group_rows, pooled)
        _, baujat_reason = _baujat_plot(plot_paths["baujat"], f"Baujat plot: {category['label']} vs {exposure}", group_rows, pooled)
        payload_out = _result_payload(category, exposure, group_rows, plot_paths, pooled, len(skipped))
        payload_out["availability"] = _availability(group_rows, funnel_reason, baujat_reason)
        output_path = results_root / major / category["subcategory_slug"] / f"{exposure_slug}.json"
        _write_json(output_path, payload_out)
        expected_result_files.add(output_path)
        expected_plot_files.update(plot_paths.values())
        category_entries[(major, category_id)].append(payload_out)

    summaries = {}
    for major, category_id in sorted(represented, key=lambda item: (item[0], registry[item[1]]["subcategory_slug"])):
        category = registry[category_id]
        summaries[f"{major}/{category['subcategory_slug']}"] = _summary_outputs(category, category_entries[(major, category_id)], plot_root)
        summary_folder = plot_root / major / category["subcategory_slug"]
        expected_plot_files.update({
            summary_folder / "forest_protective.pdf",
            summary_folder / "forest_harmful.pdf",
            summary_folder / "effect_size_vs_i2.pdf",
            summary_folder / "egger_vs_i2.pdf",
            summary_folder / "summary_manifest.json",
        })
        for locale in SUMMARY_PLOT_LOCALES:
            locale_folder = summary_folder / "locales" / locale
            expected_plot_files.update({
                locale_folder / "forest_protective.pdf",
                locale_folder / "forest_harmful.pdf",
                locale_folder / "effect_size_vs_i2.pdf",
                locale_folder / "egger_vs_i2.pdf",
            })
    ui_summary_manifest: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "scopes": {}}
    for summary in summaries.values():
        scope = summary["scope"]
        major = scope["major_site_id"]
        ui_major = ui_summary_manifest["scopes"].setdefault(major, {"subcategories": {}})
        ui_major["subcategories"][scope["subcategory_slug"]] = {
            "subcategory_id": scope["subcategory_id"],
            "label": scope["label"],
            "estimated_lifetime_probability_us_women_percent": scope["estimated_lifetime_probability_us_women_percent"],
            "plots": summary["plots"],
            "availability": {
                "eligible_exposure_count": summary["eligible_exposure_count"],
                "formal_egger_exposure_count": summary["formal_egger_exposure_count"],
            },
        }
    summary_manifest_path = plot_root / "summary_manifest.json"
    build_manifest_path = plot_root / "build_manifest.json"
    expected_plot_files.update({summary_manifest_path, build_manifest_path})
    _write_json(summary_manifest_path, ui_summary_manifest)
    build_manifest = {
        "schema_version": SCHEMA_VERSION,
        "annotations_path": str(annotations_path),
        "result_count": sum(len(values) for values in category_entries.values()),
        "eligible_estimate_count": len(rows),
        "skipped_annotations": skipped,
        "classification_audit": _classification_audit(payload, annotations_path),
        "summaries": summaries,
        "summary_manifest": _plot_path_url(plot_root / "summary_manifest.json"),
        "notes": ["No major-cancer cache was read or modified.", "No network or LLM operation was performed."],
    }
    _prune_stale_generated_files(results_root, expected_result_files)
    _prune_stale_generated_files(plot_root, expected_plot_files)
    _write_json(build_manifest_path, build_manifest)
    return build_manifest
