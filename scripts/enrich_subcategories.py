#!/usr/bin/env python3
"""Resumable saved-study enrichment for cancer subcategories.

This script intentionally never writes ``Cached_results`` and never uses ESearch.
Its only NCBI operations are batched PubMed EFetch for already-saved PMIDs and
PMC EFetch for the narrow Luna fallback described in the annotation ledger.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from subcategory_registry import MAJOR_DISEASE_BY_SITE_ID, REGISTRY, stable_id  # noqa: E402

CACHE_DIR = REPO_ROOT / "Cached_results"
EXPOSURES_FILE = REPO_ROOT / "static" / "exposures.json"
DATA_DIR = REPO_ROOT / "data"
SYNONYMS_FILE = DATA_DIR / "synonyms_cache.json"
SOURCES_PATH = DATA_DIR / "subcategory_sources.json"
ANNOTATIONS_PATH = DATA_DIR / "subcategory_annotations.json"
FULL_TEXT_DIR = DATA_DIR / "subcategory_full_text"
TERRA_MODEL = "gpt-5.6-terra"
LUNA_MODEL = "gpt-5.6-luna"
TERRA_INPUT_USD_PER_MILLION = 2.0
SCHEMA_VERSION = 1
WRITE_LOCK = threading.Lock()

VALID_STATUSES = {
    "reported_separate_estimate",
    "reported_no_separate_estimate",
    "unclear_needs_full_text",
}
REQUIRED_NUMERIC_ESTIMATE_FIELDS = ("effect_size", "lower_ci", "upper_ci")
OPTIONAL_NUMERIC_ESTIMATE_FIELDS = ("cases", "sample_size")

TERRA_SYSTEM = """You classify cancer outcomes in systematic-review article abstracts. Use only supplied text. Return valid JSON only; never infer histology from a general cancer label."""
LUNA_SYSTEM = """You extract cancer-subcategory outcomes from supplied full article text for a systematic review. Use only supplied text. Return valid JSON only; never infer histology from a general cancer label."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)


def safe_path_component(value: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(value).lower()).strip("_")


def canonical_exposure_name(exposure: str) -> str:
    """Replicate the cache-name portion of ``meta_analysis.get_canonical_name``."""
    lowered = exposure.lower().strip()
    synonyms = read_json(SYNONYMS_FILE, {})
    if isinstance(synonyms, dict):
        for canonical, terms in synonyms.items():
            if canonical.lower().strip() == lowered:
                return canonical
            if isinstance(terms, dict) and lowered in {term.strip().lower() for term in str(terms.get("core") or "").split(",")}:
                return canonical
    return exposure


def cache_candidates(exposure: str, disease: str) -> Iterable[Path]:
    """Mirror app.py's active UI lookup: true/exclude-meta, gpt-4o, core then all."""
    canonical = canonical_exposure_name(exposure)
    exposure_dir = CACHE_DIR / safe_path_component(canonical)
    model_priority = ("openai.gpt-4o", "anthropic.claude-4.5-sonnet", "openai.gpt-5.4-pro", "google.gemini-2.5-pro", "google.gemini-2.5-flash", "google.gemini-2.0-flash")
    for use_downstream in (False, True):
        suffix = "all" if use_downstream else "core"
        for model in model_priority:
            # This is app.py's legacy/default cache-tag behaviour.
            model_tag = "" if model in {"openai.gpt-4o", "anthropic.claude-4.5-sonnet"} else f"_{safe_path_component(model)}"
            yield exposure_dir / f"{safe_path_component(f'{disease}_Incidence_True_{suffix}{model_tag}')}.json"


