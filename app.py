from flask import Flask, render_template, request, jsonify, send_from_directory
import meta_analysis
import os
import pandas as pd
import numpy as np
import json
import hashlib
import re
import smtplib
import time
from email.message import EmailMessage
from functools import partial
from datetime import datetime

print = partial(print, flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, 'metafemina_runtime.log')

def log_event(message):
    """Write progress to stdout and the project refresh log."""
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}"
    
    # Hide verbose cache lookup prints from console unless DEBUG=true
    debug_enabled = os.environ.get('DEBUG', 'false').lower() == 'true'
    is_verbose = "Checking cache candidate:" in message or "Cache hit found:" in message
    if not is_verbose or debug_enabled:
        print(line)
        
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception:
        pass

# Define absolute paths for templates and static files based on current directory
try:
    TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
    STATIC_DIR = os.path.join(BASE_DIR, 'static')
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)
        
    app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
except Exception as e:
    # Fallback if abspath fails (rare)
    app = Flask(__name__)

CACHE_DIR = os.path.join(BASE_DIR, 'Cached_results')
DATA_DIR = os.path.join(BASE_DIR, 'data')
VERIFICATIONS_FILE = os.path.join(DATA_DIR, 'verifications.json')
USAGE_FILE = os.path.join(DATA_DIR, 'usage_stats.json')

os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_MODEL = 'openai.gpt-4o'
DEFAULT_DISEASE = 'Breast cancer'

DEVELOPER_NOTIFICATION_EMAILS = (
    "yus4011@med.cornell.edu",
    "shiyushu2006@gmail.com",
    "margauxdelporte@gmail.com",
)

CONSENSUS_FIELDS = (
    "Effect Size",
    "Lower CI",
    "Upper CI",
    "Cases",
    "Sample Size",
    "exposure_measurement_type",
)

has_openai = bool(os.environ.get("OPENAI_API_KEY"))
has_gemini = bool(os.environ.get("GOOGLE_API_KEY"))
READ_ONLY_MODE = os.environ.get('READ_ONLY_MODE', 'false').lower() == 'true' or not (has_openai or has_gemini)

def _safe_email_value(value, fallback="Not available"):
    """Return a one-line value that is safe to place in an email body."""
    text = re.sub(r"[\r\n]+", " ", str(value or "")).strip()
    return text or fallback

def first_author_last_name(study_data):
    """Extract the first author's last name from a saved study record."""
    study_data = study_data or {}
    authors = _safe_email_value(study_data.get("Authors"), fallback="")
    if authors:
        first_author = authors.split(",", 1)[0].strip()
        last_name = re.sub(r"(?:\s+[A-Z][A-Z.'-]*)+$", "", first_author).strip()
        if last_name:
            return last_name

    study_label = _safe_email_value(study_data.get("Study"), fallback="")
    if study_label:
        author_part = re.split(r"\s+et\s+al\.?|\s+\(\d{4}\)", study_label, maxsplit=1, flags=re.IGNORECASE)[0]
        last_name = re.sub(r"(?:\s+[A-Z][A-Z.'-]*)+$", "", author_part).strip()
        if last_name:
            return last_name
    return "Not available"

def _normalise_consensus_value(value):
    if value is None:
        return "none"
    text = str(value).strip().lower()
    return "none" if text in {"", "null", "none", "nan"} else text

def matching_submission_signature(submissions):
    """Return a stable signature when any two crowdsourced submissions match."""
    seen = set()
    for submission in reversed(submissions or []):
        values = tuple(
            _normalise_consensus_value((submission.get("data") or {}).get(field))
            for field in CONSENSUS_FIELDS
        )
        if values in seen:
            payload = json.dumps(dict(zip(CONSENSUS_FIELDS, values)), sort_keys=True)
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()
        seen.add(values)
    return None

