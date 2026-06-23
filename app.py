from flask import Flask, render_template, request, jsonify, send_from_directory
import meta_analysis
import os
import pandas as pd
import numpy as np
import json
import time
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

has_openai = bool(os.environ.get("OPENAI_API_KEY"))
has_gemini = bool(os.environ.get("GOOGLE_API_KEY"))
READ_ONLY_MODE = os.environ.get('READ_ONLY_MODE', 'false').lower() == 'true' or not (has_openai or has_gemini)

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
    # Maintain backward compatibility: don't add suffix for the default model
    model_tag = f"_{safe_path_component(model)}" if model and model != DEFAULT_MODEL else ""
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
    Finds all cache files under Cached_results/<exposure> and updates their studies'
    Effect Size, CIs, and comparison_types according to verifications.json, then
    re-runs perform_meta_analysis on each cache file and saves it back to disk.
    """
    canonical_exp = meta_analysis.get_canonical_name(exposure)
    safe_exposure = safe_path_component(canonical_exp)
    exposure_dir = os.path.join(CACHE_DIR, safe_exposure)
    
    if not os.path.exists(exposure_dir):
        return
        
    verifications = load_json(VERIFICATIONS_FILE, {})
    context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
    
    # Loop over all json files in exposure_dir
    for filename in os.listdir(exposure_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(exposure_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                
                if "studies" not in cache:
                    continue
                    
                # Apply consensus and exclusion overlay to studies list
                cache_updated = False
                for study in cache["studies"]:
                    pmid = str(study.get("PMID"))
                    v_info = verifications.get(pmid, {})
                    contexts = v_info.get("contexts", {})
                    current_context_data = contexts.get(context_key, {})
                    
                    # Handle exclusion
                    context_excl = v_info.get("context_exclusions", {})
                    exclusion_val = context_excl.get(context_key, 0)
                    if study.get("exclusions", 0) != exclusion_val:
                        study["exclusions"] = exclusion_val
                        cache_updated = True
                        
                    # Handle consensus overlay
                    consensus = current_context_data.get("consensus_data")
                    if consensus:
                        for key, val in consensus.items():
                            if val is not None and val != "":
                                cache_key = key
                                if key == "Comparison Type":
                                    cache_key = "comparison_type"
                                if str(study.get(cache_key)) != str(val):
                                    study[cache_key] = val
                                    # N/Cases/Participants sync
                                    if cache_key == 'Sample Size':
                                        study['Participants'] = val
                                    if cache_key == 'Participants':
                                        study['Sample Size'] = val
                                    cache_updated = True
                
                if cache_updated:
                    # Convert to df and re-run meta-analysis
                    valid_studies = [s for s in cache["studies"] if s.get("exclusions", 0) < 2]
                    df_new = pd.DataFrame(valid_studies)
                    
                    # Ensure numeric precision
                    if len(df_new) > 0:
                        for col in ['Effect Size', 'Lower CI', 'Upper CI', 'SE']:
                            if col in df_new.columns:
                                df_new[col] = pd.to_numeric(df_new[col], errors='coerce')
                                
                        exclude_meta = "true" in filename.lower()
                        new_meta = meta_analysis.perform_meta_analysis(
                            df_new, 
                            disease, 
                            exposure, 
                            outcome=outcome, 
                            exclude_meta=exclude_meta
                        )
                        # Update key result fields
                        for key in ['headline', 'summary_html', 'plot_url', 'funnel_plot_url', 'baujat_plot_url']:
                            cache[key] = new_meta.get(key)
                    else:
                        cache['headline'] = None
                        cache['summary_html'] = None
                        cache['plot_url'] = None
                        cache['funnel_plot_url'] = None
                        cache['baujat_plot_url'] = None
                        
                    # Save updated cache safely
                    cache_str = json.dumps(sanitize_data(cache), indent=4)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(cache_str)
                    log_event(f"[MetaFemina] Updated cache file and regenerated plots for {filepath}")
            except Exception as e:
                log_event(f"Error updating cache file {filepath}: {e}")

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
    
    # Inject verification counts and consensus data
    verifications = load_json(VERIFICATIONS_FILE, {})
    canonical_exp = meta_analysis.get_canonical_name(exposure)
    context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
    
    if "studies" in result:
        # Track if any studies were removed or consensus was applied
        num_before = len(result.get("studies", []))
        consensus_applied = False
        
        # The frontend now handles deselection and watermarking of flagged studies, 
        # so we no longer drop them from the result array here.

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
            
            # Legacy handling and structured data overlay
            if isinstance(v_info, int):
                study['verifications'] = v_info
                study['verification_status'] = 'partial' if v_info > 0 else 'unverified'
                study['exclusions'] = 0
            else:
                context_excl = v_info.get('context_exclusions', {})
                study['exclusions'] = context_excl.get(context_key, 0)
                
                contexts = v_info.get('contexts', {})
                current_context_data = contexts.get(context_key, {})
                
                if current_context_data:
                    submissions = current_context_data.get('submissions', [])
                    consensus = current_context_data.get('consensus_data')
                else:
                    submissions = []
                    consensus = None
                
                study['verifications'] = len(submissions)
                
                if consensus:
                    # Overlay consensus data
                    for key, val in consensus.items():
                        if val is not None and val != "":
                            if str(study.get(key)) != str(val):
                                study[key] = val
                                # Consistency Fix: N/Cases/Participants sync
                                if key == 'Sample Size':
                                    study['Participants'] = val
                                if key == 'Participants':
                                    study['Sample Size'] = val
                                consensus_applied = True
                    study['verification_status'] = 'consensus'
                elif study['verifications'] > 0:
                    study['verification_status'] = 'partial'
                else:
                    study['verification_status'] = 'unverified'
        
        num_after = len(result['studies'])
        has_flagged = any(s.get('exclusions', 0) >= 2 for s in result['studies'])
        
        # If studies were removed or modified by consensus, re-run meta-analysis
        if num_after == 0:
            result['headline'] = None
            result['summary_html'] = None
            result['error'] = "No relevant evidence was identified in the reviewed sources after verification filtering."
        elif num_after < num_before or consensus_applied or has_flagged:
            log_event(f"[MetaFemina] Re-analyzing {exposure} due to verification filtering/consensus/flags...")
            # Only include valid studies in the recalculated meta-analysis
            valid_studies = [s for s in result['studies'] if s.get('exclusions', 0) < 2]
            df_new = pd.DataFrame(valid_studies)
            
            if len(df_new) > 0:
                # Ensure numeric precision
                for col in ['Effect Size', 'Lower CI', 'Upper CI', 'SE']:
                    if col in df_new.columns:
                        df_new[col] = pd.to_numeric(df_new[col], errors='coerce')
                
                new_meta = meta_analysis.perform_meta_analysis(df_new, disease, exposure, outcome=outcome, exclude_meta=exclude_meta)
                
                # Update key result fields
                for key in ['headline', 'summary_html', 'plot_url', 'funnel_plot_url', 'baujat_plot_url']:
                    result[key] = new_meta.get(key)
            else:
                result['headline'] = None
                result['summary_html'] = None
                result['error'] = "No relevant evidence was identified in the reviewed sources after verification filtering."
            
    log_event(
        f"[MetaFemina] Analyze complete in {time.time() - started_at:.1f}s: "
        f"studies={len(result.get('studies', []))}, error={result.get('error')}"
    )
    return jsonify(sanitize_data(result))

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json
    pmid = str(data.get('pmid'))
    study_data = data.get('study_data')
    exposure = data.get('exposure')
    if not exposure and study_data:
        # Fallback to current browser exposure value if not provided
        exposure = request.json.get('exposure')
    
    # Resolve canonical name for context key consistency
    canonical_exp = meta_analysis.get_canonical_name(exposure) if exposure else "unknown_exposure"
    disease = data.get('disease', DEFAULT_DISEASE)
    outcome = data.get('outcome', 'incidence')
    context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
    
    if not pmid:
        return jsonify({"error": "No PMID provided"}), 400
    
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
            "consensus_data": None
        }
    
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
        verifications[pmid]["contexts"][context_key]["submissions"].append({
            "data": metrics,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        # Check for consensus: at least two MATCHING submissions
        subs = verifications[pmid]["contexts"][context_key]["submissions"]
        if len(subs) >= 2:
            # Look for matches starting from the LATEST submission (backward iteration)
            # This allows a user to "overwrite" an old consensus by providing two new matching entries.
            found_match = False
            for i in range(len(subs) - 1, -1, -1):
                for j in range(i - 1, -1, -1):
                    d1 = subs[i]["data"]
                    d2 = subs[j]["data"]
                    
                    # Compare key metric fields
                    is_match = True
                    for field in ["Effect Size", "Lower CI", "Upper CI", "Cases", "Sample Size", "exposure_measurement_type"]:
                        v1 = str(d1.get(field)).strip().lower()
                        v2 = str(d2.get(field)).strip().lower()
                        
                        # Handle potential None/empty values
                        v1 = "none" if v1 in ["None", "null", "", "nan"] else v1
                        v2 = "none" if v2 in ["None", "null", "", "nan"] else v2
                        
                        if v1 != v2:
                            is_match = False
                            break
                    
                    if is_match:
                        verifications[pmid]["contexts"][context_key]["consensus_data"] = d1
                        found_match = True
                        break
                if found_match:
                    break
 
    save_json(VERIFICATIONS_FILE, verifications)
    update_cache_from_verifications(disease, exposure, outcome)
    
    # Count includes legacy count + new structured submissions
    total_count = len(verifications[pmid]["contexts"][context_key]["submissions"]) + verifications[pmid].get("legacy_count", 0)
    status = "consensus" if verifications[pmid]["contexts"][context_key]["consensus_data"] else "partial"
    
    return jsonify({
        "success": True, 
        "count": total_count, 
        "status": status,
        "consensus_reached": verifications[pmid]["contexts"][context_key]["consensus_data"] is not None
    })

@app.route('/exclude', methods=['POST'])
def exclude():
    data = request.json
    pmid = str(data.get('pmid'))
    exposure = data.get('exposure')
    canonical_exp = meta_analysis.get_canonical_name(exposure) if exposure else "unknown_exposure"
    disease = data.get('disease', DEFAULT_DISEASE)
    outcome = data.get('outcome', 'incidence')
    context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
    
    if not pmid:
        return jsonify({"error": "No PMID provided"}), 400
    
    verifications = load_json(VERIFICATIONS_FILE, {})
    
    # Initialize entry if not exists or if legacy
    if pmid not in verifications or isinstance(verifications[pmid], int):
        legacy_count = verifications.get(pmid, 0) if isinstance(verifications.get(pmid), int) else 0
        verifications[pmid] = {
            "submissions": [],
            "consensus_data": None,
            "legacy_count": legacy_count,
            "context_exclusions": {}
        }
    
    if "context_exclusions" not in verifications[pmid]:
        verifications[pmid]["context_exclusions"] = {}
        
    if context_key not in verifications[pmid]["context_exclusions"]:
        verifications[pmid]["context_exclusions"][context_key] = 0
            
    verifications[pmid]["context_exclusions"][context_key] += 1
    save_json(VERIFICATIONS_FILE, verifications)
    update_cache_from_verifications(disease, exposure, outcome)
    
    return jsonify({
        "success": True,
        "pmid": pmid,
        "context_key": context_key,
        "exclusions": verifications[pmid]["context_exclusions"][context_key]
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

@app.route('/api/config')
def get_config():
    """Return read-only status and the list of pre‑cached exposures."""
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
        "cached_exposures": sorted(exposures)
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
