#!/usr/bin/env python3
"""Discover and audit newly published MetaFemina evidence.

The workflow is deliberately resumable. Discovery writes an immutable candidate
packet before any relevance screening or saved-result mutation takes place.
"""

from __future__ import annotations

import argparse
import calendar
import concurrent.futures
import glob
import json
import os
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from Bio import Entrez
from dotenv import load_dotenv
from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = REPO_ROOT / "Cached_results"
EXPOSURES_FILE = REPO_ROOT / "static" / "exposures.json"
SYNONYMS_FILE = DATA_DIR / "synonyms_cache.json"

CANCER_QUERIES = {
    "Breast cancer": (
        '"Breast Neoplasms"[MeSH Terms] OR "breast cancer"[Title/Abstract] '
        'OR "breast carcinoma"[Title/Abstract] OR "mammary cancer"[Title/Abstract]'
    ),
    "Ovarian cancer": (
        '"Ovarian Neoplasms"[MeSH Terms] OR "ovarian cancer"[Title/Abstract] '
        'OR "ovarian carcinoma"[Title/Abstract] OR "ovary cancer"[Title/Abstract]'
    ),
    "Uterine cancer": (
        '"Uterine Neoplasms"[MeSH Terms] OR "Endometrial Neoplasms"[MeSH Terms] '
        'OR "uterine cancer"[Title/Abstract] OR "uterine carcinoma"[Title/Abstract] '
        'OR "endometrial cancer"[Title/Abstract] OR "endometrial carcinoma"[Title/Abstract]'
    ),
}

USAGE_LOCK = threading.Lock()

FIRST_SCREEN_SYSTEM = """You are the sensitive first screening layer for a systematic review of nutritional exposures and incident women's cancers. Return valid JSON only."""

FIRST_SCREEN_INSTRUCTIONS = """
For every supplied exposure-cancer context, decide whether the article's title,
abstract, or MeSH terms plausibly study the association between that exposure
and the incidence/risk/development of that cancer.

PASS when the requested exposure (or a direct nutritional synonym/biomarker)
and requested cancer are genuinely connected to a risk/incidence question. When
uncertain, PASS so the detailed second layer can decide. A null association is
relevant. A missing effect size, p-value, confidence interval, sample size, case
count, or even a missing abstract must NEVER by itself cause failure.

FAIL only when this is clearly a lexical false match, the exposure is incidental,
the requested cancer is not studied, or the article is clearly limited to
treatment/survival/prognosis/recurrence/mechanism with no incident-cancer question.
Do not use publication type, animal status, composite exposure, benign disease,
or genetics as the primary reason here; those belong to the second screen.

Return exactly:
{"results":[{"context_id":"...","decision":"PASS or FAIL","reason":"one sentence"}]}
Return one result for every context_id and do not add prose.
"""

SECOND_SCREEN_SYSTEM = """You are the detailed second screening and abstract-extraction layer for a systematic review. Apply the supplied protocol exactly and return valid JSON only."""

SECOND_SCREEN_INSTRUCTIONS = """
Evaluate every supplied context for an original human study of the requested
nutritional exposure and incident requested cancer. Apply these exclusion codes:

S2-REVIEW: meta-analysis, systematic/scoping/narrative/umbrella review.
S2-NONPRIMARY: editorial, commentary, guideline, protocol, non-comparative case
report/series, correction without original results, or retracted publication.
S2-ANIMAL: exclusively animal, cell-line, organoid, xenograft, or preclinical.
S2-EXPOSURE-MISMATCH: requested nutritional exposure is absent, incidental,
another concept, or a medical treatment rather than the exposure.
S2-COMPOUND: target is inseparable from a dietary index, mixture, multi-nutrient
intervention, or combined exposure, with no target-specific estimate.
S2-CANCER-MISMATCH: requested cancer lacks separable results. Cervical cancer is
not uterine cancer.
S2-WRONG-OUTCOME: survival, mortality, recurrence, progression, treatment
response, prognosis, prevalence, or another endpoint without incident cancer.
S2-POSTDIAGNOSIS: exposure is measured/administered only after cancer diagnosis
or treatment. A case-control study using prediagnostic exposure remains eligible.
S2-BENIGN-ONLY: only benign breast disease, proliferative benign breast disease,
uterine fibroid/leiomyoma, endometriosis, or another nonmalignant condition.
S2-GENETIC-FOCUS: focus is a particular gene, mutation, SNP, polymorphism, gene
expression, genotype-stratified result, or gene-exposure interaction without a
population-wide exposure effect. Do not automatically exclude Mendelian
randomization of the exposure-cancer relationship; flag it as MR instead.
S2-DIAGNOSTIC-MECHANISTIC: diagnostic accuracy, tumor tissue, molecular mechanism,
imaging, or biomarker discrimination without evidence about developing cancer.
S2-NO-TARGET-ESTIMATE: target cancer incidence result cannot be separated.
S2-DUPLICATE: clearly a duplicate/overlapping report of the same analysis; use
only when the supplied metadata establishes this.

CRITICAL: Do not exclude an otherwise relevant study merely because the abstract
does not state an effect size, p-value, confidence interval, sample size, or case
count. Mark missing fields and request full text. A null association is relevant.
Mixed animal-human work is eligible when human results are separable. Multiple
cancers are eligible when target-cancer results are separable.

For each INCLUDE context, extract only explicitly supported abstract data:
effect_size, effect_type (RR/OR/HR), ci_lower, ci_upper, p_value, total_n, cases,
comparison_type, design, timing, continent, exposure_measurement_type
(dietary_intake/human_biospecimen/unclear), needs_inversion, and concise supporting
text. Use null when absent. abstract_sufficient_for_meta is true only when a
usable target-context effect estimate and uncertainty (normally both CI bounds)
are available with enough comparison/design information to pool responsibly.

Perform preliminary JBI appraisal using the appropriate current checklist:
cohort q1-q11, case_control q1-q10, cross_sectional q1-q8, or rct q1-q13. Answers
must be Yes, No, Unclear, or NA. Score Yes/(total-NA)*100. Good >80%; Moderate
51-80%; Fair <51%. Do not infer unreported methods as Yes.

needs_full_text must be true for an INCLUDE context when abstract_sufficient_for_meta
is false OR the preliminary JBI grade is not Good. PMCID availability does not
change eligibility.

Return exactly:
{"results":[{
 "context_id":"...","eligibility":"INCLUDE or EXCLUDE",
 "exclusion_code":"one approved code or null","reason":"one sentence",
 "is_mendelian_randomization":false,"abstract_sufficient_for_meta":false,
 "missing_quantitative_fields":["..."],"needs_full_text":false,
 "extraction":{"effect_size":null,"effect_type":null,"ci_lower":null,
 "ci_upper":null,"p_value":null,"total_n":null,"cases":null,
 "comparison_type":null,"design":null,"timing":null,"continent":null,
 "exposure_measurement_type":"unclear","needs_inversion":false,
 "supporting_text":""},
 "jbi":{"checklist_type":"cohort/case_control/cross_sectional/rct",
 "answers":{"q1":"Unclear"},"score_percent":0,"grade":"Good/Moderate/Fair"}
}]}
Return one result for every context_id and do not add prose.
"""

FULL_TEXT_SYSTEM = """You are a systematic-review full-text extractor and JBI appraiser. Use only the supplied article text, apply the protocol exactly, and return valid JSON only."""

FULL_TEXT_INSTRUCTIONS = """
Re-evaluate each supplied exposure-cancer-incidence context using the complete PMC
article text. Missing abstract statistics were not an exclusion; now inspect text
and tables for context-specific quantitative results.

Return one of:
- INCLUDE_META: an eligible original human incidence study with a usable effect
  estimate and uncertainty, and a full-text JBI grade of Good.
- ELIGIBLE_NOT_POOLABLE: relevant, but quantitative data remain unusable or the
  full-text JBI grade remains below Good.
- MR_SEPARATE: Mendelian-randomization evidence about the exposure-cancer
  relationship; record separately and do not pool with conventional studies.
- EXCLUDE: full text establishes one of the approved S2 exclusion codes.

Use the same S2 exclusion codes and interpretations supplied in the second-screen
protocol. Prefer the most fully adjusted target-context estimate. Standardize to
higher versus lower exposure and flag needs_inversion when the published contrast
is lower versus higher. Never invent values.

Extract: effect_size, effect_type (RR/OR/HR), ci_lower, ci_upper, p_value, total_n,
cases, comparison_type, design, timing, continent, exposure_measurement_type,
needs_inversion, and concise supporting_text. Reperform JBI using cohort q1-q11,
case_control q1-q10, cross_sectional q1-q8, or rct q1-q13, with Yes/No/Unclear/NA.
Unreported information is Unclear, not Yes.

Return exactly:
{"results":[{"context_id":"...","status":"INCLUDE_META, ELIGIBLE_NOT_POOLABLE, MR_SEPARATE, or EXCLUDE","exclusion_code":null,"reason":"one sentence","extraction":{"effect_size":null,"effect_type":null,"ci_lower":null,"ci_upper":null,"p_value":null,"total_n":null,"cases":null,"comparison_type":null,"design":null,"timing":null,"continent":null,"exposure_measurement_type":"unclear","needs_inversion":false,"supporting_text":""},"jbi":{"checklist_type":"cohort/case_control/cross_sectional/rct","answers":{"q1":"Unclear"}}}]}
Return one result for every context_id and do not add prose.
"""


def configure_cornell() -> tuple[OpenAI, str]:
    load_dotenv(REPO_ROOT / "mykey.env", override=True)
    api_key = (
        os.getenv("CORNELL_API_KEY")
        or os.getenv("Cornell_API_Key")
        or os.getenv("OPENAI_API_KEY")
    )
    base_url = (
        os.getenv("CORNELL_API_BASE_URL")
        or os.getenv("API_Base_URI")
        or os.getenv("OPENAI_BASE_URL")
    )
    if not api_key or not base_url:
        raise RuntimeError(
            "CORNELL_API_KEY/Cornell_API_Key and CORNELL_API_BASE_URL/API_Base_URI must be configured"
        )
    return OpenAI(api_key=api_key, base_url=base_url, timeout=180), os.getenv("MONTHLY_SCREEN_MODEL", "gpt-5.6-sol")