def find_saved_study(pmid, exposure=None):
    """Find local author metadata when the browser did not send a study record."""
    safe_exposure = safe_path_component(meta_analysis.get_canonical_name(exposure)) if exposure else None
    search_root = os.path.join(CACHE_DIR, safe_exposure) if safe_exposure else CACHE_DIR
    if not os.path.isdir(search_root):
        return {}
    for root, _, files in os.walk(search_root):
        for filename in files:
            if not filename.endswith(".json"):
                continue
            cached = load_json(os.path.join(root, filename), {})
            for study in cached.get("studies", []) if isinstance(cached, dict) else []:
                if str(study.get("PMID")) == str(pmid):
                    return study
    return {}

def send_developer_notification(event_type, exposure, disease, outcome, pmid, study_data=None):
    """Email developers about a crowdsourced review trigger without changing results."""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM") or smtp_username
    use_ssl = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    safe_pmid = _safe_email_value(pmid)

    if not smtp_host or not smtp_from:
        message = "SMTP_HOST and SMTP_FROM (or SMTP_USERNAME) must be configured"
        log_event(f"[MetaFemina] Developer notification not sent for PMID {safe_pmid}: {message}")
        return False, message
    try:
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        message = "SMTP_PORT must be an integer"
        log_event(f"[MetaFemina] Developer notification not sent for PMID {safe_pmid}: {message}")
        return False, message

    event_label = {
        "matching_submissions": "Two matching crowdsourced submissions",
        "exclusion_flags": "Two or more crowdsourced exclusion flags",
    }.get(event_type, "Crowdsourced review trigger")
    author_last_name = first_author_last_name(study_data)

    email = EmailMessage()
    email["Subject"] = f"MetaFemina review requested: PMID {safe_pmid}"
    email["From"] = smtp_from
    email["To"] = ", ".join(DEVELOPER_NOTIFICATION_EMAILS)
    email.set_content(
        "A crowdsourced report requires developer review. Results were not changed.\n\n"
        f"Trigger: {event_label}\n"
        f"Exposure: {_safe_email_value(exposure)}\n"
        f"Disease: {_safe_email_value(disease)}\n"
        f"Outcome: {_safe_email_value(outcome)}\n"
        f"PMID: {safe_pmid}\n"
        f"First author last name: {_safe_email_value(author_last_name)}\n"
        f"PubMed: https://pubmed.ncbi.nlm.nih.gov/{safe_pmid}/\n"
    )

    try:
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(smtp_host, smtp_port, timeout=15) as server:
            if use_tls and not use_ssl:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(email)
        log_event(f"[MetaFemina] Developer notification sent for PMID {safe_pmid}: {event_type}")
        return True, None
    except Exception as exc:
        log_event(f"[MetaFemina] Developer notification failed for PMID {safe_pmid}: {exc}")
        return False, str(exc)

def safe_path_component(value):
    """Return a stable filesystem-safe path component for cache names."""
    chars = []
    for c in str(value).lower():
        if c.isalnum() or c in "._-":
            chars.append(c)
        elif c.isspace():
            chars.append("_")
        else:
            chars.append("_")
    return "".join(chars).strip("_")

def model_cache_priority(requested_model):
    """Prefer the requested model, then fall back to known higher-quality caches."""
    priority = [
        requested_model or DEFAULT_MODEL,
        'anthropic.claude-4.5-sonnet',
        'openai.gpt-5.4-pro',
        'openai.gpt-4o',
        DEFAULT_MODEL,
        'google.gemini-2.5-pro',
        'google.gemini-2.5-flash',
        'google.gemini-2.0-flash',
    ]
    return list(dict.fromkeys(priority))

def get_cache_path(disease, exposure, outcome, exclude_meta, use_downstream=False, model=None):
    """Construct a file path for the specific analysis cache and resolve synonyms."""
    # Resolve canonical name first to avoid DHEA vs dehydroepiandrosterone duplicate caches
    canonical_exposure = meta_analysis.get_canonical_name(exposure)
    safe_exposure = safe_path_component(canonical_exposure)
    
    downstream_tag = "all" if use_downstream else "core"
    # Maintain backward compatibility: don't add suffix for the default model or legacy gpt-4o default
    is_default_or_legacy = (model == DEFAULT_MODEL) or (model == 'openai.gpt-4o') or (model == 'anthropic.claude-4.5-sonnet')
    model_tag = "" if not model or is_default_or_legacy else f"_{safe_path_component(model)}"
    safe_analysis = safe_path_component(f"{disease}_{outcome}_{exclude_meta}_{downstream_tag}{model_tag}")
    
    exposure_dir = os.path.join(CACHE_DIR, safe_exposure)
    return os.path.join(exposure_dir, f"{safe_analysis}.json")

