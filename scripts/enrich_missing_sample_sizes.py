#!/usr/bin/env python3
"""Fill saved PMCID study sample sizes with Luna full-text review.

Only already-saved MetaFemina study records are considered.  PubMed EFetch is
used solely to resolve PMCID metadata for those PMIDs, and PMC EFetch is used
solely for articles with a PMCID and a missing sample size.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import re
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import meta_analysis  # noqa: E402
from scripts.enrich_subcategories import (  # noqa: E402
    LUNA_MODEL,
    configure_cornell,
    configure_ncbi,
    fetch_pmc_text,
    model_json_call,
    parse_pubmed_xml,
)


AUDIT_PATH = ROOT / "data" / "full_text_sample_size_review.json"
SOURCES_PATH = ROOT / "data" / "subcategory_sources.json"
WRITE_LOCK = threading.Lock()
CHECKLIST_TOTALS = {"cohort": 11, "case_control": 10, "cross_sectional": 8, "rct": 13}
VALID_ANSWERS = {"yes": "Yes", "no": "No", "unclear": "Unclear", "na": "NA", "n/a": "NA"}
LIFETIME_RISK = {"breast": 0.13, "ovarian": 0.013, "uterine": 0.031}

SYSTEM_PROMPT = (
    "You are a systematic-review full-text extractor and JBI appraiser. "
    "Use only the supplied article text. Return valid JSON only and never invent a sample size."
)

JBI_PROMPT = """
Choose exactly one JBI checklist and answer every item with Yes, No, Unclear, or NA.
Unreported information is Unclear, never Yes.

rct q1-q13: true randomization; concealed allocation; baseline similarity;
participant blinding; treatment-provider blinding; identical care apart from the
intervention; outcome-assessor blinding; same outcome measurement; reliable
outcome measurement; complete/appropriately analyzed follow-up; intention-to-treat;
appropriate statistics; appropriate trial design/deviations addressed.

cohort q1-q11: groups similar/same population; exposure measured similarly;
valid/reliable exposure; confounders identified; confounding strategies stated;
outcome absent at baseline; valid/reliable outcome; sufficient follow-up time;
complete/explained follow-up; incomplete follow-up addressed; appropriate statistics.

case_control q1-q10: groups comparable apart from disease; appropriate matching;
same case/control identification criteria; valid/reliable exposure; exposure measured
the same way; confounders identified; confounding strategies stated; valid/reliable
outcome assessment; meaningful exposure period; appropriate statistics.

cross_sectional q1-q8: inclusion criteria clear; subjects/setting described;
valid/reliable exposure; objective condition criteria; confounders identified;
confounding strategies stated; valid/reliable outcomes; appropriate statistics.
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=True, indent=4)
        temporary = Path(handle.name)
    temporary.replace(path)