def json_from_model_text(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            return json.loads(value[start : end + 1])
        raise


def empty_usage(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "calculated_cost_usd": 0.0,
        "gateway_reported_cost_usd": 0.0,
    }


def add_usage(usage: dict[str, Any], response: Any, headers: Any = None) -> None:
    response_usage = getattr(response, "usage", None)
    input_tokens = int(getattr(response_usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(response_usage, "completion_tokens", 0) or 0)
    details = getattr(response_usage, "completion_tokens_details", None)
    reasoning_tokens = int(getattr(details, "reasoning_tokens", 0) or 0)
    with USAGE_LOCK:
        usage["calls"] += 1
        usage["input_tokens"] += input_tokens
        usage["output_tokens"] += output_tokens
        usage["reasoning_tokens"] += reasoning_tokens
        usage["calculated_cost_usd"] = round(
            usage["input_tokens"] * 5 / 1_000_000 + usage["output_tokens"] * 30 / 1_000_000,
            6,
        )
        if headers:
            for key in ("x-litellm-response-cost", "x-response-cost", "x-cost"):
                raw_cost = headers.get(key)
                if raw_cost:
                    try:
                        usage["gateway_reported_cost_usd"] = round(
                            usage["gateway_reported_cost_usd"] + float(raw_cost), 6
                        )
                    except ValueError:
                        pass
                    break


def cornell_json_call(
    client: OpenAI,
    model: str,
    system: str,
    prompt: str,
    usage: dict[str, Any],
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            raw_response = client.chat.completions.with_raw_response.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            response = raw_response.parse()
            add_usage(usage, response, raw_response.headers)
            return json_from_model_text(response.choices[0].message.content)
        except Exception as exc:  # pragma: no cover - API retry path
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Cornell screening call failed after retries: {last_error}")


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data: Any, indent: int = 2, ensure_ascii: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=ensure_ascii, indent=indent)
    temporary.replace(path)


def previous_month(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    first_this_month = today.replace(day=1)
    last_previous = first_this_month - timedelta(days=1)
    first_previous = last_previous.replace(day=1)
    return first_previous.isoformat(), last_previous.isoformat()


def configure_entrez() -> str:
    # A locally edited mykey.env should take precedence over stale variables in
    # a long-lived shell. GitHub Actions has no mykey.env, so repository secrets
    # remain authoritative there.
    load_dotenv(REPO_ROOT / "mykey.env", override=True)
    Entrez.email = os.getenv("NCBI_EMAIL") or os.getenv("PUBMED_EMAIL")
    Entrez.api_key = os.getenv("NCBI_API_KEY") or os.getenv("PUBMED_API_KEY")
    strict_key = os.getenv("MONTHLY_REQUIRE_VALID_NCBI_KEY", "false").lower() == "true"
    if not Entrez.email:
        raise RuntimeError("NCBI_EMAIL (or PUBMED_EMAIL) is not configured")
    if not Entrez.api_key:
        if strict_key:
            raise RuntimeError("NCBI_API_KEY is missing; strict monthly validation is enabled")
        return "not_configured"

    # NCBI returns HTTP 400 for an invalid/expired API key. Detect that once and
    # continue through the public rate-limited endpoint so evidence discovery is
    # not lost; the status is persisted for alerting and audit purposes.
    try:
        with Entrez.esearch(db="pubmed", term="breast cancer", retmax=0) as handle:
            Entrez.read(handle)
        return "working"
    except Exception as exc:
        if "400" not in str(exc):
            raise RuntimeError(f"NCBI API-key validation failed: {exc}") from exc
        if strict_key:
            raise RuntimeError(
                "NCBI_API_KEY was rejected with HTTP 400 (expired or invalid); "
                "strict monthly validation is enabled"
            ) from exc
        print(
            "WARNING: NCBI_API_KEY was rejected (HTTP 400; likely expired or invalid). "
            "Continuing through NCBI's public rate-limited endpoint.",
            flush=True,
        )
        Entrez.api_key = None
        return "rejected_http_400"


def saved_pmids() -> set[str]:
    values: set[str] = set()
    for filename in glob.glob(str(CACHE_DIR / "**" / "*.json"), recursive=True):
        cached = load_json(Path(filename), {})
        if not isinstance(cached, dict):
            continue
        for study in cached.get("studies", []):
            pmid = str(study.get("PMID") or "").strip()
            if pmid and pmid.lower() not in {"none", "nan"}:
                values.add(pmid)
    return values


def clean_search_term(term: str) -> str:
    return re.sub(r"\s+", " ", str(term or "")).strip().strip('"')


def exposure_terms() -> dict[str, list[str]]:
    exposures = load_json(EXPOSURES_FILE, [])
    synonyms = load_json(SYNONYMS_FILE, {})
    result: dict[str, list[str]] = {}
    for exposure in exposures:
        cache_entry = synonyms.get(str(exposure).lower(), {})
        core = cache_entry.get("core", "") if isinstance(cache_entry, dict) else str(cache_entry)
        terms = [str(exposure)] + [part for part in core.split(",") if part.strip()]
        seen: set[str] = set()
        cleaned: list[str] = []
        for raw_term in terms:
            term = clean_search_term(raw_term)
            key = term.casefold()
            if len(term) >= 3 and key not in seen:
                cleaned.append(term)
                seen.add(key)
        result[str(exposure)] = cleaned[:12]
    return result


def quote_term(term: str) -> str:
    escaped = term.replace('"', "")
    return f'"{escaped}"[Title/Abstract]'


def build_query(terms: list[str], cancer_query: str) -> str:
    exposure_query = " OR ".join(quote_term(term) for term in terms)
    return f"(({exposure_query}) AND ({cancer_query}))"


def entrez_search(query: str, start_date: str, end_date: str) -> list[str]:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with Entrez.esearch(
                db="pubmed",
                term=query,
                retmax=10000,
                datetype="pdat",
                mindate=start_date.replace("-", "/"),
                maxdate=end_date.replace("-", "/"),
            ) as handle:
                record = Entrez.read(handle)
            return [str(value) for value in record.get("IdList", [])]
        except Exception as exc:  # pragma: no cover - network retry path
            last_error = exc
            if "400" in str(exc):
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"NCBI ESearch failed after retries: {last_error}")


def scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(scalar_text(item) for item in value).strip()
    return str(value).strip()


def journal_publication_date(article: dict[str, Any]) -> str:
    citation = article.get("MedlineCitation", {})
    article_data = citation.get("Article", {})
    # PubMed's PDAT filter follows the issue/publication date. Prefer that over
    # ArticleDate, which is commonly the earlier electronic-publication date.
    pub_date = article_data.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
    year = scalar_text(pub_date.get("Year"))
    month_raw = scalar_text(pub_date.get("Month"))
    day = scalar_text(pub_date.get("Day")) or "01"
    if year:
        if not month_raw:
            return year
        try:
            month = str(list(calendar.month_abbr).index(month_raw[:3].title())).zfill(2)
        except ValueError:
            month = month_raw.zfill(2) if month_raw.isdigit() else "01"
        return f"{year}-{month}-{day.zfill(2)}"
    if scalar_text(pub_date.get("MedlineDate")):
        match = re.search(r"\b(19|20)\d{2}\b", scalar_text(pub_date.get("MedlineDate")))
        return match.group(0) if match else "Unknown"

    return "Unknown"


def electronic_publication_date(article: dict[str, Any]) -> str:
    article_data = article.get("MedlineCitation", {}).get("Article", {})
    article_dates = article_data.get("ArticleDate", [])
    if article_dates:
        value = article_dates[0]
        year = scalar_text(value.get("Year"))
        month = scalar_text(value.get("Month")) or "01"
        day = scalar_text(value.get("Day")) or "01"
        if year:
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return "Unknown"


def article_record(article: dict[str, Any]) -> dict[str, Any]:
    citation = article.get("MedlineCitation", {})
    article_data = citation.get("Article", {})
    pmid = scalar_text(citation.get("PMID"))
    abstract_parts = article_data.get("Abstract", {}).get("AbstractText", [])
    abstract = " ".join(scalar_text(part) for part in abstract_parts).strip()
    mesh = []
    for heading in citation.get("MeshHeadingList", []):
        descriptor = scalar_text(heading.get("DescriptorName"))
        qualifiers = [scalar_text(value) for value in heading.get("QualifierName", [])]
        mesh.append(descriptor + (" / " + ", ".join(qualifiers) if qualifiers else ""))
    identifiers = {}
    for item in article.get("PubmedData", {}).get("ArticleIdList", []):
        id_type = str(getattr(item, "attributes", {}).get("IdType", "")).lower()
        identifiers[id_type] = scalar_text(item)
    authors = []
    for author in article_data.get("AuthorList", []):
        collective = scalar_text(author.get("CollectiveName"))
        if collective:
            authors.append(collective)
        else:
            name = " ".join(filter(None, [scalar_text(author.get("LastName")), scalar_text(author.get("Initials"))]))
            if name:
                authors.append(name)
    return {
        "pmid": pmid,
        "pmcid": identifiers.get("pmc", ""),
        "doi": identifiers.get("doi", ""),
        "published_date": journal_publication_date(article),
        "journal_publication_date": journal_publication_date(article),
        "electronic_publication_date": electronic_publication_date(article),
        "title": scalar_text(article_data.get("ArticleTitle")),
        "abstract": abstract,
        "mesh": mesh,
        "publication_types": [scalar_text(value) for value in article_data.get("PublicationTypeList", [])],
        "authors": authors,
        "journal": scalar_text(article_data.get("Journal", {}).get("Title")),
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    }


def book_article_record(article: dict[str, Any]) -> dict[str, Any]:
    """Parse PubmedBookArticle records, which are absent from PubmedArticle."""
    document = article.get("BookDocument", {})
    book = document.get("Book", {})
    pmid = scalar_text(document.get("PMID"))
    abstract = " ".join(
        scalar_text(part) for part in document.get("Abstract", {}).get("AbstractText", [])
    ).strip()
    authors = []
    for author_group in document.get("AuthorList", []):
        for author in author_group if isinstance(author_group, (list, tuple)) else [author_group]:
            collective = scalar_text(author.get("CollectiveName"))
            name = collective or " ".join(
                filter(None, [scalar_text(author.get("LastName")), scalar_text(author.get("Initials"))])
            )
            if name:
                authors.append(name)
    identifiers = {}
    for item in article.get("PubmedBookData", {}).get("ArticleIdList", []):
        id_type = str(getattr(item, "attributes", {}).get("IdType", "")).lower()
        identifiers[id_type] = scalar_text(item)
    pub_date = book.get("PubDate", {})
    year = scalar_text(pub_date.get("Year"))
    month = scalar_text(pub_date.get("Month"))
    day = scalar_text(pub_date.get("Day"))
    published = year or "Unknown"
    if year and month:
        published = f"{year}-{month.zfill(2)}-{(day or '01').zfill(2)}"
    return {
        "pmid": pmid,
        "pmcid": identifiers.get("pmc", ""),
        "doi": identifiers.get("doi", ""),
        "published_date": published,
        "title": scalar_text(document.get("ArticleTitle")),
        "abstract": abstract,
        "mesh": [],
        "publication_types": [scalar_text(value) for value in document.get("PublicationType", [])],
        "authors": authors,
        "journal": scalar_text(book.get("BookTitle")),
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    }


def date_overlaps_window(value: str, start_date: str, end_date: str) -> bool:
    """Return whether a PubMed date, including year/month precision, overlaps."""
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", str(value or ""))
    if not match:
        # Preserve records with unknown dates for sensitive downstream screening.
        return True
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    first = date(year, month, int(match.group(3) or 1))
    if match.group(3):
        last = first
    elif match.group(2):
        last = date(year, month, calendar.monthrange(year, month)[1])
    else:
        last = date(year, 12, 31)
    return last >= date.fromisoformat(start_date) and first <= date.fromisoformat(end_date)


def select_in_window_publication_date(record: dict[str, Any], start_date: str, end_date: str) -> str | None:
    """Select the PubMed online or issue publication date falling in-window."""
    issue_date = record.get("journal_publication_date") or record.get("published_date")
    electronic_date = record.get("electronic_publication_date")
    if issue_date and issue_date != "Unknown" and date_overlaps_window(str(issue_date), start_date, end_date):
        return str(issue_date)
    if electronic_date and electronic_date != "Unknown" and date_overlaps_window(str(electronic_date), start_date, end_date):
        return str(electronic_date)
    # Unknown dates remain eligible for sensitive screening; known out-of-range
    # dates do not. PubmedBookArticle has no ArticleDate, preventing a 2026
    # contribution/update date from turning a 2012 book chapter into a new paper.
    if str(issue_date or "Unknown") == "Unknown" and str(electronic_date or "Unknown") == "Unknown":
        return "Unknown"
    return None


def entrez_fetch(pmids: list[str]) -> tuple[dict[str, dict[str, Any]], int]:
    records: dict[str, dict[str, Any]] = {}
    request_count = 0
    for offset in range(0, len(pmids), 200):
        batch = pmids[offset : offset + 200]
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with Entrez.efetch(db="pubmed", id=",".join(batch), retmode="xml") as handle:
                    payload = Entrez.read(handle)
                request_count += 1
                for article in payload.get("PubmedArticle", []):
                    parsed = article_record(article)
                    if parsed["pmid"]:
                        records[parsed["pmid"]] = parsed
                for article in payload.get("PubmedBookArticle", []):
                    parsed = book_article_record(article)
                    if parsed["pmid"]:
                        records[parsed["pmid"]] = parsed
                last_error = None
                break
            except Exception as exc:  # pragma: no cover - network retry path
                last_error = exc
                time.sleep(2 ** attempt)
        if last_error:
            raise RuntimeError(f"NCBI EFetch failed after retries: {last_error}")
    return records, request_count


def discover(start_date: str, end_date: str, output_dir: Path) -> dict[str, Any]:
    api_key_status = configure_entrez()
    known_pmids = saved_pmids()
    contexts_by_pmid: dict[str, set[tuple[str, str]]] = defaultdict(set)
    queries = 0
    terms_by_exposure = exposure_terms()
    total_contexts = len(terms_by_exposure) * len(CANCER_QUERIES)
    started = time.time()

    search_jobs = [
        (exposure, cancer, build_query(terms, cancer_query))
        for exposure, terms in terms_by_exposure.items()
        for cancer, cancer_query in CANCER_QUERIES.items()
    ]

    def run_search(job: tuple[str, str, str]) -> tuple[str, str, list[str]]:
        exposure, cancer, query = job
        return exposure, cancer, entrez_search(query, start_date, end_date)

    # Five workers stay below NCBI's keyed 10-request/second allowance while
    # avoiding hundreds of sequential network round trips.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_search, job) for job in search_jobs]
        for future in concurrent.futures.as_completed(futures):
            exposure, cancer, found_pmids = future.result()
            for pmid in found_pmids:
                if pmid not in known_pmids:
                    contexts_by_pmid[pmid].add((exposure, cancer))
            queries += 1
            if queries % 75 == 0 or queries == total_contexts:
                print(
                    f"Discovery progress: {queries}/{total_contexts} exposure-cancer searches; "
                    f"{len(contexts_by_pmid)} unique unsaved PMIDs",
                    flush=True,
                )

    pmids = sorted(contexts_by_pmid, key=lambda value: int(value))
    articles, fetch_requests = entrez_fetch(pmids)
    candidate_records = []
    out_of_window = []
    for pmid in pmids:
        record = articles.get(pmid, {"pmid": pmid})
        record["candidate_contexts"] = [
            {"exposure": exposure, "cancer": cancer, "outcome": "Incidence"}
            for exposure, cancer in sorted(contexts_by_pmid[pmid])
        ]
        selected_date = select_in_window_publication_date(record, start_date, end_date)
        if selected_date is None:
            out_of_window.append(record)
            continue
        record["published_date"] = selected_date
        candidate_records.append(record)

    packet = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "publication_date_start": start_date,
        "publication_date_end": end_date,
        "listed_exposures": len(terms_by_exposure),
        "cancer_types": list(CANCER_QUERIES),
        "saved_pmids_omitted": len(known_pmids),
        "ncbi_api_key_status": api_key_status,
        "ncbi_requests": {"esearch": queries, "efetch": fetch_requests, "total": queries + fetch_requests},
        "candidate_pmids": len(candidate_records),
        "candidate_contexts": sum(len(item["candidate_contexts"]) for item in candidate_records),
        "postfetch_out_of_window_omitted": len(out_of_window),
        "elapsed_seconds": round(time.time() - started, 1),
        "articles": candidate_records,
    }
    save_json(output_dir / "candidates.json", packet)
    save_json(
        output_dir / "out_of_window_records.json",
        {"count": len(out_of_window), "records": out_of_window},
    )
    print(json.dumps({key: value for key, value in packet.items() if key != "articles"}, indent=2))
    return packet


def refresh_candidate_metadata(output_dir: Path) -> dict[str, Any]:
    """Refresh cached PubMed metadata without repeating discovery or LLM calls."""
    configure_entrez()
    path = output_dir / "candidates.json"
    packet = load_json(path, {})
    articles = list(packet.get("articles", []))
    # A refresh may be correcting an earlier date-selection rule, so include
    # records previously parked as out-of-window rather than losing them.
    prior_out = load_json(output_dir / "out_of_window_records.json", {}).get("records", [])
    by_pmid = {str(item.get("pmid")): item for item in articles + list(prior_out)}
    articles = list(by_pmid.values())
    if not articles:
        raise RuntimeError(f"No candidates found in {path}")
    contexts = {
        str(item.get("pmid")): item.get("candidate_contexts", []) for item in articles
    }
    refreshed, requests = entrez_fetch(sorted(contexts, key=int))
    retained = []
    out_of_window = []
    start_date = packet["publication_date_start"]
    end_date = packet["publication_date_end"]
    for pmid, candidate_contexts in contexts.items():
        record = refreshed.get(pmid, next(item for item in articles if str(item.get("pmid")) == pmid))
        record["candidate_contexts"] = candidate_contexts
        selected_date = select_in_window_publication_date(record, start_date, end_date)
        if selected_date is not None:
            record["published_date"] = selected_date
            retained.append(record)
        else:
            out_of_window.append(record)
    retained.sort(key=lambda item: int(item.get("pmid") or 0))
    packet["articles"] = retained
    packet["candidate_pmids"] = len(retained)
    packet["candidate_contexts"] = sum(len(item.get("candidate_contexts", [])) for item in retained)
    packet["postfetch_out_of_window_omitted"] = len(out_of_window)
    packet["metadata_refreshed_at"] = datetime.now().astimezone().isoformat()
    packet.setdefault("ncbi_requests", {})["metadata_refresh_efetch"] = requests
    packet["ncbi_requests"]["total"] = sum(
        int(value) for key, value in packet["ncbi_requests"].items() if key != "total"
    )
    save_json(path, packet)
    save_json(
        output_dir / "out_of_window_records.json",
        {"count": len(out_of_window), "records": out_of_window},
    )

    valid_pmids = {str(item.get("pmid")) for item in retained}
    article_by_pmid = {str(item.get("pmid")): item for item in retained}
    for filename in ("first_screen.json", "second_screen.json"):
        packet_path = output_dir / filename
        screen = load_json(packet_path, {})
        if not screen:
            continue
        screen["results"] = [
            item for item in screen.get("results", [])
            if str(item.get("pmid") or str(item.get("context_id", "")).split("|", 1)[0]) in valid_pmids
        ]
        if filename == "second_screen.json":
            for item in screen["results"]:
                article = article_by_pmid.get(str(item.get("pmid")), {})
                for key in ("pmcid", "published_date", "title", "authors", "journal", "pubmed_url"):
                    item[key] = article.get(key) or ("" if key != "authors" else [])
        if filename == "first_screen.json":
            screen["source_contexts"] = packet["candidate_contexts"]
            screen["pass"] = sum(item.get("decision") == "PASS" for item in screen["results"])
            screen["fail"] = sum(item.get("decision") == "FAIL" for item in screen["results"])
        else:
            screen["source_first_screen_pass"] = sum(
                item.get("decision") == "PASS"
                for item in load_json(output_dir / "first_screen.json", {}).get("results", [])
            )
            screen["include"] = sum(item.get("eligibility") == "INCLUDE" for item in screen["results"])
            screen["exclude"] = sum(item.get("eligibility") == "EXCLUDE" for item in screen["results"])
            screen["needs_full_text"] = sum(bool(item.get("needs_full_text")) for item in screen["results"])
            screen["pmcid_full_text_candidates"] = sum(
                bool(item.get("needs_full_text")) and bool(item.get("pmcid")) for item in screen["results"]
            )
        save_json(packet_path, screen)
    print(f"Refreshed {len(retained)} candidate records with {requests} NCBI EFetch calls; omitted {len(out_of_window)} truly out-of-window records.")
    return packet


def context_id(pmid: str, exposure: str, cancer: str) -> str:
    return f"{pmid}|{exposure}|{cancer}"


def first_screen(output_dir: Path, batch_size: int = 20, force: bool = False) -> dict[str, Any]:
    output_path = output_dir / "first_screen.json"
    progress_path = output_dir / "first_screen_progress.json"
    candidates = load_json(output_dir / "candidates.json", {})
    articles = candidates.get("articles", [])
    if not articles:
        packet = {
            "schema_version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "source_candidates": 0,
            "source_contexts": 0,
            "pass": 0,
            "fail": 0,
            "usage": empty_usage(os.getenv("MONTHLY_SCREEN_MODEL", "gpt-5.6-sol")),
            "results": [],
        }
        save_json(output_path, packet)
        print("No unsaved PubMed candidates were found; first screen is empty.")
        return packet

    expected_context_ids = {
        context_id(str(article.get("pmid") or ""), item["exposure"], item["cancer"])
        for article in articles for item in article.get("candidate_contexts", [])
    }
    existing_packet = {} if force else load_json(output_path, {})
    existing_results = {
        item["context_id"]: item for item in existing_packet.get("results", [])
        if item.get("context_id") in expected_context_ids
    }
    if existing_packet and set(existing_results) == expected_context_ids:
        print(f"Using complete existing first-screen packet: {output_path}")
        return existing_packet

    client, model = configure_cornell()
    progress_packet = {} if force else load_json(progress_path, {})
    usage = progress_packet.get("usage") or existing_packet.get("usage") or empty_usage(model)
    progress = dict(existing_results)
    progress.update(progress_packet.get("results_by_context", {}))
    pending_articles = []
    for article in articles:
        pmid = str(article.get("pmid") or "")
        pending_contexts = [
            item
            for item in article.get("candidate_contexts", [])
            if context_id(pmid, item["exposure"], item["cancer"]) not in progress
        ]
        if pending_contexts:
            pending_articles.append({**article, "candidate_contexts": pending_contexts})
    batches = [
        pending_articles[offset : offset + batch_size]
        for offset in range(0, len(pending_articles), batch_size)
    ]

    def screen_batch(batch_number: int, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact_articles = []
        expected: dict[str, dict[str, str]] = {}
        for article in batch:
            pmid = str(article.get("pmid") or "")
            contexts = []
            for item in article.get("candidate_contexts", []):
                cid = context_id(pmid, item["exposure"], item["cancer"])
                context = {
                    "context_id": cid,
                    "exposure": item["exposure"],
                    "cancer": item["cancer"],
                    "outcome": "Incidence",
                }
                contexts.append(context)
                expected[cid] = context
            compact_articles.append(
                {
                    "pmid": pmid,
                    "title": article.get("title", ""),
                    "abstract": str(article.get("abstract", ""))[:9000],
                    "mesh": article.get("mesh", []),
                    "contexts": contexts,
                }
            )

        prompt = FIRST_SCREEN_INSTRUCTIONS + "\n\nARTICLES:\n" + json.dumps(
            compact_articles, ensure_ascii=False, separators=(",", ":")
        )
        for validation_attempt in range(2):
            payload = cornell_json_call(client, model, FIRST_SCREEN_SYSTEM, prompt, usage)
            returned = {}
            for item in payload.get("results", []):
                cid = str(item.get("context_id") or "")
                if cid in expected:
                    decision = str(item.get("decision") or "PASS").strip().upper()
                    returned[cid] = {
                        **expected[cid],
                        "decision": "FAIL" if decision == "FAIL" else "PASS",
                        "reason": re.sub(r"\s+", " ", str(item.get("reason") or "")).strip(),
                    }
            missing = set(expected) - set(returned)
            if not missing:
                return list(returned.values())
        raise RuntimeError(
            f"First-screen batch {batch_number} omitted {len(missing)} of {len(expected)} contexts"
        )

    results_by_context: dict[str, dict[str, Any]] = dict(progress)
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(screen_batch, index, batch): index
            for index, batch in enumerate(batches, start=1)
        }
        for future in concurrent.futures.as_completed(futures):
            for item in future.result():
                results_by_context[item["context_id"]] = item
            completed += 1
            save_json(
                progress_path,
                {
                    "updated_at": datetime.now().astimezone().isoformat(),
                    "usage": usage,
                    "results_by_context": results_by_context,
                },
            )
            if completed % 10 == 0 or completed == len(batches):
                print(
                    f"First-screen progress: {completed}/{len(batches)} batches; "
                    f"{len(results_by_context)} contexts; cost=${usage['calculated_cost_usd']:.6f}",
                    flush=True,
                )

    results = list(results_by_context.values())
    results.sort(key=lambda item: item["context_id"])
    packet = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "source_candidates": len(articles),
        "source_contexts": sum(len(article.get("candidate_contexts", [])) for article in articles),
        "pass": sum(item["decision"] == "PASS" for item in results),
        "fail": sum(item["decision"] == "FAIL" for item in results),
        "usage": usage,
        "results": results,
    }
    save_json(output_path, packet)
    if progress_path.exists():
        progress_path.unlink()
    print(json.dumps({key: value for key, value in packet.items() if key != "results"}, indent=2))
    return packet