def load_json(filepath, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return default_val
    return default_val

def save_json(filepath, data):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(sanitize_data(data), f, indent=4)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

def sanitize_data(data):
    """Recursively replace NaN/Inf values and convert numpy types for JSON compatibility."""
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}

    elif isinstance(data, list):
        return [sanitize_data(x) for x in data]
    elif isinstance(data, (np.bool_,)):
        return bool(data)
    elif isinstance(data, (np.integer,)):
        return int(data)
    elif isinstance(data, (np.floating,)):
        val = float(data)
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    elif isinstance(data, float):
        if np.isnan(data) or np.isinf(data):
            return None
    return data

def update_cache_from_verifications(disease, exposure, outcome):
    """
    Retained for compatibility with older callers.

    Crowdsourced submissions are advisory only and must never mutate cached
    studies, exclusions, pooled results, or plots.
    """
    log_event(
        f"[MetaFemina] Skipped cache update for {disease}/{exposure}/{outcome}; "
        "crowdsourced reports are advisory only."
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    return response

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    disease = data.get('disease', DEFAULT_DISEASE)
    exposure = data.get('exposure', 'Coffee')
    outcome = data.get('outcome', 'Incidence')
    exclude_meta = data.get('exclude_meta', False)
    model = data.get('model', DEFAULT_MODEL)
    if model == 'openai.gpt-4o-mini':
        model = DEFAULT_MODEL
    # The UI toggle is removed, so we default to False for downstream terms
    use_downstream = data.get('use_downstream', False)
    force_refresh = data.get('force_refresh', False)

    started_at = time.time()
    log_event(
        f"[MetaFemina] Analyze request: disease={disease}, exposure={exposure}, "
        f"outcome={outcome}, exclude_meta={exclude_meta}, force_refresh={force_refresh}, model={model}"
    )

    best_cache_path = None
    if not force_refresh:
        # Try requested downstream setting first, then fallback to opposite
        for ds_flag in [use_downstream, not use_downstream]:
            for p_model in model_cache_priority(model):
                p_path = get_cache_path(disease, exposure, outcome, exclude_meta, ds_flag, p_model)
                log_event(f"[MetaFemina] Checking cache candidate: {p_path}")
                if os.path.exists(p_path):
                    best_cache_path = p_path
                    log_event(f"[MetaFemina] Cache hit found: {best_cache_path}")
                    break
            if best_cache_path:
                break
    else:
        log_event("[MetaFemina] Force refresh requested; bypassing cached result lookup.")
        if READ_ONLY_MODE:
            return jsonify({"error": "Refreshing evidence is disabled in the public demonstration version."}), 400

    if READ_ONLY_MODE and not best_cache_path:
        log_event("[MetaFemina] No cached result found for request in read-only mode.")
        return jsonify({"error": "This exposure has not been pre-analyzed yet. In the public demonstration version, only pre-analyzed exposures are available to search."}), 400

    if best_cache_path:
        log_event(f"[MetaFemina] Returning best available cached results from {best_cache_path}")
        result = load_json(best_cache_path, {})
        screening_stats = result.get("screening_stats")
        if not screening_stats and "studies" in result:
            screening_stats = {
                "total_fetched": "N/A (Legacy Cache)",
                "after_prefilter": "N/A (Legacy Cache)",
                "prefilter_skip": {},
                "llm_screened_in": len(result["studies"]),
                "llm_screened_out": 0,
                "consensus_bypassed": 0,
                "extracted": len(result["studies"])
            }
        if screening_stats:
            log_event("\n" + "="*60)
            log_event("[MetaFemina] SCREENING & PIPELINE STATISTICS SUMMARY (LOADED FROM CACHE):")
            log_event(f"  - Total Articles Fetched from PubMed: {screening_stats.get('total_fetched', 0)}")
            log_event(f"  - Articles Remaining After Pre-filter: {screening_stats.get('after_prefilter', 0)}")
            skips = screening_stats.get('prefilter_skip', {})
            if skips:
                skips_str = ", ".join([f"{k}={v}" for k, v in skips.items() if v > 0])
                if skips_str:
                    log_event(f"    (Pre-filter skips: {skips_str})")
            log_event(f"  - LLM Screening:")
            log_event(f"    * Screened IN / Accepted:   {screening_stats.get('llm_screened_in', 0)}")
            log_event(f"    * Screened OUT / Rejected:  {screening_stats.get('llm_screened_out', 0)}")
            log_event(f"    * Consensus Bypassed:       {screening_stats.get('consensus_bypassed', 0)}")
            log_event(f"  - Final Extracted Studies: {screening_stats.get('extracted', 0)}")
            log_event("="*60 + "\n")
    else:
        # Resolve canonical name for analysis engine consumption
        canonical_exposure = meta_analysis.get_canonical_name(exposure)
        log_event(f"[MetaFemina] Running new analysis for {disease} / {canonical_exposure} (from '{exposure}') using model: {model}")
        result = meta_analysis.get_analysis_data(disease, canonical_exposure, outcome=outcome, exclude_meta=exclude_meta, use_downstream=use_downstream, model=model)
        
        # Cache successful analyses OR empty results
        is_empty = result.get("error") == "No relevant evidence was identified in the reviewed sources."
        if "error" not in result or is_empty:
            result['last_run'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Save using the model that actually ran
            target_cache_path = get_cache_path(disease, exposure, outcome, exclude_meta, use_downstream, model)
            save_json(target_cache_path, result)
            log_event(f"[MetaFemina] Saved refreshed result cache to {target_cache_path}")
        else:
            log_event(f"[MetaFemina] Analysis returned an error; not caching: {result.get('error')}")
    
    # Inject advisory crowdsourcing counts. Reports never alter study data or results.
    verifications = load_json(VERIFICATIONS_FILE, {})
    canonical_exp = meta_analysis.get_canonical_name(exposure)
    context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
    
    if "studies" in result:
        for study in result['studies']:
            if 'exposure_measurement_type' not in study or study['exposure_measurement_type'] in [None, '', '-']:
                study['exposure_measurement_type'] = 'unclear'
            if 'exposure_measurement_supporting_text' not in study or study['exposure_measurement_supporting_text'] is None:
                study['exposure_measurement_supporting_text'] = ''
            if 'extraction_supporting_text' not in study or not isinstance(study.get('extraction_supporting_text'), dict):
                study['extraction_supporting_text'] = {
                    "sample_size": "",
                    "effect_size": "",
                    "effect_direction": "",
                    "p_value": "",
                    "confidence_interval": "",
                    "outcome_definition": "",
                    "exposure_definition": ""
                }
            else:
                est = study['extraction_supporting_text']
                for k in ["sample_size", "effect_size", "effect_direction", "p_value", "confidence_interval", "outcome_definition", "exposure_definition"]:
                    if k not in est or est[k] is None:
                        est[k] = ""
            pmid = str(study.get('PMID'))
            v_info = verifications.get(pmid, {})
            
            study['exclusions'] = 0
            study['exclusion_flags'] = 0

            # Legacy handling and structured advisory status
            if isinstance(v_info, int):
                study['verifications'] = v_info
                study['verification_status'] = 'partial' if v_info > 0 else 'unverified'
            else:
                context_excl = v_info.get('context_exclusions', {})
                study['exclusion_flags'] = context_excl.get(context_key, 0)
                
                contexts = v_info.get('contexts', {})
                current_context_data = contexts.get(context_key, {})
                
                if current_context_data:
                    submissions = current_context_data.get('submissions', [])
                else:
                    submissions = []
                
                study['verifications'] = len(submissions)
                if matching_submission_signature(submissions) or study['exclusion_flags'] >= 2:
                    study['verification_status'] = 'review_requested'
                elif study['verifications'] > 0:
                    study['verification_status'] = 'partial'
                else:
                    study['verification_status'] = 'unverified'
            
    log_event(
        f"[MetaFemina] Analyze complete in {time.time() - started_at:.1f}s: "
        f"studies={len(result.get('studies', []))}, error={result.get('error')}"
    )
    return jsonify(sanitize_data(result))

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json or {}
    pmid = str(data.get('pmid') or '').strip()
    study_data = data.get('study_data') or {}
    exposure = data.get('exposure')
    
    # Resolve canonical name for context key consistency
    canonical_exp = meta_analysis.get_canonical_name(exposure) if exposure else "unknown_exposure"
    disease = data.get('disease', DEFAULT_DISEASE)
    outcome = data.get('outcome', 'incidence')
    context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
    
    if not pmid:
        return jsonify({"error": "No PMID provided"}), 400

    if not study_data:
        study_data = find_saved_study(pmid, exposure)
    
    # Load verifications
    verifications = load_json(VERIFICATIONS_FILE, {})
    
    # Initialize entry if not exists or if legacy
    if pmid not in verifications or isinstance(verifications[pmid], int):
        legacy_count = verifications.get(pmid, 0) if isinstance(verifications.get(pmid), int) else 0
        verifications[pmid] = {
            "submissions": [],
            "consensus_data": None,
            "legacy_count": legacy_count,
            "context_exclusions": {},
            "contexts": {}
        }
    
    if "contexts" not in verifications[pmid]:
        verifications[pmid]["contexts"] = {}
        
    if context_key not in verifications[pmid]["contexts"]:
        verifications[pmid]["contexts"][context_key] = {
            "submissions": [],
            "consensus_data": None,
            "notifications": {}
        }

    context = verifications[pmid]["contexts"][context_key]
    context.setdefault("submissions", [])
    context.setdefault("notifications", {})
    # Clear legacy automatic overlays for this context. Runtime analysis also
    # ignores all historical consensus_data values.
    context["consensus_data"] = None
    
    # Extract only the fields we want to track/compare for consensus
    if study_data:
        metrics = {
            "Effect Size": study_data.get("Effect Size"),
            "Lower CI": study_data.get("Lower CI"),
            "Upper CI": study_data.get("Upper CI"),
            "Cases": study_data.get("Cases"),
            "Sample Size": study_data.get("Sample Size"),
            "Design": study_data.get("Design"),
            "Timing": study_data.get("Timing"),
            "Comparison Type": study_data.get("comparison_type"),
            "exposure_measurement_type": study_data.get("exposure_measurement_type")
        }
        
        # Add new submission
        context["submissions"].append({
            "data": metrics,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    matching_signature = matching_submission_signature(context["submissions"])
    notified_signatures = context["notifications"].setdefault("matching_submission_signatures", [])
    notification_sent = False
    notification_already_sent = bool(matching_signature and matching_signature in notified_signatures)
    if matching_signature and not notification_already_sent:
        notification_sent, _ = send_developer_notification(
            "matching_submissions", exposure, disease, outcome, pmid, study_data
        )
        if notification_sent:
            notified_signatures.append(matching_signature)
            context["notifications"]["matching_submission_last_sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_json(VERIFICATIONS_FILE, verifications)
    
    # Count includes legacy count + new structured submissions
    total_count = len(context["submissions"]) + verifications[pmid].get("legacy_count", 0)
    review_requested = matching_signature is not None
    status = "review_requested" if review_requested else "partial"
    
    return jsonify({
        "success": True, 
        "count": total_count, 
        "status": status,
        "consensus_reached": False,
        "review_requested": review_requested,
        "notification_sent": notification_sent,
        "notification_already_sent": notification_already_sent,
        "results_changed": False
    })

@app.route('/exclude', methods=['POST'])
def exclude():
    data = request.json or {}
    pmid = str(data.get('pmid') or '').strip()
    exposure = data.get('exposure')
    study_data = data.get('study_data') or {}
    canonical_exp = meta_analysis.get_canonical_name(exposure) if exposure else "unknown_exposure"
    disease = data.get('disease', DEFAULT_DISEASE)
    outcome = data.get('outcome', 'incidence')
    context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
    
    if not pmid:
        return jsonify({"error": "No PMID provided"}), 400

    if not study_data:
        study_data = find_saved_study(pmid, exposure)
    
    verifications = load_json(VERIFICATIONS_FILE, {})
    
    # Initialize entry if not exists or if legacy
    if pmid not in verifications or isinstance(verifications[pmid], int):
        legacy_count = verifications.get(pmid, 0) if isinstance(verifications.get(pmid), int) else 0
        verifications[pmid] = {
            "submissions": [],
            "consensus_data": None,
            "legacy_count": legacy_count,
            "context_exclusions": {},
            "contexts": {}
        }
    
    if "context_exclusions" not in verifications[pmid]:
        verifications[pmid]["context_exclusions"] = {}
    if "contexts" not in verifications[pmid]:
        verifications[pmid]["contexts"] = {}
    if context_key not in verifications[pmid]["contexts"]:
        verifications[pmid]["contexts"][context_key] = {
            "submissions": [],
            "consensus_data": None,
            "notifications": {}
        }

    context = verifications[pmid]["contexts"][context_key]
    context.setdefault("notifications", {})
    context["consensus_data"] = None
        
    if context_key not in verifications[pmid]["context_exclusions"]:
        verifications[pmid]["context_exclusions"][context_key] = 0
            
    verifications[pmid]["context_exclusions"][context_key] += 1
    exclusion_count = verifications[pmid]["context_exclusions"][context_key]

    notification_sent = False
    notification_already_sent = bool(context["notifications"].get("exclusion_flags_sent_at"))
    if exclusion_count >= 2 and not notification_already_sent:
        notification_sent, _ = send_developer_notification(
            "exclusion_flags", exposure, disease, outcome, pmid, study_data
        )
        if notification_sent:
            context["notifications"]["exclusion_flags_sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_json(VERIFICATIONS_FILE, verifications)
    
    return jsonify({
        "success": True,
        "pmid": pmid,
        "context_key": context_key,
        "exclusions": exclusion_count,
        "review_requested": exclusion_count >= 2,
        "notification_sent": notification_sent,
        "notification_already_sent": notification_already_sent,
        "results_changed": False
    })

@app.route('/reanalyze', methods=['POST'])
def reanalyze():
    data = request.json
    studies = data.get('studies', [])
    disease = data.get('disease', 'Custom Analysis')
    exposure = data.get('exposure', 'Custom Exposure')
    
    if not studies:
        return jsonify({"error": "No studies provided for analysis."})
    
    # Convert list of dicts to DataFrame
    df = pd.DataFrame(studies)
    
    # Ensure numeric columns are floats
    numeric_cols = ['Effect Size', 'Lower CI', 'Upper CI', 'SE']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    result = meta_analysis.perform_meta_analysis(df, disease, exposure, outcome=data.get('outcome', 'Incidence'), exclude_meta=data.get('exclude_meta', False))
    return jsonify(sanitize_data(result))

@app.route('/usage')
def usage():
    stats = load_json(USAGE_FILE, {})
    
    # Calculate costs
    # Pricing per token (per 1M tokens)
    pricing = {
        # OpenAI
        "gpt-4o-mini":        {"in": 0.15  / 1_000_000, "out": 0.60  / 1_000_000},
        "openai.gpt-4o-mini": {"in": 0.15  / 1_000_000, "out": 0.60  / 1_000_000},
        "gpt-4o":             {"in": 2.50  / 1_000_000, "out": 10.00 / 1_000_000},
        "gpt-4.1":            {"in": 2.00  / 1_000_000, "out": 8.00  / 1_000_000},
        "openai.gpt-4.1":     {"in": 2.00  / 1_000_000, "out": 8.00  / 1_000_000},
        # Gemini
        "gemini-2.0-flash":         {"in": 0.10 / 1_000_000, "out": 0.40  / 1_000_000},
        "gemini-2.5-flash":         {"in": 0.30 / 1_000_000, "out": 2.50  / 1_000_000},
        "google.gemini-2.5-flash":  {"in": 0.30 / 1_000_000, "out": 2.50  / 1_000_000},
        "gemini-2.5-pro":           {"in": 1.25 / 1_000_000, "out": 10.00 / 1_000_000},
        "google.gemini-2.5-pro":    {"in": 1.25 / 1_000_000, "out": 10.00 / 1_000_000},
    }

    def compute_cost_breakdown(usage_dict):
        total = 0
        rows = []
        for model, d in usage_dict.items():
            price = pricing.get(model, {"in": 0, "out": 0})
            cost = (d["input_tokens"] * price["in"]) + (d["output_tokens"] * price["out"])
            total += cost
            rows.append({
                "model": model,
                "input_tokens": d["input_tokens"],
                "output_tokens": d["output_tokens"],
                "calls": d["calls"],
                "cost": round(cost, 4)
            })
        return round(total, 4), rows

    total_cost, detailed_stats = compute_cost_breakdown(stats)

    # Last-analysis cost
    last_stats = load_json(os.path.join(DATA_DIR, 'last_analysis_usage.json'), {})
    last_cost, last_detailed = compute_cost_breakdown(last_stats)

    return jsonify({
        "total_cost": total_cost,
        "models": detailed_stats,
        "last_analysis_cost": last_cost,
        "last_analysis_models": last_detailed,
    })

def get_last_updated_time():
    """Find the latest modification time of any file in CACHE_DIR as a Unix timestamp."""
    latest_time = 0.0
    if os.path.exists(CACHE_DIR):
        for root, dirs, files in os.walk(CACHE_DIR):
            for file in files:
                if file.endswith('.json'):
                    fp = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(fp)
                        if mtime > latest_time:
                            latest_time = mtime
                    except Exception:
                        pass
    return latest_time if latest_time > 0 else None

@app.route('/api/config')
def get_config():
    """Return read-only status, last updated time, and the list of pre‑cached exposures."""
    exposures = []
    if os.path.exists(CACHE_DIR):
        for d in os.listdir(CACHE_DIR):
            d_path = os.path.join(CACHE_DIR, d)
            if os.path.isdir(d_path):
                try:
                    if any(f.endswith('.json') for f in os.listdir(d_path)):
                        exposures.append(d)
                except Exception:
                    pass
    return jsonify({
        "read_only": READ_ONLY_MODE,
        "cached_exposures": sorted(exposures),
        "last_updated": get_last_updated_time()
    })

# Diagnostic endpoint for cache status
@app.route('/debug/cache_status', methods=['POST'])
def debug_cache_status():
    data = request.json or {}
    disease = data.get('disease', DEFAULT_DISEASE)
    exposure = data.get('exposure', 'Coffee')
    outcome = data.get('outcome', 'Incidence')
    exclude_meta = data.get('exclude_meta', False)
    model = data.get('model', DEFAULT_MODEL)
    use_downstream = data.get('use_downstream', False)
    path = get_cache_path(disease, exposure, outcome, exclude_meta, use_downstream, model)
    exists = os.path.exists(path)
    return jsonify({
        "cache_path": path,
        "exists": exists,
        "message": f"Cache {'found' if exists else 'not found'} for exposure '{exposure}'"
    })

@app.route('/api/synonyms')
def get_synonyms():
    """Return the synonyms cache so the frontend can show synonym hints in the search dropdown."""
    synonyms = load_json(os.path.join(DATA_DIR, 'synonyms_cache.json'), {})
    return jsonify(synonyms)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Disable the reloader so that mid-analysis .pyc file generation in stdlib (like xml.sax) doesn't restart the server
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