def is_missing_sample(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower().replace(",", "")
    if text in {"", "-", "--", "na", "n/a", "none", "null", "unknown", "not available"}:
        return True
    try:
        number = float(text)
    except ValueError:
        return False
    return not math.isfinite(number) or number <= 0


def complete_effect(study: dict[str, Any]) -> bool:
    try:
        values = [float(study[field]) for field in ("Effect Size", "Lower CI", "Upper CI")]
    except (KeyError, TypeError, ValueError):
        return False
    return all(math.isfinite(value) and value > 0 for value in values)


def disease_from_filename(path: Path) -> str | None:
    match = re.match(r"(breast|ovarian|uterine)_cancer_(.+)_true_all\.json$", path.name)
    return match.group(1) if match else None


def context_id(path: Path, index: int, study: dict[str, Any]) -> str:
    payload = [
        str(study.get("PMID") or ""), str(path.relative_to(ROOT)), index,
        study.get("Effect Size"), study.get("Lower CI"), study.get("Upper CI"),
        study.get("comparison_type"),
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


def missing_sample_contexts() -> dict[str, list[dict[str, Any]]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted((ROOT / "Cached_results").glob("*/*_true_all.json")):
        disease = disease_from_filename(path)
        if not disease:
            continue
        packet = read_json(path, {})
        for index, study in enumerate(packet.get("studies", []) or []):
            pmid = str(study.get("PMID") or "").strip()
            if (
                not pmid
                or not meta_analysis.is_eligible_effect_type(study.get("Effect Type"))
                or not complete_effect(study)
                or not is_missing_sample(study.get("Sample Size"))
            ):
                continue
            grouped[pmid].append({
                "context_id": context_id(path, index, study),
                "cache_path": str(path.relative_to(ROOT)),
                "study_index": index,
                "pmid": pmid,
                "exposure": path.parent.name,
                "disease": disease,
                "outcome": "incidence",
                "study": study.get("Study"),
                "title": study.get("Reference"),
                "design": study.get("Design"),
                "effect_type": study.get("Effect Type"),
                "effect_size": study.get("Effect Size"),
                "lower_ci": study.get("Lower CI"),
                "upper_ci": study.get("Upper CI"),
                "comparison_type": study.get("comparison_type"),
            })
    return dict(grouped)


def pmcid_map(pmids: set[str]) -> dict[str, str]:
    packet = read_json(SOURCES_PATH, {})
    mapping = {
        str(pmid): str(source.get("pmcid") or "").strip()
        for pmid, source in packet.get("sources", {}).items()
        if isinstance(source, dict) and str(source.get("pmcid") or "").strip()
    }
    unresolved = sorted(pmids - set(mapping), key=int)
    if unresolved:
        entrez = configure_ncbi()
        for offset in range(0, len(unresolved), 100):
            batch = unresolved[offset:offset + 100]
            with entrez.efetch(db="pubmed", id=",".join(batch), retmode="xml") as handle:
                resolved = parse_pubmed_xml(handle.read())
            for pmid, record in resolved.items():
                if record.get("pmcid"):
                    mapping[pmid] = record["pmcid"]
    return mapping


def audit_packet() -> dict[str, Any]:
    packet = read_json(AUDIT_PATH, {})
    if not isinstance(packet, dict) or packet.get("schema_version") != 1:
        packet = {"schema_version": 1, "created_at": utc_now(), "model": LUNA_MODEL, "results": {}}
    packet.setdefault("results", {})
    return packet


def grade_jbi(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("JBI result is not an object")
    checklist = str(raw.get("checklist_type") or "").strip().lower()
    total = CHECKLIST_TOTALS.get(checklist)
    if total is None:
        raise ValueError(f"Unknown JBI checklist: {checklist!r}")
    answers_raw = raw.get("answers")
    if not isinstance(answers_raw, dict):
        raise ValueError("JBI answers are missing")
    answers = {}
    for index in range(1, total + 1):
        key = f"q{index}"
        normalized = str(answers_raw.get(key) or "").strip().lower()
        if normalized not in VALID_ANSWERS:
            raise ValueError(f"Invalid JBI answer for {key}: {answers_raw.get(key)!r}")
        answers[key] = VALID_ANSWERS[normalized]
    yes = sum(value == "Yes" for value in answers.values())
    na = sum(value == "NA" for value in answers.values())
    denominator = total - na
    score = round(yes / denominator * 100, 1) if denominator else 0.0
    grade = "Good" if score > 80 else "Moderate" if score >= 51 else "Fair"
    return {"checklist_type": checklist, "answers": answers, "score_percent": score, "grade": grade}


def prompt_for(pmid: str, contexts: list[dict[str, Any]], article_text: str) -> str:
    compact = [{key: value for key, value in context.items() if key not in {"cache_path", "study_index"}} for context in contexts]
    return f"""Review PMID {pmid}. For each supplied context, find the number of human participants
actually contributing to the reported exposure-cancer estimate. Prefer the context-specific analytic
sample over an enrollment total. If several cohorts were pooled for that estimate, use their combined
analytic sample. Do not use case count as sample size. Return null when the full text does not establish it.

Reassess JBI from the full text using the checklist below. The JBI appraisal is article-level.
{JBI_PROMPT}

Return exactly:
{{"pmid":"{pmid}","contexts":[{{"context_id":"...","sample_size":123-or-null,
"sample_size_supporting_text":"concise source-supported explanation",
"confidence":"high|medium|low"}}],"jbi":{{"checklist_type":"cohort|case_control|cross_sectional|rct",
"answers":{{"q1":"Yes"}}}}}}
Return every context_id exactly once and no prose.

CONTEXTS:
{json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}

FULL ARTICLE TEXT:
{article_text[:180000]}"""


def validate_luna_result(value: Any, pmid: str, contexts: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict) or str(value.get("pmid")) != pmid:
        raise ValueError("Luna result has the wrong PMID")
    expected = {context["context_id"] for context in contexts}
    returned = value.get("contexts")
    if not isinstance(returned, list):
        raise ValueError("Luna result contexts are missing")
    normalized = []
    seen = set()
    for item in returned:
        cid = str(item.get("context_id") or "") if isinstance(item, dict) else ""
        if cid not in expected or cid in seen:
            raise ValueError(f"Unknown or duplicate Luna context: {cid!r}")
        seen.add(cid)
        sample = item.get("sample_size")
        if sample is not None:
            if isinstance(sample, bool) or not isinstance(sample, (int, float)) or not math.isfinite(float(sample)) or float(sample) <= 0:
                raise ValueError(f"Invalid sample size for {cid}")
            sample = int(round(float(sample)))
        confidence = str(item.get("confidence") or "").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            raise ValueError(f"Invalid confidence for {cid}")
        normalized.append({
            "context_id": cid,
            "sample_size": sample,
            "sample_size_supporting_text": str(item.get("sample_size_supporting_text") or "").strip(),
            "confidence": confidence,
        })
    if seen != expected:
        raise ValueError(f"Luna omitted {len(expected - seen)} contexts")
    return {"pmid": pmid, "contexts": normalized, "jbi": grade_jbi(value.get("jbi"))}


def save_result(pmid: str, pmcid: str, result: dict[str, Any], usage: dict[str, Any]) -> None:
    with WRITE_LOCK:
        packet = audit_packet()
        packet["results"][pmid] = {
            "status": "complete", "reviewed_at": utc_now(), "pmcid": pmcid,
            "model": LUNA_MODEL, "result": result, "usage": usage,
        }
        packet["updated_at"] = utc_now()
        atomic_json_write(AUDIT_PATH, packet)


def save_error(pmid: str, pmcid: str, error: Exception) -> None:
    with WRITE_LOCK:
        packet = audit_packet()
        packet["results"][pmid] = {
            "status": "error", "reviewed_at": utc_now(), "pmcid": pmcid,
            "model": LUNA_MODEL, "error": str(error),
        }
        packet["updated_at"] = utc_now()
        atomic_json_write(AUDIT_PATH, packet)


def apply_results(grouped: dict[str, list[dict[str, Any]]], review: dict[str, Any]) -> dict[str, Any]:
    changed_files: set[str] = set()
    filled_contexts = 0
    jbi_updates = 0
    for pmid, entry in review.get("results", {}).items():
        if entry.get("status") != "complete" or pmid not in grouped:
            continue
        result = entry["result"]
        context_result = {item["context_id"]: item for item in result["contexts"]}
        jbi = result["jbi"]
        for context in grouped[pmid]:
            extracted = context_result.get(context["context_id"])
            if not extracted:
                continue
            source_path = ROOT / context["cache_path"]
            sibling_pattern = re.compile(
                re.escape(source_path.name.removesuffix("_true_all.json"))
                + r"_true_(?:all|core)\.json$"
            )
            sibling_paths = sorted(
                path for path in source_path.parent.glob("*.json")
                if sibling_pattern.match(path.name)
            )
            for path in sibling_paths:
                packet = read_json(path, {})
                modified = False
                for study in packet.get("studies", []) or []:
                    if str(study.get("PMID") or "") != pmid:
                        continue
                    if study.get("Effect Size") != context["effect_size"] or study.get("Lower CI") != context["lower_ci"] or study.get("Upper CI") != context["upper_ci"]:
                        continue
                    sample = extracted.get("sample_size")
                    if sample is not None and study.get("Sample Size") != sample:
                        study["Sample Size"] = sample
                        if study.get("Cases") in {None, "", "-", "N/A"}:
                            study["Estimated Cases"] = int(round(sample * LIFETIME_RISK[context["disease"]]))
                        support = study.get("extraction_supporting_text")
                        if not isinstance(support, dict):
                            support = {}
                            study["extraction_supporting_text"] = support
                        support["sample_size"] = extracted["sample_size_supporting_text"]
                        filled_contexts += 1
                        modified = True
                    if (
                        study.get("JBI") != jbi["answers"]
                        or study.get("Quality %") != jbi["score_percent"]
                        or study.get("Quality Score") != jbi["grade"]
                    ):
                        study["JBI"] = jbi["answers"]
                        study["Quality %"] = jbi["score_percent"]
                        study["Quality Score"] = jbi["grade"]
                        jbi_updates += 1
                        modified = True
                if modified:
                    atomic_json_write(path, packet)
                    changed_files.add(str(path.relative_to(ROOT)))
    return {"changed_files": sorted(changed_files), "filled_contexts": filled_contexts, "jbi_updates": jbi_updates}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Apply completed Luna results to saved caches")
    parser.add_argument("--force", action="store_true", help="Repeat already-completed Luna reviews")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-items", type=int)
    args = parser.parse_args()

    grouped = missing_sample_contexts()
    pmcids = pmcid_map(set(grouped))
    targets = [(pmid, pmcids[pmid], grouped[pmid]) for pmid in sorted(grouped, key=int) if pmcids.get(pmid)]
    if args.max_items is not None:
        targets = targets[:args.max_items]
    existing = audit_packet().get("results", {})
    pending = [target for target in targets if args.force or existing.get(target[0], {}).get("status") != "complete"]
    print(json.dumps({
        "missing_sample_pmids": len(grouped), "pmcid_targets": len(targets),
        "pending_luna_reviews": len(pending), "model": LUNA_MODEL,
    }, indent=2))
    if pending:
        client = configure_cornell()

        def review_one(task: tuple[str, str, list[dict[str, Any]]]) -> str:
            pmid, pmcid, contexts = task
            try:
                text = fetch_pmc_text(pmcid)
                value, usage = model_json_call(client, LUNA_MODEL, SYSTEM_PROMPT, prompt_for(pmid, contexts, text))
                result = validate_luna_result(value, pmid, contexts)
                save_result(pmid, pmcid, result, usage)
                return "complete"
            except Exception as exc:
                save_error(pmid, pmcid, exc)
                return "error"

        counts: defaultdict[str, int] = defaultdict(int)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            for status in executor.map(review_one, pending):
                counts[status] += 1
        print(json.dumps(dict(counts), indent=2))
    if args.write:
        print(json.dumps(apply_results(grouped, audit_packet()), indent=2))


if __name__ == "__main__":
    main()