EXCLUSION_CODES = {
    "S2-REVIEW",
    "S2-NONPRIMARY",
    "S2-ANIMAL",
    "S2-EXPOSURE-MISMATCH",
    "S2-COMPOUND",
    "S2-CANCER-MISMATCH",
    "S2-WRONG-OUTCOME",
    "S2-POSTDIAGNOSIS",
    "S2-BENIGN-ONLY",
    "S2-GENETIC-FOCUS",
    "S2-DIAGNOSTIC-MECHANISTIC",
    "S2-NO-TARGET-ESTIMATE",
    "S2-DUPLICATE",
}

JBI_TOTALS = {"cohort": 11, "case_control": 10, "cross_sectional": 8, "rct": 13}


def normalise_jbi(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    checklist_type = str(raw.get("checklist_type") or "cross_sectional").lower()
    if checklist_type not in JBI_TOTALS:
        checklist_type = "cross_sectional"
    total = JBI_TOTALS[checklist_type]
    supplied = raw.get("answers") if isinstance(raw.get("answers"), dict) else {}
    answers = {}
    for index in range(1, total + 1):
        answer = str(supplied.get(f"q{index}") or "Unclear").strip().lower()
        answers[f"q{index}"] = {
            "yes": "Yes",
            "no": "No",
            "na": "NA",
            "n/a": "NA",
            "unclear": "Unclear",
        }.get(answer, "Unclear")
    denominator = total - sum(answer == "NA" for answer in answers.values())
    score = round(100 * sum(answer == "Yes" for answer in answers.values()) / denominator, 1) if denominator else 0.0
    grade = "Good" if score > 80 else "Moderate" if score >= 51 else "Fair"
    return {
        "checklist_type": checklist_type,
        "answers": answers,
        "score_percent": score,
        "grade": grade,
    }


def second_screen(output_dir: Path, batch_size: int = 8, force: bool = False) -> dict[str, Any]:
    output_path = output_dir / "second_screen.json"
    progress_path = output_dir / "second_screen_progress.json"
    candidates = load_json(output_dir / "candidates.json", {})
    first_packet = load_json(output_dir / "first_screen.json", {})
    passing = {
        item["context_id"]: item
        for item in first_packet.get("results", [])
        if item.get("decision") == "PASS"
    }
    if not passing:
        packet = {
            "schema_version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "source_first_screen_pass": 0,
            "include": 0,
            "exclude": 0,
            "needs_full_text": 0,
            "pmcid_full_text_candidates": 0,
            "usage": empty_usage(os.getenv("MONTHLY_SCREEN_MODEL", "gpt-5.6-sol")),
            "results": [],
        }
        save_json(output_path, packet)
        print("No contexts passed the first screen; second screen is empty.")
        return packet

    expected_context_ids = set(passing)
    existing_packet = {} if force else load_json(output_path, {})
    existing_results = {
        item["context_id"]: item for item in existing_packet.get("results", [])
        if item.get("context_id") in expected_context_ids
    }
    if existing_packet and set(existing_results) == expected_context_ids:
        print(f"Using complete existing second-screen packet: {output_path}")
        return existing_packet

    articles_by_pmid = {str(article.get("pmid")): article for article in candidates.get("articles", [])}
    contexts_by_pmid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in passing.values():
        pmid = item["context_id"].split("|", 1)[0]
        contexts_by_pmid[pmid].append(item)

    client, model = configure_cornell()
    progress_packet = {} if force else load_json(progress_path, {})
    usage = progress_packet.get("usage") or existing_packet.get("usage") or empty_usage(model)
    progress = dict(existing_results)
    progress.update(progress_packet.get("results_by_context", {}))
    pending_articles = []
    for pmid, contexts in contexts_by_pmid.items():
        pending_contexts = [item for item in contexts if item["context_id"] not in progress]
        if pending_contexts:
            pending_articles.append((articles_by_pmid[pmid], pending_contexts))
    batches = [
        pending_articles[offset : offset + batch_size]
        for offset in range(0, len(pending_articles), batch_size)
    ]

    def screen_batch(batch_number: int, batch: list[tuple[dict[str, Any], list[dict[str, Any]]]]) -> list[dict[str, Any]]:
        compact_articles = []
        expected: dict[str, dict[str, Any]] = {}
        for article, contexts in batch:
            compact_contexts = []
            for context in contexts:
                cid = context["context_id"]
                expected[cid] = {
                    "context_id": cid,
                    "pmid": str(article.get("pmid") or ""),
                    "pmcid": article.get("pmcid") or "",
                    "published_date": article.get("published_date") or "Unknown",
                    "title": article.get("title") or "",
                    "authors": article.get("authors") or [],
                    "journal": article.get("journal") or "",
                    "pubmed_url": article.get("pubmed_url") or "",
                    "exposure": context["exposure"],
                    "cancer": context["cancer"],
                    "outcome": "Incidence",
                    "first_screen_reason": context.get("reason") or "",
                }
                compact_contexts.append(
                    {
                        "context_id": cid,
                        "exposure": context["exposure"],
                        "cancer": context["cancer"],
                        "outcome": "Incidence",
                    }
                )
            compact_articles.append(
                {
                    "pmid": article.get("pmid"),
                    "pmcid": article.get("pmcid"),
                    "published_date": article.get("published_date"),
                    "title": article.get("title"),
                    "abstract": str(article.get("abstract") or "")[:12000],
                    "mesh": article.get("mesh", []),
                    "publication_types": article.get("publication_types", []),
                    "contexts": compact_contexts,
                }
            )

        prompt = SECOND_SCREEN_INSTRUCTIONS + "\n\nARTICLES:\n" + json.dumps(
            compact_articles, ensure_ascii=False, separators=(",", ":")
        )
        missing: set[str] = set(expected)
        for validation_attempt in range(2):
            payload = cornell_json_call(client, model, SECOND_SCREEN_SYSTEM, prompt, usage)
            returned = {}
            invalid = []
            for item in payload.get("results", []):
                cid = str(item.get("context_id") or "")
                if cid not in expected:
                    continue
                eligibility = str(item.get("eligibility") or "").strip().upper()
                exclusion_code = item.get("exclusion_code")
                if eligibility not in {"INCLUDE", "EXCLUDE"}:
                    invalid.append(cid)
                    continue
                if eligibility == "EXCLUDE" and exclusion_code not in EXCLUSION_CODES:
                    invalid.append(cid)
                    continue
                jbi = normalise_jbi(item.get("jbi")) if eligibility == "INCLUDE" else None
                abstract_sufficient = bool(item.get("abstract_sufficient_for_meta")) if eligibility == "INCLUDE" else False
                returned[cid] = {
                    **expected[cid],
                    "eligibility": eligibility,
                    "exclusion_code": exclusion_code if eligibility == "EXCLUDE" else None,
                    "reason": re.sub(r"\s+", " ", str(item.get("reason") or "")).strip(),
                    "is_mendelian_randomization": bool(item.get("is_mendelian_randomization")),
                    "abstract_sufficient_for_meta": abstract_sufficient,
                    "missing_quantitative_fields": item.get("missing_quantitative_fields") or [],
                    "needs_full_text": bool(
                        eligibility == "INCLUDE"
                        and (not abstract_sufficient or jbi["grade"] != "Good")
                    ),
                    "extraction": item.get("extraction") if eligibility == "INCLUDE" else None,
                    "jbi": jbi,
                }
            missing = set(expected) - set(returned)
            if not missing and not invalid:
                return list(returned.values())
        raise RuntimeError(
            f"Second-screen batch {batch_number} omitted/invalidated {len(missing)} of {len(expected)} contexts"
        )

    results_by_context: dict[str, dict[str, Any]] = dict(progress)
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(screen_batch, index, batch): index
            for index, batch in enumerate(batches, start=1)
        }
        for future in concurrent.futures.as_completed(futures):
            for item in future.result():
                results_by_context[item["context_id"]] = item
            completed += 1
            save_json(
                progress_path,
                {
                    "updated_at": datetime.now().astimezone().isoformat(),
                    "usage": usage,
                    "results_by_context": results_by_context,
                },
            )
            if completed % 5 == 0 or completed == len(batches):
                print(
                    f"Second-screen progress: {completed}/{len(batches)} batches; "
                    f"{len(results_by_context)} contexts; cost=${usage['calculated_cost_usd']:.6f}",
                    flush=True,
                )

    results = sorted(results_by_context.values(), key=lambda item: item["context_id"])
    packet = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "source_first_screen_pass": len(passing),
        "include": sum(item["eligibility"] == "INCLUDE" for item in results),
        "exclude": sum(item["eligibility"] == "EXCLUDE" for item in results),
        "needs_full_text": sum(item.get("needs_full_text", False) for item in results),
        "pmcid_full_text_candidates": sum(
            item.get("needs_full_text", False) and bool(item.get("pmcid")) for item in results
        ),
        "usage": usage,
        "results": results,
    }
    save_json(output_path, packet)
    if progress_path.exists():
        progress_path.unlink()
    print(json.dumps({key: value for key, value in packet.items() if key != "results"}, indent=2))
    return packet