def build_live_contexts(exposures_path: Path = EXPOSURES_FILE) -> dict[str, dict[str, Any]]:
    """Build exactly the cache records reachable by the public default UI.

    Like ``app.py``, each exposure/site uses the first hit (core before all) and
    does not merge both cache variants.  The cache data itself is never changed.
    """
    exposures = read_json(exposures_path, [])
    if not isinstance(exposures, list):
        raise ValueError("static/exposures.json must be a list")
    contexts: dict[str, dict[str, Any]] = {}
    selected_cache_paths: set[Path] = set()
    for exposure in exposures:
        if not isinstance(exposure, str) or not exposure.strip():
            continue
        canonical_exposure = canonical_exposure_name(exposure)
        exposure_id = stable_id(canonical_exposure)
        for major_site_id, disease in MAJOR_DISEASE_BY_SITE_ID.items():
            chosen = next((path for path in cache_candidates(exposure, disease) if path.exists()), None)
            if chosen is None or chosen in selected_cache_paths:
                continue
            selected_cache_paths.add(chosen)
            packet = read_json(chosen, {})
            studies = packet.get("studies", []) if isinstance(packet, dict) else []
            seen_per_pmid: defaultdict[str, int] = defaultdict(int)
            for study in studies:
                if not isinstance(study, dict) or not str(study.get("PMID") or "").strip():
                    continue
                pmid = str(study["PMID"]).strip()
                ordinal = seen_per_pmid[pmid]
                seen_per_pmid[pmid] += 1
                context_id = f"{pmid}|{major_site_id}|{exposure_id}|{ordinal}"
                if context_id in contexts:
                    raise ValueError(f"Duplicate live context ID: {context_id}")
                contexts[context_id] = {
                    "context_id": context_id,
                    "pmid": pmid,
                    "major_site_id": major_site_id,
                    "major_disease": disease,
                    "exposure": canonical_exposure,
                    "cache_path": str(chosen.relative_to(REPO_ROOT)),
                    "cached_study": study,
                }
    return contexts


def contexts_by_pmid(contexts: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for context in contexts.values():
        grouped[context["pmid"]].append(context)
    return dict(grouped)


def source_packet() -> dict[str, Any]:
    value = read_json(SOURCES_PATH, {})
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return {"schema_version": SCHEMA_VERSION, "updated_at": None, "context_index": {}, "sources": {}}
    value.setdefault("sources", {})
    value.setdefault("context_index", {})
    return value


def annotation_packet() -> dict[str, Any]:
    value = read_json(ANNOTATIONS_PATH, {})
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return {"schema_version": SCHEMA_VERSION, "events": []}
    value.setdefault("events", [])
    return value


def configure_ncbi() -> Any:
    """Configure EFetch only. Do not validate keys because validation uses ESearch."""
    from Bio import Entrez
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / "mykey.env", override=True)
    Entrez.email = os.getenv("NCBI_EMAIL") or os.getenv("PUBMED_EMAIL")
    Entrez.api_key = os.getenv("NCBI_API_KEY") or os.getenv("PUBMED_API_KEY") or None
    if not Entrez.email:
        raise RuntimeError("NCBI_EMAIL (or PUBMED_EMAIL) must be configured for EFetch")
    return Entrez


def xml_text(node: ET.Element | None) -> str:
    return " ".join(part.strip() for part in (node.itertext() if node is not None else []) if part.strip())