def one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def write_reports(output_dir: Path, report_dir: Path) -> dict[str, Any]:
    candidates = load_json(output_dir / "candidates.json", {})
    first_packet = load_json(output_dir / "first_screen.json", {})
    second_packet = load_json(output_dir / "second_screen.json", {})
    if not candidates or not first_packet or not second_packet:
        raise RuntimeError("Candidate, first-screen, and second-screen packets are required")

    articles = candidates.get("articles", [])
    article_by_pmid = {str(article.get("pmid")): article for article in articles}
    first_failures = [item for item in first_packet.get("results", []) if item.get("decision") == "FAIL"]
    second_exclusions = [
        item for item in second_packet.get("results", []) if item.get("eligibility") == "EXCLUDE"
    ]
    included = [item for item in second_packet.get("results", []) if item.get("eligibility") == "INCLUDE"]

    exclusions = []
    for item in first_failures:
        pmid = item["context_id"].split("|", 1)[0]
        article = article_by_pmid.get(pmid, {})
        exclusions.append(
            {
                "pmid": pmid,
                "published_date": article.get("published_date") or "Unknown",
                "title": article.get("title") or "",
                "exposure": item.get("exposure"),
                "cancer": item.get("cancer"),
                "screen_layer": "first",
                "exclusion_code": "S1-NOT-DIRECT",
                "reason": item.get("reason") or "Not a direct exposure-cancer incidence match.",
            }
        )
    for item in second_exclusions:
        exclusions.append(
            {
                "pmid": item.get("pmid"),
                "published_date": item.get("published_date") or "Unknown",
                "title": item.get("title") or "",
                "exposure": item.get("exposure"),
                "cancer": item.get("cancer"),
                "screen_layer": "second",
                "exclusion_code": item.get("exclusion_code"),
                "reason": item.get("reason") or "Excluded by the detailed screen.",
            }
        )
    exclusions.sort(key=lambda item: (str(item["pmid"]), str(item["exposure"]), str(item["cancer"])))
    save_json(output_dir / "exclusions.json", {"count": len(exclusions), "records": exclusions})

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "newStudies.txt"
    candidate_path = report_dir / "newCandidatePMIDs.txt"
    exclusion_path = report_dir / "newStudyExclusions.txt"

    contexts_by_pmid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in included:
        contexts_by_pmid[str(item["pmid"])].append(item)

    report_lines = [
        "MetaFemina new-study report",
        "===========================",
        f"Publication-date search window: {candidates.get('publication_date_start')} through {candidates.get('publication_date_end')}",
        "Cancer types: Breast cancer; Ovarian cancer; Uterine cancer",
        "Outcome: Incidence",
        f"Listed exposures searched: {candidates.get('listed_exposures')}",
        f"Previously saved unique PMIDs omitted globally: {candidates.get('saved_pmids_omitted')}",
        f"Unsaved candidate PMIDs indexed: {candidates.get('candidate_pmids')}",
        f"First-screen passing contexts: {first_packet.get('pass')}",
        f"Second-screen eligible contexts: {len(included)}",
        f"Second-screen eligible unique PMIDs: {len(contexts_by_pmid)}",
        f"Eligible contexts needing full text: {sum(item.get('needs_full_text', False) for item in included)}",
        f"Eligible contexts with PMCID: {sum(bool(item.get('pmcid')) for item in included)}",
        "",
        "IMPORTANT STATUS",
        "----------------",
        "This file was written after both relevance screens and before any PMC full-text retrieval, saved-result mutation, or plot/workbook regeneration.",
        "Missing effect sizes or p-values were not used as exclusion reasons.",
        "",
        "PRELIMINARILY ELIGIBLE NEW STUDIES",
        "-----------------------------------",
    ]
    for pmid in sorted(contexts_by_pmid, key=int):
        contexts = contexts_by_pmid[pmid]
        first = contexts[0]
        report_lines.extend(
            [
                "",
                f"PMID: {pmid}",
                f"Published date: {first.get('published_date') or 'Unknown'}",
                f"PMCID: {first.get('pmcid') or 'None found'}",
                f"Title: {one_line(first.get('title')) or 'Not available from PubMedArticle XML'}",
                f"Authors: {', '.join(first.get('authors') or []) or 'Not available'}",
                f"Journal: {one_line(first.get('journal')) or 'Not available'}",
                f"PubMed: {first.get('pubmed_url') or ''}",
            ]
        )
        for context in contexts:
            report_lines.extend(
                [
                    f"  Context: {context.get('exposure')} | {context.get('cancer')} | Incidence",
                    f"  Second-screen reason: {one_line(context.get('reason'))}",
                    f"  Abstract sufficient for meta-analysis: {'Yes' if context.get('abstract_sufficient_for_meta') else 'No'}",
                    f"  Preliminary JBI: {context.get('jbi', {}).get('grade')} ({context.get('jbi', {}).get('score_percent')}%)",
                    f"  Mendelian randomization: {'Yes' if context.get('is_mendelian_randomization') else 'No'}",
                    f"  Full text required: {'Yes' if context.get('needs_full_text') else 'No'}",
                    f"  Missing quantitative fields: {', '.join(map(str, context.get('missing_quantitative_fields') or [])) or 'None'}",
                ]
            )

    report_lines.extend(
        [
            "",
            "AUDIT FILES",
            "-----------",
            f"All unsaved candidate PMIDs: {candidate_path.name}",
            f"All first- and second-screen exclusions: {exclusion_path.name}",
            f"Machine-readable audit packet: {output_dir}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    candidate_lines = [
        "Unsaved PubMed candidates before relevance screening",
        "====================================================",
        "PMID | Published date | Candidate contexts | Title",
    ]
    for article in sorted(articles, key=lambda item: int(item.get("pmid") or 0)):
        contexts = "; ".join(
            f"{item['exposure']} / {item['cancer']} / Incidence"
            for item in article.get("candidate_contexts", [])
        )
        candidate_lines.append(
            f"{article.get('pmid')} | {article.get('published_date') or 'Unknown'} | {contexts} | {one_line(article.get('title'))}"
        )
    candidate_path.write_text("\n".join(candidate_lines) + "\n", encoding="utf-8")

    exclusion_lines = [
        "MetaFemina new-study exclusion ledger",
        "=======================================",
        "PMID | Published date | Screen | Code | Exposure | Cancer | Reason",
    ]
    exclusion_lines.extend(
        f"{item['pmid']} | {item['published_date']} | {item['screen_layer']} | {item['exclusion_code']} | "
        f"{item['exposure']} | {item['cancer']} | {one_line(item['reason'])}"
        for item in exclusions
    )
    exclusion_path.write_text("\n".join(exclusion_lines) + "\n", encoding="utf-8")

    summary = {
        "new_studies_report": str(report_path),
        "candidate_pmids_report": str(candidate_path),
        "exclusion_report": str(exclusion_path),
        "eligible_contexts": len(included),
        "eligible_pmids": len(contexts_by_pmid),
        "exclusion_contexts": len(exclusions),
    }
    print(json.dumps(summary, indent=2))
    return summary


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def jats_to_text(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    blocks = []
    allowed = {"article-title", "title", "p", "th", "td", "caption"}
    for element in root.iter():
        if local_name(element.tag) not in allowed:
            continue
        value = one_line(" ".join(element.itertext()))
        if value and (not blocks or value != blocks[-1]):
            blocks.append(value)
    return "\n".join(blocks)


def fetch_pmc_full_text(pmcid: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with Entrez.efetch(db="pmc", id=pmcid, retmode="xml") as handle:
                return handle.read()
        except Exception as exc:  # pragma: no cover - network retry path
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"PMC EFetch failed for {pmcid}: {last_error}")


def full_text_review(output_dir: Path, force: bool = False) -> dict[str, Any]:
    output_path = output_dir / "full_text_review.json"
    progress_path = output_dir / "full_text_review_progress.json"
    if output_path.exists() and not force:
        print(f"Using existing full-text review packet: {output_path}")
        return load_json(output_path, {})

    second_packet = load_json(output_dir / "second_screen.json", {})
    contexts = [
        item
        for item in second_packet.get("results", [])
        if item.get("eligibility") == "INCLUDE" and item.get("needs_full_text") and item.get("pmcid")
    ]
    if not contexts:
        packet = {"schema_version": 1, "contexts": 0, "results": [], "ncbi_requests": 0}
        save_json(output_path, packet)
        return packet

    api_key_status = configure_entrez()
    full_text_dir = output_dir / "full_text"
    full_text_dir.mkdir(parents=True, exist_ok=True)
    contexts_by_pmcid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in contexts:
        contexts_by_pmcid[str(item["pmcid"])].append(item)

    source_texts = {}
    source_status = {}
    ncbi_requests = 0
    for pmcid in sorted(contexts_by_pmcid):
        text_path = full_text_dir / f"{pmcid}.txt"
        if text_path.exists() and not force:
            text = text_path.read_text(encoding="utf-8")
        else:
            xml_bytes = fetch_pmc_full_text(pmcid)
            ncbi_requests += 1
            text = jats_to_text(xml_bytes)
            text_path.write_text(text + "\n", encoding="utf-8")
        source_texts[pmcid] = text
        source_status[pmcid] = "full_text" if len(text) >= 5000 else "partial_front_matter"
        print(
            f"PMC source ready: {pmcid} ({len(text):,} characters; {source_status[pmcid]})",
            flush=True,
        )

    client, model = configure_cornell()
    progress_packet = {} if force else load_json(progress_path, {})
    usage = progress_packet.get("usage") or empty_usage(model)
    results_by_context = progress_packet.get("results_by_context", {})

    def appraise_article(pmcid: str, article_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pending = [item for item in article_contexts if item["context_id"] not in results_by_context]
        if not pending:
            return []
        if source_status[pmcid] != "full_text":
            return [
                {
                    **item,
                    "full_text_status": (
                        "MR_SEPARATE" if item.get("is_mendelian_randomization") else "ELIGIBLE_NOT_POOLABLE"
                    ),
                    "exclusion_code": None,
                    "reason": (
                        "The PMC record currently contains only abstract/front matter, so no complete "
                        "full-text extraction or JBI upgrade was possible."
                    ),
                    "extraction": item.get("extraction") or {},
                    "jbi": item.get("jbi") or normalise_jbi({}),
                    "full_text_characters_reviewed": len(source_texts[pmcid]),
                    "pmc_source_status": source_status[pmcid],
                }
                for item in pending
            ]
        expected = {item["context_id"]: item for item in pending}
        compact_contexts = [
            {
                "context_id": item["context_id"],
                "pmid": item["pmid"],
                "pmcid": item["pmcid"],
                "title": item["title"],
                "exposure": item["exposure"],
                "cancer": item["cancer"],
                "outcome": "Incidence",
                "abstract_screen_reason": item["reason"],
            }
            for item in pending
        ]
        prompt = (
            FULL_TEXT_INSTRUCTIONS
            + "\n\nCONTEXTS:\n"
            + json.dumps(compact_contexts, ensure_ascii=False, separators=(",", ":"))
            + "\n\nFULL ARTICLE TEXT:\n"
            + source_texts[pmcid][:180000]
        )
        missing: set[str] = set(expected)
        for validation_attempt in range(2):
            payload = cornell_json_call(client, model, FULL_TEXT_SYSTEM, prompt, usage)
            returned = {}
            for item in payload.get("results", []):
                cid = str(item.get("context_id") or "")
                if cid not in expected:
                    continue
                status = re.sub(r"[^A-Z]+", "_", str(item.get("status") or "").strip().upper()).strip("_")
                status = {
                    "INCLUDE": "INCLUDE_META",
                    "INCLUDE_IN_META": "INCLUDE_META",
                    "ELIGIBLE_BUT_NOT_POOLABLE": "ELIGIBLE_NOT_POOLABLE",
                    "MENDELIAN_RANDOMIZATION": "MR_SEPARATE",
                    "MR": "MR_SEPARATE",
                }.get(status, status)
                if status not in {"INCLUDE_META", "ELIGIBLE_NOT_POOLABLE", "MR_SEPARATE", "EXCLUDE"}:
                    print(f"Invalid full-text status for {cid}: {item.get('status')!r}", flush=True)
                    continue
                exclusion_code = item.get("exclusion_code")
                if status == "EXCLUDE" and exclusion_code not in EXCLUSION_CODES:
                    print(f"Invalid full-text exclusion code for {cid}: {exclusion_code!r}", flush=True)
                    continue
                jbi = normalise_jbi(item.get("jbi"))
                # Enforce protocol status from extracted completeness and JBI.
                extraction = item.get("extraction") if isinstance(item.get("extraction"), dict) else {}
                has_poolable = all(
                    extraction.get(field) is not None
                    for field in ("effect_size", "ci_lower", "ci_upper")
                )
                if status == "INCLUDE_META" and (not has_poolable or jbi["grade"] != "Good"):
                    status = "ELIGIBLE_NOT_POOLABLE"
                returned[cid] = {
                    **expected[cid],
                    "full_text_status": status,
                    "exclusion_code": exclusion_code if status == "EXCLUDE" else None,
                    "reason": one_line(item.get("reason")),
                    "extraction": extraction,
                    "jbi": jbi,
                    "full_text_characters_reviewed": min(len(source_texts[pmcid]), 180000),
                    "pmc_source_status": source_status[pmcid],
                }
            missing = set(expected) - set(returned)
            if not missing:
                return list(returned.values())
        raise RuntimeError(f"Full-text appraisal for {pmcid} omitted {len(missing)} contexts")

    completed = 0
    items = sorted(contexts_by_pmcid.items())
    # Full texts are expensive calls; sequential processing guarantees that each
    # completed result and its usage are checkpointed before the next call.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = {
            executor.submit(appraise_article, pmcid, article_contexts): pmcid
            for pmcid, article_contexts in items
        }
        for future in concurrent.futures.as_completed(futures):
            for item in future.result():
                results_by_context[item["context_id"]] = item
            completed += 1
            save_json(
                progress_path,
                {
                    "updated_at": datetime.now().astimezone().isoformat(),
                    "usage": usage,
                    "results_by_context": results_by_context,
                },
            )
            print(
                f"Full-text progress: {completed}/{len(items)} PMC articles; "
                f"{len(results_by_context)} contexts; cost=${usage['calculated_cost_usd']:.6f}",
                flush=True,
            )

    results = sorted(results_by_context.values(), key=lambda item: item["context_id"])
    status_counts = defaultdict(int)
    for item in results:
        status_counts[item["full_text_status"]] += 1
    packet = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "ncbi_api_key_status": api_key_status,
        "ncbi_requests": ncbi_requests,
        "pmc_articles": len(items),
        "contexts": len(results),
        "status_counts": dict(status_counts),
        "usage": usage,
        "results": results,
    }
    save_json(output_path, packet)
    if progress_path.exists():
        progress_path.unlink()
    print(json.dumps({key: value for key, value in packet.items() if key != "results"}, indent=2))
    return packet


FULL_TEXT_PROTOCOL_OVERRIDES = {
    # Full text explicitly states that ovarian cancer was not among the four
    # alcohol-linked cancers. Keeping this as an auditable deterministic
    # override prevents "missing statistics" from obscuring a true mismatch.
    "42094023|Alcohol|Ovarian cancer": {
        "full_text_status": "EXCLUDE",
        "exclusion_code": "S2-NO-TARGET-ESTIMATE",
        "reason": (
            "Full text states that the alcohol-linked cancers were liver, colorectal, oral, "
            "and breast cancer, so it provides no alcohol–ovarian cancer incidence analysis."
        ),
    },
}


def finalize_evidence(output_dir: Path, report_dir: Path) -> dict[str, Any]:
    """Combine abstract and PMC decisions into one final, auditable disposition."""
    candidates = load_json(output_dir / "candidates.json", {})
    second = load_json(output_dir / "second_screen.json", {})
    full_text = load_json(output_dir / "full_text_review.json", {})
    if not second:
        raise RuntimeError("Second-screen results are required before finalization")
    full_by_context = {
        item["context_id"]: item for item in full_text.get("results", [])
    }
    final_results = []
    for item in second.get("results", []):
        if item.get("eligibility") != "INCLUDE":
            continue
        context = item["context_id"]
        if context in full_by_context:
            final = dict(full_by_context[context])
            # Full-text packets may have been created before a PubMed metadata
            # refresh. Always carry forward the reconciled second-screen fields.
            for key in ("pmcid", "published_date", "title", "authors", "journal", "pubmed_url"):
                final[key] = item.get(key)
        elif item.get("is_mendelian_randomization"):
            final = {
                **item,
                "full_text_status": "MR_SEPARATE",
                "exclusion_code": None,
                "reason": "Eligible Mendelian-randomization evidence is retained separately from conventional studies.",
            }
        elif item.get("abstract_sufficient_for_meta") and item.get("jbi", {}).get("grade") == "Good":
            final = {
                **item,
                "full_text_status": "INCLUDE_META",
                "exclusion_code": None,
                "reason": "The abstract provides a usable estimate and the abstract-level JBI grade is Good.",
            }
        else:
            final = {
                **item,
                "full_text_status": "ELIGIBLE_NOT_POOLABLE",
                "exclusion_code": None,
                "reason": (
                    "The study remains relevant, but no complete Good-quality quantitative extraction "
                    "could be verified from the available abstract and accessible full text."
                ),
            }
        if context in FULL_TEXT_PROTOCOL_OVERRIDES:
            final.update(FULL_TEXT_PROTOCOL_OVERRIDES[context])
        final_results.append(final)

    final_results.sort(key=lambda value: value["context_id"])
    counts = defaultdict(int)
    for item in final_results:
        counts[item["full_text_status"]] += 1
    packet = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "publication_date_start": candidates.get("publication_date_start"),
        "publication_date_end": candidates.get("publication_date_end"),
        "counts": dict(counts),
        "results": final_results,
    }
    save_json(output_dir / "final_screening.json", packet)
    write_final_reports(output_dir, report_dir, packet)
    return packet