def parse_pubmed_xml(xml_bytes: bytes) -> dict[str, dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    parsed: dict[str, dict[str, str]] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = xml_text(article.find("./MedlineCitation/PMID"))
        if not pmid:
            continue
        abstract_nodes = article.findall("./MedlineCitation/Article/Abstract/AbstractText")
        abstract = "\n".join(xml_text(node) for node in abstract_nodes if xml_text(node))
        pmcid = ""
        for identifier in article.findall("./PubmedData/ArticleIdList/ArticleId"):
            if identifier.attrib.get("IdType", "").lower() == "pmc":
                pmcid = xml_text(identifier)
                break
        parsed[pmid] = {
            "pmid": pmid,
            "pmcid": pmcid,
            "title": xml_text(article.find("./MedlineCitation/Article/ArticleTitle")),
            "abstract": abstract,
        }
    return parsed


def fetch_sources(pmids: list[str], dry_run: bool = False, batch_size: int = 100, max_items: int | None = None) -> dict[str, int]:
    """EFetch only missing saved PMIDs and atomically checkpoint every batch."""
    contexts = build_live_contexts()
    live = contexts_by_pmid(contexts)
    selected = [pmid for pmid in sorted(live) if pmid in set(pmids)]
    if max_items is not None:
        selected = selected[:max_items]
    packet = source_packet()
    # A source is immutable PubMed content, while its saved-study contexts can
    # evolve.  Persist the current context index without another NCBI request.
    live_index = {context_id: compact_context(context) for context_id, context in contexts.items()}
    for pmid, source in packet["sources"].items():
        if pmid not in live:
            continue
        source["contexts"] = sorted(context["context_id"] for context in live[pmid])
        source["context_hash"] = canonical_json_hash([live_index[item] for item in source["contexts"]])
        source["source_hash"] = canonical_json_hash({
            "pmid": source.get("pmid"), "pmcid": source.get("pmcid"), "title": source.get("title"),
            "abstract": source.get("abstract"), "contexts": source["contexts"], "context_hash": source["context_hash"],
        })
    packet["context_index"] = live_index
    pending = [pmid for pmid in selected if packet["sources"].get(pmid, {}).get("fetch_status") != "complete"]
    if dry_run:
        return {"live_pmids": len(selected), "pending": len(pending), "fetched": 0}
    if not pending:
        packet["updated_at"] = utc_now()
        atomic_json_write(SOURCES_PATH, packet)
        return {"live_pmids": len(selected), "pending": 0, "fetched": 0}
    entrez = configure_ncbi()
    fetched = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with entrez.efetch(db="pubmed", id=",".join(batch), retmode="xml") as handle:
                    records = parse_pubmed_xml(handle.read())
                last_error = None
                break
            except Exception as exc:  # network errors are checkpointed below
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        for pmid in batch:
            record = records.get(pmid, {}) if last_error is None else {}
            source = {
                "pmid": pmid,
                "pmcid": record.get("pmcid", ""),
                "title": record.get("title", ""),
                "abstract": record.get("abstract", ""),
                "fetch_status": "complete" if last_error is None else "error",
                "fetched_at": utc_now(),
                "contexts": sorted(context["context_id"] for context in live[pmid]),
            }
            if last_error is not None:
                source["error"] = str(last_error)
            source["context_hash"] = canonical_json_hash([live_index[item] for item in source["contexts"]])
            source["source_hash"] = canonical_json_hash({k: source[k] for k in ("pmid", "pmcid", "title", "abstract", "contexts", "context_hash")})
            packet["sources"][pmid] = source
        packet["updated_at"] = utc_now()
        atomic_json_write(SOURCES_PATH, packet)
        fetched += len(batch)
    return {"live_pmids": len(selected), "pending": len(pending), "fetched": fetched}


def configure_cornell() -> Any:
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(REPO_ROOT / "mykey.env", override=True)
    api_key = os.getenv("CORNELL_API_KEY") or os.getenv("Cornell_API_Key") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("CORNELL_API_BASE_URL") or os.getenv("API_Base_URI") or os.getenv("OPENAI_BASE_URL")
    if not api_key or not base_url:
        raise RuntimeError("Cornell/OpenAI key and base URL must be configured")
    return OpenAI(api_key=api_key, base_url=base_url, timeout=180)


def model_json_call(client: Any, model: str, system: str, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            raw = client.chat.completions.with_raw_response.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            response = raw.parse()
            content = str(response.choices[0].message.content or "").strip()
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
            value = json.loads(content)
            usage = getattr(response, "usage", None)
            details = getattr(usage, "completion_tokens_details", None)
            headers = raw.headers
            gateway_cost = None
            for key in ("x-litellm-response-cost", "x-response-cost", "x-cost"):
                if headers.get(key):
                    try:
                        gateway_cost = float(headers[key])
                    except ValueError:
                        pass
                    break
            return value, {
                "model": model,
                "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "reasoning_tokens": int(getattr(details, "reasoning_tokens", 0) or 0),
                "gateway_reported_cost_usd": gateway_cost,
            }
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"{model} JSON call failed after retries: {last_error}")


def compact_context(context: dict[str, Any]) -> dict[str, Any]:
    study = context["cached_study"]
    return {
        "context_id": context["context_id"], "major_site_id": context["major_site_id"],
        "exposure": context["exposure"], "effect_size": study.get("Effect Size"),
        "lower_ci": study.get("Lower CI"), "upper_ci": study.get("Upper CI"),
        "effect_type": study.get("Effect Type"), "cases": study.get("Cases"),
        "sample_size": study.get("Sample Size"), "comparison_type": study.get("comparison_type"),
    }


def classifier_prompt(source: dict[str, Any], contexts: list[dict[str, Any]], article_text: str, full_text: bool) -> str:
    taxonomies = {
        site: [item.to_dict() for item in REGISTRY.for_site(site)]
        for site in MAJOR_DISEASE_BY_SITE_ID
    }
    payload = {
        "pmid": source["pmid"], "title": source.get("title", ""), "article_text": article_text,
        "known_contexts": [compact_context(context) for context in contexts], "allowed_subcategories": taxonomies,
    }
    return """Return exactly one JSON object with this schema:
{"pmid":"...","major_outcomes":[{"major_site_id":"breast|uterus|ovary","general_outcome_reported":true,"subcategory_outcomes":[{"subcategory_id":"allowed ID","status":"reported_separate_estimate|reported_no_separate_estimate|unclear_needs_full_text","evidence_text":"short supplied-text evidence","needs_full_text":true,"estimates":[{"context_id":"known ID","effect_size":number,"lower_ci":number,"upper_ci":number,"effect_type":"RR|OR|HR|...","cases":number|null,"sample_size":number|null,"comparison_type":"...","supporting_text":"quoted/paraphrased supplied-text support"}]}]}]}
Return one major_outcomes entry for every major_site_id represented by a known context, and also retain any of the other two major cancer sites when explicitly reported in the supplied text. An empty subcategory_outcomes list is valid. Use unclear_needs_full_text when the abstract indicates an allowed subtype analysis may exist but cannot establish or fully extract its separate plot-ready effect estimate and confidence interval; set needs_full_text true. Use reported_no_separate_estimate only when the supplied text supports subtype involvement but does not report or imply a separately extractable exposure-association estimate. Do not return unknown IDs. Each estimate must be a separately reported subtype estimate, not a copied general-cancer estimate. Match it to the known context with the same major site and exposure; the same context_id may be used for separate estimates in more than one subcategory. Effect size and both confidence limits are required finite positive numbers ordered as lower_ci <= effect_size <= upper_ci; cases and sample_size may be null when unreported.\n\nINPUT:\n""" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def validate_result(value: Any, source: dict[str, Any], contexts: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict) or str(value.get("pmid")) != source["pmid"] or not isinstance(value.get("major_outcomes"), list):
        raise ValueError("Model response lacks the required PMID/major_outcomes schema")
    context_by_id = {context["context_id"]: context for context in contexts}
    represented = {context["major_site_id"] for context in contexts}
    known_sites = set(MAJOR_DISEASE_BY_SITE_ID)
    seen_sites: set[str] = set()
    for major in value["major_outcomes"]:
        site = major.get("major_site_id") if isinstance(major, dict) else None
        if site not in known_sites or site in seen_sites or not isinstance(major.get("general_outcome_reported"), bool):
            raise ValueError("Unknown, duplicate, or invalid major outcome")
        seen_sites.add(site)
        outcomes = major.get("subcategory_outcomes")
        if not isinstance(outcomes, list):
            raise ValueError("subcategory_outcomes must be a list")
        seen_categories: set[str] = set()
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                raise ValueError("Invalid subcategory outcome")
            category = outcome.get("subcategory_id")
            if not REGISTRY.is_known_subcategory(category, site) or category in seen_categories:
                raise ValueError(f"Unknown/duplicate category ID: {category!r}")
            seen_categories.add(category)
            if outcome.get("status") not in VALID_STATUSES or not isinstance(outcome.get("evidence_text"), str) or not isinstance(outcome.get("needs_full_text"), bool):
                raise ValueError("Invalid subcategory status fields")
            estimates = outcome.get("estimates")
            if not isinstance(estimates, list):
                raise ValueError("estimates must be a list")
            if outcome["status"] == "reported_separate_estimate" and not estimates:
                raise ValueError("reported_separate_estimate requires an estimate")
            if outcome["status"] != "reported_separate_estimate" and estimates:
                raise ValueError("Only reported_separate_estimate may contain estimates")
            for estimate in estimates:
                if not isinstance(estimate, dict) or estimate.get("context_id") not in context_by_id:
                    raise ValueError("Estimate references an unknown context")
                if context_by_id[estimate["context_id"]]["major_site_id"] != site:
                    raise ValueError("Estimate context site does not match subcategory site")
                for field in REQUIRED_NUMERIC_ESTIMATE_FIELDS:
                    if (isinstance(estimate.get(field), bool) or not isinstance(estimate.get(field), (int, float))
                            or not math.isfinite(float(estimate[field]))):
                        raise ValueError(f"Estimate {field} must be numeric")
                for field in OPTIONAL_NUMERIC_ESTIMATE_FIELDS:
                    if estimate.get(field) is not None and (
                        isinstance(estimate.get(field), bool)
                        or not isinstance(estimate.get(field), (int, float))
                        or not math.isfinite(float(estimate[field]))
                    ):
                        raise ValueError(f"Estimate {field} must be numeric or null")
                effect = float(estimate["effect_size"])
                lower = float(estimate["lower_ci"])
                upper = float(estimate["upper_ci"])
                if effect <= 0 or lower <= 0 or upper <= 0 or not lower <= effect <= upper:
                    raise ValueError("Estimate and confidence interval must be positive and ordered")
                if not isinstance(estimate.get("effect_type"), str) or not isinstance(estimate.get("comparison_type"), str) or not isinstance(estimate.get("supporting_text"), str):
                    raise ValueError("Estimate text fields are required")
    if not represented.issubset(seen_sites):
        raise ValueError("Model omitted a represented major_site_id")
    return value


def has_current_complete_event(
    events: list[dict[str, Any]],
    pmid: str,
    stage: str,
    source_hash: str,
    model: str,
) -> bool:
    """Return whether the current saved source already has a model result.

    Prompt hashes remain in the append-only audit ledger, but a harmless prompt
    wording change must not cause every unchanged article to incur another paid
    model call during a monthly update.  ``--force`` is the explicit opt-in for
    reclassification.
    """
    return any(
        event.get("pmid") == pmid
        and event.get("stage") == stage
        and event.get("source_hash") == source_hash
        and event.get("model") == model
        and event.get("status") == "complete"
        for event in events
    )


def append_event(event: dict[str, Any]) -> None:
    with WRITE_LOCK:
        packet = annotation_packet()
        packet["events"].append(event)
        atomic_json_write(ANNOTATIONS_PATH, packet)


def run_model_stage(
    stage: str,
    max_items: int | None,
    dry_run: bool,
    workers: int,
    selected_pmids: set[str] | None = None,
    force: bool = False,
) -> dict[str, int]:
    if stage not in {"terra", "luna"}:
        raise ValueError("stage must be terra or luna")
    contexts = build_live_contexts()
    grouped = contexts_by_pmid(contexts)
    sources = source_packet()["sources"]
    annotations = annotation_packet()["events"]
    tasks = []
    already_complete = 0
    model = TERRA_MODEL if stage == "terra" else LUNA_MODEL
    terra_escalations = needs_luna_from_terra(sources) if stage == "luna" else set()
    for pmid in sorted(grouped):
        if selected_pmids is not None and pmid not in selected_pmids:
            continue
        source = sources.get(pmid)
        if not source or source.get("fetch_status") != "complete":
            continue
        if not force and has_current_complete_event(
            annotations, pmid, stage, source["source_hash"], model
        ):
            already_complete += 1
            continue
        text = str(source.get("abstract") or "")
        pmcid = str(source.get("pmcid") or "")
        if stage == "terra" and not text:
            # Missing abstracts are handled by the Luna PMCID path below;
            # Terra is abstract-only and should not report a phantom task.
            continue
        if stage == "luna":
            # The full-text model is deliberately narrow: missing abstracts or
            # an explicit Terra uncertainty are the only escalation paths.
            if not pmcid or (text and pmid not in terra_escalations):
                continue
            text_path = FULL_TEXT_DIR / f"{pmcid}.txt"
            if not text_path.exists():
                tasks.append((pmid, source, grouped[pmid], ""))
            else:
                tasks.append((pmid, source, grouped[pmid], text_path.read_text(encoding="utf-8")))
        else:
            tasks.append((pmid, source, grouped[pmid], text))
    if max_items is not None:
        tasks = tasks[:max_items]
    if dry_run:
        return {"eligible": len(tasks), "completed": 0, "skipped": already_complete, "errors": 0}
    if not tasks:
        return {"eligible": 0, "completed": 0, "skipped": already_complete, "errors": 0}
    client = configure_cornell()

    def one(task: tuple[str, dict[str, Any], list[dict[str, Any]], str]) -> str:
        pmid, source, article_contexts, text = task
        if stage == "luna" and not text:
            text = fetch_pmc_text(source["pmcid"])
        if not text:
            return "skipped"
        prompt = classifier_prompt(source, article_contexts, text[:180000], full_text=stage == "luna")
        prompt_hash = canonical_json_hash({"stage": stage, "model": TERRA_MODEL if stage == "terra" else LUNA_MODEL, "prompt": prompt})
        result: dict[str, Any] | None = None
        try:
            result, usage = model_json_call(client, model, TERRA_SYSTEM if stage == "terra" else LUNA_SYSTEM, prompt)
            result = validate_result(result, source, article_contexts)
            event = {"event_id": canonical_json_hash([utc_now(), pmid, stage, source["source_hash"], prompt_hash]), "created_at": utc_now(), "pmid": pmid, "stage": stage, "model": model, "status": "complete", "source_hash": source["source_hash"], "prompt_hash": prompt_hash, "result": result, "usage": usage}
            if stage == "terra":
                event["usage"]["terra_input_cost_usd"] = usage["input_tokens"] * TERRA_INPUT_USD_PER_MILLION / 1_000_000
            append_event(event)
            return "completed"
        except Exception as exc:
            error_event = {"event_id": canonical_json_hash([utc_now(), pmid, stage, "error"]), "created_at": utc_now(), "pmid": pmid, "stage": stage, "model": model, "status": "error", "source_hash": source["source_hash"], "prompt_hash": prompt_hash, "error": str(exc)}
            if result is not None:
                error_event["invalid_result"] = result
            append_event(error_event)
            return "error"

    counts = defaultdict(int)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        for status in executor.map(one, tasks):
            counts[status] += 1
    return {
        "eligible": len(tasks),
        "completed": counts["completed"],
        "skipped": already_complete + counts["skipped"],
        "errors": counts["error"],
    }


def needs_luna_from_terra(current_sources: dict[str, Any] | None = None) -> set[str]:
    needed: set[str] = set()
    latest: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for event in annotation_packet()["events"]:
        if event.get("stage") != "terra" or event.get("status") != "complete":
            continue
        if current_sources and event.get("source_hash") != current_sources.get(str(event.get("pmid")), {}).get("source_hash"):
            continue
        key = (str(event.get("pmid")), str(event.get("source_hash") or ""))
        created_at = str(event.get("created_at") or "")
        if key not in latest or created_at >= latest[key][0]:
            latest[key] = (created_at, event)
    for (_, _), (_, event) in latest.items():
        for major in event.get("result", {}).get("major_outcomes", []):
            if any(item.get("status") == "unclear_needs_full_text" for item in major.get("subcategory_outcomes", [])):
                needed.add(str(event.get("pmid")))
    return needed


def fetch_pmc_text(pmcid: str) -> str:
    """Retrieve a PMCID only after Luna escalation and cache the exact local text."""
    path = FULL_TEXT_DIR / f"{pmcid}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    entrez = configure_ncbi()
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with entrez.efetch(db="pmc", id=pmcid, retmode="xml") as handle:
                root = ET.fromstring(handle.read())
            text = "\n".join(part.strip() for part in root.itertext() if part.strip())
            with WRITE_LOCK:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text + "\n", encoding="utf-8")
            return text
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"PMC EFetch failed for {pmcid}: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("sources", "terra", "luna", "all"), default="all")
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--pmid",
        action="append",
        dest="pmids",
        help="Restrict a model stage to one already-included PMID; repeat as needed.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reclassify selected current sources even when a complete result already exists.",
    )
    args = parser.parse_args()
    selected_pmids = set(args.pmids) if args.pmids else None
    live = contexts_by_pmid(build_live_contexts())
    report: dict[str, Any] = {"live_pmids": len(live), "live_contexts": sum(len(v) for v in live.values())}
    if args.stage in {"sources", "all"}:
        report["sources"] = fetch_sources(sorted(live), args.dry_run, args.batch_size, args.max_items)
    if args.stage in {"terra", "all"}:
        report["terra"] = run_model_stage(
            "terra", args.max_items, args.dry_run, args.workers, selected_pmids, args.force
        )
    if args.stage in {"luna", "all"}:
        # Luna admits Terra-unclear items plus empty-abstract sources with a PMCID.
        report["luna"] = run_model_stage(
            "luna", args.max_items, args.dry_run, args.workers, selected_pmids, args.force
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