def write_final_reports(output_dir: Path, report_dir: Path, final_packet: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    final_results = final_packet.get("results", [])
    report_path = report_dir / "newStudies.txt"
    preliminary = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    marker = "\nFINAL DISPOSITION AFTER FULL-TEXT REVIEW\n"
    if marker in preliminary:
        preliminary = preliminary.split(marker, 1)[0].rstrip() + "\n"
    lines = [
        "",
        "FINAL DISPOSITION AFTER FULL-TEXT REVIEW",
        "----------------------------------------",
        "Only INCLUDE_META records were added to the conventional saved meta-analysis.",
        "MR_SEPARATE records were retained in MR.txt and were not pooled with conventional studies.",
        "Missing effect sizes or p-values were not used as exclusion reasons.",
    ]
    for item in final_results:
        extraction = item.get("extraction") or {}
        jbi = item.get("jbi") or {}
        if all(extraction.get(key) is not None for key in ("effect_size", "ci_lower", "ci_upper")):
            estimate_text = (
                f"{extraction.get('effect_type') or 'Effect'} {extraction.get('effect_size')} "
                f"(95% CI {extraction.get('ci_lower')}–{extraction.get('ci_upper')})"
            )
        elif extraction.get("effect_size") is not None:
            estimate_text = f"Incomplete estimate {extraction.get('effect_size')}; no usable confidence interval verified"
        else:
            estimate_text = "No usable estimate verified"
        lines.extend(
            [
                "",
                f"PMID: {item.get('pmid')}",
                f"Context: {item.get('exposure')} | {item.get('cancer')} | Incidence",
                f"Published date: {item.get('published_date') or 'Unknown'}",
                f"PMCID: {item.get('pmcid') or 'None found'}",
                f"Title: {one_line(item.get('title'))}",
                f"Final status: {item.get('full_text_status')}",
                f"Reason: {one_line(item.get('reason'))}",
                f"JBI: {jbi.get('grade') or 'Not applicable'} ({jbi.get('score_percent', 'NA')}%)",
                f"Extracted estimate: {estimate_text}",
            ]
        )
    report_path.write_text(preliminary.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    # A stable filename makes every dated monthly directory immediately
    # understandable without changing the pre-retrieval newStudies contract.
    (report_dir / "summary.txt").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")

    # Add exclusions established only after full-text retrieval to the detailed ledger.
    exclusion_path = report_dir / "newStudyExclusions.txt"
    existing = exclusion_path.read_text(encoding="utf-8") if exclusion_path.exists() else ""
    for item in final_results:
        if item.get("full_text_status") != "EXCLUDE":
            continue
        line = (
            f"{item.get('pmid')} | {item.get('published_date') or 'Unknown'} | full-text | "
            f"{item.get('exclusion_code')} | {item.get('exposure')} | {item.get('cancer')} | "
            f"{one_line(item.get('reason'))}"
        )
        if line not in existing:
            existing = existing.rstrip() + "\n" + line + "\n"
    exclusion_path.write_text(existing, encoding="utf-8")
    append_mr_report(report_dir / "MR.txt", final_results, final_packet)


def append_mr_report(path: Path, final_results: list[dict[str, Any]], packet: dict[str, Any]) -> None:
    mr_results = [item for item in final_results if item.get("full_text_status") == "MR_SEPARATE"]
    if not mr_results:
        return
    existing = path.read_text(encoding="utf-8") if path.exists() else (
        "Mendelian-randomization studies identified by MetaFemina\n"
        "========================================================\n"
    )
    marker = (
        f"Monthly evidence update: {packet.get('publication_date_start')} through "
        f"{packet.get('publication_date_end')}"
    )
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n"
    unique_pmids = {str(item.get("pmid")) for item in mr_results}
    lines = [
        "",
        marker,
        "-" * len(marker),
        f"New MR records: {len(unique_pmids)} unique articles; {len(mr_results)} exposure-cancer contexts.",
        "These studies are retained as original human evidence but are not pooled with conventional observational studies.",
        "The displayed JBI score is not treated as a valid MR appraisal because MetaFemina does not yet implement an MR-specific checklist.",
    ]
    for item in mr_results:
        extraction = item.get("extraction") or {}
        lines.extend(
            [
                "",
                f"PMID: {item.get('pmid')}; PMCID: {item.get('pmcid') or 'None found'}",
                f"Title: {one_line(item.get('title'))}",
                f"Context: {item.get('exposure')} | {item.get('cancer')} | Incidence",
                f"Published date: {item.get('published_date') or 'Unknown'}",
                f"Estimate: {extraction.get('effect_type')} {extraction.get('effect_size')} "
                f"(95% CI {extraction.get('ci_lower')}–{extraction.get('ci_upper')}); "
                f"p={extraction.get('p_value')}",
                f"Comparison: {one_line(extraction.get('comparison_type'))}",
                f"Reason kept separate: {one_line(item.get('reason'))}",
                f"PubMed: {item.get('pubmed_url') or f'https://pubmed.ncbi.nlm.nih.gov/{item.get('pmid')}/'}",
            ]
        )
    path.write_text(existing.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def json_compatible(value: Any) -> Any:
    """Convert pandas/numpy scalar values returned by meta_analysis to JSON."""
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def study_row(item: dict[str, Any]) -> dict[str, Any]:
    extraction = item.get("extraction") or {}
    jbi = item.get("jbi") or {}
    authors = item.get("authors") or []
    first_author = authors[0] if authors else "Unknown"
    year_match = re.search(r"\b(19|20)\d{2}\b", str(item.get("published_date") or ""))
    effect = extraction.get("effect_size")
    lower = extraction.get("ci_lower")
    upper = extraction.get("ci_upper")
    se = (
        round((float(upper) - float(lower)) / 3.92, 16)
        if lower is not None and upper is not None
        else None
    )
    supporting = one_line(extraction.get("supporting_text"))
    raw_measurement = one_line(extraction.get("exposure_measurement_type")).lower()
    if any(term in raw_measurement for term in ("diet", "questionnaire", "self-report", "recall")):
        measurement_type = "dietary_intake"
    elif any(term in raw_measurement for term in ("biospecimen", "blood", "serum", "plasma", "urine")):
        measurement_type = "human_biospecimen"
    else:
        measurement_type = "unclear"
    return {
        "Study": f"{first_author} et al. ({year_match.group(0) if year_match else 'Unknown'}) [PMID: {item.get('pmid')}]",
        "PMID": str(item.get("pmid")),
        "Effect Size": effect,
        "Lower CI": lower,
        "Upper CI": upper,
        "Population": "Human study population described in the cited article",
        "Reference": one_line(item.get("title")),
        "Authors": ", ".join(authors),
        "Journal": one_line(item.get("journal")),
        "Year": year_match.group(0) if year_match else "Unknown",
        "Link": item.get("pubmed_url") or f"https://pubmed.ncbi.nlm.nih.gov/{item.get('pmid')}/",
        "Effect Type": extraction.get("effect_type"),
        "SE": se,
        "Sample Size": extraction.get("total_n"),
        "Cases": extraction.get("cases"),
        "Estimated Cases": None,
        "Design": extraction.get("design"),
        "Timing": extraction.get("timing"),
        "Continent": extraction.get("continent"),
        "Stage": None,
        "Quality %": jbi.get("score_percent"),
        "Quality Score": jbi.get("grade"),
        "comparison_type": extraction.get("comparison_type"),
        "JBI": jbi.get("answers") or {},
        "exposure_measurement_type": measurement_type,
        "exposure_measurement_supporting_text": supporting,
        "extraction_supporting_text": {
            "sample_size": supporting,
            "effect_size": supporting,
            "effect_direction": "",
            "p_value": str(extraction.get("p_value") or ""),
            "confidence_interval": f"95% CI {lower}-{upper}" if lower is not None and upper is not None else "",
            "outcome_definition": f"Incident {item.get('cancer')}",
            "exposure_definition": one_line(extraction.get("comparison_type")),
        },
    }


def apply_to_saved_results(output_dir: Path) -> dict[str, Any]:
    """Add only final Good, poolable, conventional studies and rebuild diagnostics."""
    import pandas as pd

    sys.path.insert(0, str(REPO_ROOT))
    import meta_analysis

    final_packet = load_json(output_dir / "final_screening.json", {})
    included = [
        item for item in final_packet.get("results", [])
        if item.get("full_text_status") == "INCLUDE_META"
    ]
    changes = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in included:
        grouped[(item["exposure"], item["cancer"])].append(item)

    for (exposure, cancer), items in grouped.items():
        safe_exposure = re.sub(r"[^a-zA-Z0-9]+", "_", exposure.lower()).strip("_")
        safe_cancer = re.sub(r"[^a-zA-Z0-9]+", "_", cancer.lower()).strip("_")
        cache_paths = [
            CACHE_DIR / safe_exposure / f"{safe_cancer}_incidence_true_{suffix}.json"
            for suffix in ("all", "core")
        ]
        existing_path = next((path for path in cache_paths if path.exists()), None)
        if not existing_path:
            changes.append({"exposure": exposure, "cancer": cancer, "status": "cache_not_found"})
            continue
        source_cache = load_json(existing_path, {})
        studies = list(source_cache.get("studies", []))
        window_start = final_packet.get("publication_date_start")
        window_end = final_packet.get("publication_date_end")
        recorded_added = {
            str(pmid)
            for update in source_cache.get("monthly_updates", [])
            if update.get("publication_date_start") == window_start
            and update.get("publication_date_end") == window_end
            for pmid in update.get("added_pmids", [])
        }
        index_by_pmid = {str(study.get("PMID")): index for index, study in enumerate(studies)}
        appended = []
        refreshed = []
        for item in items:
            pmid = str(item.get("pmid"))
            new_row = study_row(item)
            if pmid in index_by_pmid:
                index = index_by_pmid[pmid]
                if studies[index] != new_row:
                    studies[index] = new_row
                    refreshed.append(pmid)
                continue
            studies.append(new_row)
            index_by_pmid[pmid] = len(studies) - 1
            appended.append(pmid)
        if not appended and not refreshed:
            # Consolidate duplicate audit entries from an interrupted/replayed
            # run without recomputing an unchanged meta-analysis.
            for path in cache_paths:
                if not path.exists():
                    continue
                cache = load_json(path, {})
                other_updates = [
                    update for update in cache.get("monthly_updates", [])
                    if not (
                        update.get("publication_date_start") == window_start
                        and update.get("publication_date_end") == window_end
                    )
                ]
                if recorded_added:
                    other_updates.append(
                        {
                            "publication_date_start": window_start,
                            "publication_date_end": window_end,
                            "added_pmids": sorted(recorded_added),
                        }
                    )
                cache["monthly_updates"] = other_updates
                save_json(path, json_compatible(cache), indent=4, ensure_ascii=True)
            changes.append(
                {
                    "exposure": exposure,
                    "cancer": cancer,
                    "status": "previously_applied" if recorded_added else "already_present",
                    "added_pmids": sorted(recorded_added),
                }
            )
            continue

        frame = pd.DataFrame(studies)
        for column in ("Effect Size", "Lower CI", "Upper CI", "SE", "Cases", "Sample Size", "Estimated Cases"):
            if column in frame:
                frame[column] = pd.to_numeric(
                    frame[column].astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce"
                )
        result = meta_analysis.perform_meta_analysis(
            frame,
            cancer,
            exposure,
            outcome="Incidence",
            exclude_meta=True,
            df_all=frame,
            screening_stats=source_cache.get("screening_stats"),
        )
        if not result.get("success"):
            raise RuntimeError(f"Meta-analysis rebuild failed for {exposure}/{cancer}: {result}")
        for path in cache_paths:
            if not path.exists():
                continue
            cache = load_json(path, {})
            for key in (
                "studies", "summary_html", "headline", "screening_stats",
                "plot_url", "funnel_plot_url", "baujat_plot_url",
            ):
                cache[key] = studies if key == "studies" else result.get(key)
            cache["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            all_added = sorted(recorded_added | set(appended))
            updates = [
                update for update in cache.get("monthly_updates", [])
                if not (
                    update.get("publication_date_start") == window_start
                    and update.get("publication_date_end") == window_end
                )
            ]
            updates.append(
                {
                    "publication_date_start": window_start,
                    "publication_date_end": window_end,
                    "added_pmids": all_added,
                }
            )
            cache["monthly_updates"] = updates
            save_json(path, json_compatible(cache), indent=4, ensure_ascii=True)
        changes.append(
            {
                "exposure": exposure,
                "cancer": cancer,
                "status": "updated",
                "added_pmids": sorted(recorded_added | set(appended)),
                "refreshed_pmids": refreshed,
                "studies_after": len(result.get("studies", [])),
                "headline": result.get("headline"),
            }
        )
    packet = {"created_at": datetime.now().astimezone().isoformat(), "changes": changes}
    save_json(output_dir / "applied_changes.json", json_compatible(packet))
    print(json.dumps(packet, indent=2, default=str))
    return packet


def write_run_cost_report(output_dir: Path, report_dir: Path) -> Path:
    """Write per-run API usage separately from the scientific reports."""
    candidates = load_json(output_dir / "candidates.json", {})
    first = load_json(output_dir / "first_screen.json", {})
    second = load_json(output_dir / "second_screen.json", {})
    full_text = load_json(output_dir / "full_text_review.json", {})
    usages = [
        ("First relevance screen", first.get("usage") or {}),
        ("Second relevance screen", second.get("usage") or {}),
        ("PMC full-text extraction/JBI", full_text.get("usage") or {}),
    ]
    total_calls = sum(int(usage.get("calls") or 0) for _, usage in usages)
    total_input = sum(int(usage.get("input_tokens") or 0) for _, usage in usages)
    total_output = sum(int(usage.get("output_tokens") or 0) for _, usage in usages)
    total_reasoning = sum(int(usage.get("reasoning_tokens") or 0) for _, usage in usages)
    total_cost = sum(float(usage.get("calculated_cost_usd") or 0) for _, usage in usages)
    discovery_requests = int((candidates.get("ncbi_requests") or {}).get("total") or 0)
    pmc_requests = int(full_text.get("ncbi_requests") or 0)
    lines = [
        "MetaFemina monthly update API use and cost",
        "===========================================",
        f"Window: {candidates.get('publication_date_start')} through {candidates.get('publication_date_end')}",
        f"Model: {os.getenv('MONTHLY_SCREEN_MODEL', 'gpt-5.6-sol')}",
        "",
        "Cornell AI Gateway",
        "------------------",
    ]
    for label, usage in usages:
        lines.append(
            f"{label}: {int(usage.get('calls') or 0)} calls; "
            f"{int(usage.get('input_tokens') or 0)} input tokens; "
            f"{int(usage.get('output_tokens') or 0)} output tokens; "
            f"${float(usage.get('calculated_cost_usd') or 0):.6f}"
        )
    lines.extend(
        [
            f"Total: {total_calls} calls; {total_input} input tokens; {total_output} output tokens; "
            f"{total_reasoning} reasoning tokens; ${total_cost:.6f}",
            "",
            "NCBI E-utilities",
            "----------------",
            f"Discovery/metadata requests recorded: {discovery_requests}",
            f"PMC full-text requests recorded: {pmc_requests}",
            f"Total recorded NCBI requests: {discovery_requests + pmc_requests}",
            "Cost: $0.00 (NCBI does not charge a per-request fee)",
            "",
            "No API keys or secret values are written to this file.",
        ]
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "cost.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--previous-month", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--stage",
        choices=(
            "discover", "refresh-metadata", "first-screen", "second-screen",
            "report", "full-text", "finalize", "apply", "cost-report", "all",
        ),
        default="discover",
    )
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=REPO_ROOT.parent)
    parser.add_argument(
        "--monthly-report-subdir",
        action="store_true",
        help="write human-readable reports under REPORT_DIR/YYYY-MM-DD_YYYY-MM-DD",
    )
    args = parser.parse_args()
    if args.previous_month:
        args.start_date, args.end_date = previous_month()
    if not args.start_date or not args.end_date:
        parser.error("provide --start-date and --end-date, or use --previous-month")
    if args.output_dir is None:
        args.output_dir = DATA_DIR / "monthly_updates" / f"{args.start_date}_{args.end_date}"
    if args.monthly_report_subdir:
        args.report_dir = args.report_dir / f"{args.start_date}_{args.end_date}"
    return args


def main() -> int:
    args = parse_args()
    if args.stage == "all":
        discover(args.start_date, args.end_date, args.output_dir)
        first_screen(args.output_dir, batch_size=args.batch_size, force=args.force)
        second_screen(args.output_dir, batch_size=args.batch_size, force=args.force)
        # Preserve the requested pre-retrieval report before any full-text or
        # saved-result work changes the evidence state.
        write_reports(args.output_dir, args.report_dir)
        full_text_review(args.output_dir, force=args.force)
        finalize_evidence(args.output_dir, args.report_dir)
        apply_to_saved_results(args.output_dir)
        write_run_cost_report(args.output_dir, args.report_dir)
    elif args.stage == "discover":
        discover(args.start_date, args.end_date, args.output_dir)
    elif args.stage == "refresh-metadata":
        refresh_candidate_metadata(args.output_dir)
    elif args.stage == "first-screen":
        first_screen(args.output_dir, batch_size=args.batch_size, force=args.force)
    elif args.stage == "second-screen":
        second_screen(args.output_dir, batch_size=args.batch_size, force=args.force)
    elif args.stage == "report":
        write_reports(args.output_dir, args.report_dir)
    elif args.stage == "full-text":
        full_text_review(args.output_dir, force=args.force)
    elif args.stage == "finalize":
        finalize_evidence(args.output_dir, args.report_dir)
    elif args.stage == "apply":
        apply_to_saved_results(args.output_dir)
    elif args.stage == "cost-report":
        write_run_cost_report(args.output_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Monthly evidence update failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
