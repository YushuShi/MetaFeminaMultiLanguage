import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Set non-interactive backend for Flask
import matplotlib.pyplot as plt
from Bio import Entrez
from dotenv import load_dotenv
import statsmodels.api as sm
from statsmodels.stats.meta_analysis import CombineResults, combine_effects
import forestplot
from openai import OpenAI
import json
from google import genai
from functools import partial

print = partial(print, flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ... (rest of imports)

DISEASE_ALIASES = {
    "breast cancer": {
        "query": '(Breast AND Cancer)',
        "terms": ["breast", "mammary"],
        "patient_phrases": ["breast cancer survivors", "breast cancer patients", "cancer survivors", "cancer patients"],
        "pattern": r'breast\s*(?:and\s*)?(?:cancer|tumou?r|carcinoma)|mammary\s*(?:and\s*)?(?:cancer|tumou?r|carcinoma)',
        "score_terms": ["breast cancer", "mammary cancer", "carcinoma"],
    },
    "ovarian cancer": {
        "query": '(Ovary AND Cancer) OR (Ovarian AND Cancer)',
        "terms": ["ovarian", "ovary"],
        "patient_phrases": ["ovarian cancer survivors", "ovarian cancer patients", "cancer survivors", "cancer patients"],
        "pattern": r'ovarian\s*(?:and\s*)?(?:cancer|tumou?r|carcinoma)|ovary\s*(?:and\s*)?(?:cancer|tumou?r|carcinoma)',
        "score_terms": ["ovarian cancer", "ovary cancer", "carcinoma"],
    },
    "uterine cancer": {
        "query": '(Uterus AND Cancer) OR (Uterine AND Cancer) OR (Endometrial AND Cancer)',
        "terms": ["uterine", "uterus", "endometrial"],
        "patient_phrases": ["uterine cancer survivors", "uterine cancer patients"],
        "pattern": r'uterine\s*(?:and\s*)?(?:cancer|tumou?r|carcinoma)|uterus\s*(?:and\s*)?(?:cancer|tumou?r|carcinoma)|endometrial\s*(?:and\s*)?(?:cancer|tumou?r|carcinoma)',
        "score_terms": ["uterine cancer", "endometrial cancer", "carcinoma"],
    },
}

OTHER_DISEASE_TERMS = [
    "breast", "ovarian", "ovary", "uterine", "uterus", "endometrial",
    "colon", "colorectal", "lung", "prostate", "liver", "gastric", "cervical",
    "neonate", "infant", "child", "non-alcoholic", "fatty liver", "bladder",
    "alzheimer", "dementia", "parkinson", "neurological",
]

def get_disease_alias(disease):
    """Return disease-specific query and filtering aliases for supported scopes."""
    key = str(disease or "").lower().strip()
    return DISEASE_ALIASES.get(key, {
        "query": disease,
        "terms": [key] if key else [],
        "patient_phrases": [],
        "pattern": re.escape(key) if key else "",
        "score_terms": [key] if key else [],
    })

def get_openai_model_name(model_override=None):
    model_name = model_override or os.getenv("OPENAI_MODEL_NAME", "openai.gpt-4o")
    base_url = os.getenv("OPENAI_BASE_URL")
    if not base_url:
        if model_name.startswith("openai."):
            model_name = model_name[7:]
        if model_name == "gpt-4.1":
            model_name = "gpt-4o"
    return model_name

def is_disease_relevant(text, disease):
    alias = get_disease_alias(disease)
    if alias["pattern"] and re.search(alias["pattern"], text, re.IGNORECASE):
        return True
    disease_lower = str(disease or "").lower().strip()
    if disease_lower and disease_lower in text:
        return True
    
    # Allow matches where a disease-specific term (e.g., 'breast') and a cancer term both appear in the text
    text_lower = text.lower()
    cancer_terms = ["cancer", "carcinoma", "tumour", "tumor"]
    if any(ct in text_lower for ct in cancer_terms):
        if alias.get("terms") and any(term.lower() in text_lower for term in alias["terms"]):
            return True
            
    return False

def has_other_disease_conflict(title, disease):
    alias_terms = set(get_disease_alias(disease)["terms"])
    title_lower = title.lower()
    if any(term and term in title_lower for term in alias_terms):
        return False
    disease_lower = str(disease or "").lower().strip()
    if disease_lower and disease_lower in title_lower:
        return False
    return any(term in title_lower for term in OTHER_DISEASE_TERMS if term not in alias_terms)

def patient_phrase_in_title(title, disease):
    title_lower = title.lower()
    return any(phrase in title_lower for phrase in get_disease_alias(disease)["patient_phrases"])

# Initialize Clients
load_dotenv(os.path.join(BASE_DIR, "mykey.env"))
try:
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=base_url)
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    client = None

# Initialize Gemini
try:
    gemini_key = os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        gemini_client = genai.Client(api_key=gemini_key)
        # Use a string for the model name in the new SDK
        gemini_model_name = 'gemini-2.5-flash'
    else:
        gemini_client = None
        gemini_model_name = None
except Exception as e:
    print(f"Gemini init failed: {e}")
    gemini_client = None
    gemini_model_name = None


USAGE_FILE = os.path.join(DATA_DIR, 'usage_stats.json')
LAST_ANALYSIS_FILE = os.path.join(DATA_DIR, 'last_analysis_usage.json')

def track_usage(model_name, input_tokens, output_tokens):
    # --- Cumulative all-time stats ---
    stats = {}
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, 'r') as f:
                stats = json.load(f)
        except:
            pass
    
    if model_name not in stats:
        stats[model_name] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    
    stats[model_name]["input_tokens"] += input_tokens
    stats[model_name]["output_tokens"] += output_tokens
    stats[model_name]["calls"] += 1
    
    try:
        with open(USAGE_FILE, 'w') as f:
            json.dump(stats, f, indent=4)
    except Exception as e:
        print(f"Error saving usage: {e}")

    # --- Per-analysis stats (current run only) ---
    last = {}
    if os.path.exists(LAST_ANALYSIS_FILE):
        try:
            with open(LAST_ANALYSIS_FILE, 'r') as f:
                last = json.load(f)
        except:
            pass

    if model_name not in last:
        last[model_name] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    last[model_name]["input_tokens"] += input_tokens
    last[model_name]["output_tokens"] += output_tokens
    last[model_name]["calls"] += 1

    try:
        with open(LAST_ANALYSIS_FILE, 'w') as f:
            json.dump(last, f, indent=4)
    except Exception as e:
        print(f"Error saving last-analysis usage: {e}")

def eggers_test(log_es, log_se):
    """
    Performs Egger's regression test for funnel plot asymmetry.
    Regression: Standardized Effect ~ 1/SE (Precision)
    """
    if len(log_es) < 3:
        return None, None
    
    precision = 1.0 / log_se
    std_effect = log_es / log_se
    
    X = sm.add_constant(precision)
    model = sm.OLS(std_effect, X).fit()
    
    # The intercept (const) indicates asymmetry
    intercept = model.params.get('const', 0)
    p_value = model.pvalues.get('const', 1.0)
    
    return intercept, p_value

def perform_leave_one_out(df):
    """
    Iteratively performs meta-analysis excluding one study at a time.
    """
    results = []
    studies = df.index.tolist()
    
    for i in range(len(df)):
        subset = df.drop(df.index[i])
        if len(subset) < 2:
            continue
            
        res = combine_effects(subset['log_ES'], subset['var'], method_re='dl')
        summary = res.summary_frame().iloc[-1] # Random effects row
        
        results.append({
            "omitted": studies[i],
            "pooled_es": np.exp(summary['eff']),
            "ci_low": np.exp(summary['ci_low']),
            "ci_upp": np.exp(summary['ci_upp']),
            "is_significant": (summary['ci_low'] > 0) or (summary['ci_upp'] < 0)
        })
    
    return results

def capitalize_sentences(text):
    """Lowercases the string then capitalizes the start of each sentence, while preserving 'CI' and 'Vitamin X'."""
    if not text:
        return text
    text = text.lower()
    # Capitalize the very first character
    text = text[0].upper() + text[1:]
    # Capitalize characters following a period and space
    text = re.sub(r'\.\s+([a-z])', lambda m: ". " + m.group(1).upper(), text)
    # Restore CI
    text = re.sub(r'\bci\b', 'CI', text)
    # Restore I²
    text = text.replace('i²', 'I²')
    # Restore Vitamin casing (Vitamin A, Vitamin B12, etc.)
    text = re.sub(r'\bvitamin\s+([a-z])', lambda m: "Vitamin " + m.group(1).upper(), text)
    # Restore known acronyms
    text = re.sub(r'\bbcaas\b', 'BCAAs', text)
    return text

# Map of lowercase exposure names -> their correct display capitalisation.
_EXPOSURE_DISPLAY_MAP = {
    "bcaas": "BCAAs",
    "bcaa":  "BCAA",
}

def normalise_exposure_display(exposure: str) -> str:
    """Return the correctly capitalised display name for a known exposure acronym,
    otherwise return the original string unchanged."""
    return _EXPOSURE_DISPLAY_MAP.get(exposure.lower().strip(), exposure)

def get_funnel_interpretation(disease, exposure, n_studies, eggers_p, intercept):
    """
    Provides a brief rule-based interpretation of the funnel plot and Egger's test.
    """
    if eggers_p is None:
        interpretation = "Insufficient studies to perform formal publication bias testing."
    elif eggers_p < 0.05:
        interpretation = f"The significant funnel plot asymmetry (Egger's p={eggers_p:.4f}) indicates substantial publication bias in this meta-analysis on {exposure} and {disease}. This specific pattern suggests that smaller studies with smaller or null effects may be underrepresented, compromising the reliability of the pooled estimate and potentially leading to an overestimation of the true association."
    else:
        interpretation = f"Egger's test indicates no significant funnel plot asymmetry (p={eggers_p:.4f}). The distribution of studies appears symmetric, suggesting a lower risk of publication bias."

    return capitalize_sentences(interpretation)

def get_results_interpretation(disease, exposure, outcome, n_studies, pooled_es, ci_low, ci_upp, i2, stat_interpretation):
    """
    Provides a brief, non-causal rule-based interpretation of the meta-analysis results.
    """
    # Parse the statistical interpretation for direction and significance
    is_sig = "not" not in stat_interpretation.lower()
    
    is_decreased = "decreased" in stat_interpretation.lower() or (pooled_es is not None and float(pooled_es) < 1.0)
    is_increased = "increased" in stat_interpretation.lower() or (pooled_es is not None and float(pooled_es) > 1.0)
    
    # Handle I2 interpretation
    try:
        i2_val = float(i2)
    except:
        i2_val = 0

    if i2_val < 25:
        het_text = "low between-study heterogeneity"
        het_implication = "indicating consistent findings across the included studies"
    elif i2_val < 50:
        het_text = "moderate between-study heterogeneity"
        het_implication = "suggesting some variability in the results across studies"
    elif i2_val < 75:
        het_text = "substantial between-study heterogeneity"
        het_implication = "reflecting considerable variability across studies"
    else:
        het_text = "very high between-study heterogeneity"
        het_implication = "reflecting highly inconsistent results across studies"

    if is_sig:
        dir_text = "higher risk" if is_increased else "lower risk"
        interpretation = f"The pooled analysis of {n_studies} studies yielded an overall effect size of {pooled_es} (95% CI: {ci_low}–{ci_upp}), suggesting that {exposure} is associated with a {dir_text} of {disease}. "
        if i2_val >= 50:
            interpretation += f"However, this association should be interpreted with caution, as there was {het_text} (I² = {i2_val:.2f}%), {het_implication}."
        else:
            interpretation += f"These findings were supported by {het_text} (I² = {i2_val:.2f}%), {het_implication}."
    else:
        rel_text = "positive" if is_increased else "inverse"
        interpretation = f"The pooled analysis of {n_studies} studies yielded an effect size of {pooled_es} (95% CI: {ci_low}–{ci_upp}), indicating no statistically significant association between {exposure} and {disease}. "
        interpretation += f"Although the point estimate suggests a potential {rel_text} relationship, the confidence interval includes the null. "
        interpretation += f"These findings were accompanied by {het_text.replace('between-study ', '')} (I² = {i2_val:.2f}%), {het_implication}."

    return capitalize_sentences(interpretation)

def generate_baujat_plot(df, disease, exposure, outcome="Incidence", exclude_meta=False):
    """
    Generates a Baujat plot to identify studies contributing to heterogeneity and influence.
    X: Contribution to Q (heterogeneity)
    Y: Influence on pooled effect
    """
    print(f"DEBUG Baujat: Called with {len(df)} studies, columns: {list(df.columns)}")
    if len(df) < 3:
        print(f"DEBUG Baujat: Skipping, need >= 3 studies, got {len(df)}")
        return None
        
    # X: (observed - predicted)^2 / variance
    # Y: (pooled_all - pooled_without_i)^2 / var_pooled_all
    
    res_all = combine_effects(df['log_ES'], df['var'], method_re='dl')
    summary_all = res_all.summary_frame().iloc[-1]  # Random effects row
    pooled_all = float(summary_all['eff'])
    var_all = float(summary_all['sd_eff'])**2  # var = sd^2
    
    q_contributions = []
    influence = []
    
    for i in range(len(df)):
        # Q contribution
        qi = float(((df['log_ES'].iloc[i] - pooled_all)**2) / df['var'].iloc[i])
        q_contributions.append(qi)
        
        # Influence
        subset = df.drop(df.index[i])
        res_sub = combine_effects(subset['log_ES'], subset['var'], method_re='dl')
        sub_summary = res_sub.summary_frame().iloc[-1]
        sub_eff = float(sub_summary['eff'])
        inf = float(((pooled_all - sub_eff)**2) / var_all) if var_all > 0 else 0.0
        influence.append(inf)
        
    plt.figure(figsize=(8, 6))
    plt.scatter(q_contributions, influence, alpha=0.6, edgecolors='k')
    
    for i, txt in enumerate(df.index):
        plt.annotate(str(txt), (float(q_contributions[i]), float(influence[i])), fontsize=8, alpha=0.7)
        
    plt.xlabel('Contribution to Heterogeneity (Q)')
    plt.ylabel('Influence on Pooled Effect')
    plt.title(f'Baujat Plot: {disease} vs {exposure}')
    plt.grid(True, alpha=0.2)
    
    safe_disease = re.sub(r'[^a-zA-Z0-9]+', '_', disease.lower()).strip('_')
    safe_exposure = re.sub(r'[^a-zA-Z0-9]+', '_', exposure.lower()).strip('_')
    safe_outcome = re.sub(r'[^a-zA-Z0-9]+', '_', outcome.lower()).strip('_')
    safe_meta = "primary" if exclude_meta else "all"
    # Create exposure subfolder
    exposure_dir = os.path.join("static", safe_exposure)
    os.makedirs(exposure_dir, exist_ok=True)
    
    path = os.path.join(exposure_dir, f"baujat_{safe_disease}_{safe_outcome}_{safe_meta}.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path


def is_genetic(row):
    """
    Identifies studies that are genetic in nature (SNPs, polymorphisms, etc.)
    based on keywords in the reference/study description.
    """
    ref = str(row.get('Reference', '')).lower()
    study_name = str(row.get('Study', '')).lower()
    
    genetic_keywords = [
        'polymorphism', 'genotype', 'variant', 'codon', 'snp', 'allele', 
        'mutation', 'genetics'
    ]
    
    # Check Reference and Study name (fast check, matches spreadsheet logic)
    for kw in genetic_keywords:
        if kw in ref or kw in study_name:
            return True
            
    return False

def get_analysis_data(disease, exposure, outcome="Incidence", exclude_meta=False, use_downstream=True, model=None):
    """
    Main entry point for web app. Returns a dict with results.
    """
    # Normalise display name for known acronyms (e.g. bcaas -> BCAAs)
    exposure = normalise_exposure_display(exposure)

    # Reset per-analysis usage counter at the start of every new run
    try:
        with open(LAST_ANALYSIS_FILE, 'w') as f:
            json.dump({}, f)
    except Exception:
        pass

    print(f"[MetaFemina] Analyzing: {disease} vs {exposure} (Outcome: {outcome}, Exclude Meta/Reviews: {exclude_meta}, Use Downstream: {use_downstream})")
    print("[MetaFemina] Stage 1/4: Searching PubMed...")
    ids = search_pubmed(disease, exposure, outcome=outcome, exclude_meta=exclude_meta, max_results=5000)

    print(f"[MetaFemina] Stage 2/4: Fetching details for {len(ids)} PubMed records...")
    articles = fetch_details(ids)

    # Get full synonym list for better relevance matching across both extraction engines
    syn_dict = get_equivalent_terms(exposure)
    core_str = syn_dict.get("core", "")
    all_terms_str = ", ".join(filter(None, [core_str, syn_dict.get("downstream", "")]))
    synonyms = [s.strip().lower() for s in all_terms_str.split(',')] if all_terms_str else []
    synonyms.append(exposure.lower())
    
    # Parse and add anchored synonym term prefixes (e.g. "mediterranean" from "Mediterranean:diet")
    anchored_terms = []
    anch_str = syn_dict.get("anchored", "")
    if anch_str:
        for pair in [p.strip() for p in anch_str.split(',') if p.strip()]:
            if ':' in pair:
                anchored_terms.append(pair.split(':', 1)[0].strip().lower())
    synonyms.extend(anchored_terms)
    synonyms = list(set([s for s in synonyms if len(s) > 2]))

    # Core-only synonym list for relevance filtering when use_downstream=False
    core_synonyms = [s.strip().lower() for s in core_str.split(',')] if core_str else []
    core_synonyms.append(exposure.lower())
    core_synonyms.extend(anchored_terms)
    core_synonyms = list(set([s for s in core_synonyms if len(s) > 2]))

    # Try LLM Extraction First
    df = pd.DataFrame()
    try:
        print(f"[MetaFemina] Stage 3/4: Extracting study data from {len(articles)} records with LLM assistance...")
        df = extract_data_llm(articles, exclude_meta=exclude_meta, exposure_keyword=exposure, disease_keyword=disease, outcome_keyword=outcome, synonyms=synonyms, use_downstream=use_downstream, core_synonyms=core_synonyms, model=model)
    except Exception as e:
        print(f"LLM Extraction failed: {e}")

    # Fallback to Regex if LLM failed or returned no data
    if df.empty:
        print("[MetaFemina] Falling back to Regex extraction...")
        df = extract_data(articles, exclude_meta=exclude_meta, exposure_keyword=exposure, disease_keyword=disease, outcome_keyword=outcome, synonyms=synonyms, use_downstream=use_downstream, core_synonyms=core_synonyms)

    if df.empty:
        return {"error": "No relevant evidence was identified in the reviewed sources."}

    # Initialize exclusions column to 0
    df['exclusions'] = 0
    
    # Apply verification consensus and exclusions overlay if available
    verifications_file = os.path.join(DATA_DIR, "verifications.json")
    if os.path.exists(verifications_file):
        try:
            with open(verifications_file, 'r', encoding='utf-8') as f:
                verifications = json.load(f)
            
            canonical_exp = get_canonical_name(exposure)
            context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
            
            overlay_count = 0
            for idx, row in df.iterrows():
                pmid = str(row.get("PMID", ""))
                if pmid in verifications:
                    v_info = verifications[pmid]
                    
                    # Set exclusions
                    context_excl = v_info.get("context_exclusions", {})
                    exclusion_val = context_excl.get(context_key, 0)
                    df.at[idx, 'exclusions'] = exclusion_val
                    
                    # Apply consensus data
                    contexts = v_info.get("contexts", {})
                    if context_key in contexts:
                        consensus = contexts[context_key].get("consensus_data")
                        if consensus:
                            for key, val in consensus.items():
                                if val is not None and val != "":
                                    df_col = key
                                    if key == "Comparison Type":
                                        df_col = "comparison_type"
                                    
                                    if df_col in df.columns:
                                        # Cast appropriately
                                        if df_col in ["Effect Size", "Lower CI", "Upper CI", "Cases", "Sample Size"]:
                                            try:
                                                df.at[idx, df_col] = float(val) if df_col not in ["Cases", "Sample Size"] else int(val)
                                            except (ValueError, TypeError):
                                                df.at[idx, df_col] = val
                                        else:
                                            df.at[idx, df_col] = val
                            overlay_count += 1
            if overlay_count > 0:
                print(f"  [Overlay] Applied verification consensus to {overlay_count} studies in get_analysis_data")
        except Exception as e:
            print(f"Error applying verification overlay to dataframe: {e}")
            
    # Filter out studies that have been excluded (exclusions >= 2)
    df_len_before = len(df)
    df = df[df['exclusions'] < 2].copy()
    df_len_after = len(df)
    if df_len_after < df_len_before:
        print(f"  [Overlay] Filtered out {df_len_before - df_len_after} excluded studies (exclusions >= 2) from analysis.")

    df['SE'] = df.apply(calculate_se, axis=1)
    df_clean = df.dropna(subset=['Effect Size', 'SE'])

    if df_clean.empty:
        return {"error": "No relevant evidence was identified in the reviewed sources."}

    print(f"[MetaFemina] Stage 4/4: Running meta-analysis on {len(df_clean)} extracted studies...")
    return perform_meta_analysis(df_clean, disease, exposure=exposure, outcome=outcome, exclude_meta=exclude_meta, df_all=df_clean)

def perform_meta_analysis(df_clean, disease, exposure, outcome="Incidence", exclude_meta=False, df_all=None):
    """
    Performs random-effects meta-analysis on the provided DataFrame.
    """
    if df_all is None:
        df_all = df_clean

    safe_disease = re.sub(r'[^a-zA-Z0-9]+', '_', disease.lower()).strip('_')
    safe_exposure = re.sub(r'[^a-zA-Z0-9]+', '_', exposure.lower()).strip('_')
    safe_outcome = re.sub(r'[^a-zA-Z0-9]+', '_', outcome.lower()).strip('_')
    safe_meta = "primary" if exclude_meta else "all"

    # Sort by Effect Size for consistent display (Table and Plot)
    df_clean = df_clean.sort_values(by='Effect Size', ascending=True)

    # Meta-Analysis
    # Log transformation logic (using Estimated RR for pooling)
    p0 = 0.13
    
    def convert_to_rr(es, eff_type):
        if es is None or np.isnan(es) or es <= 0:
            return es
        eff_type_str = str(eff_type).upper().strip()
        if eff_type_str in ['OR', 'ODDS RATIO']:
            return es / (1 - p0 + (p0 * es))
        elif eff_type_str in ['HR', 'HAZARD RATIO']:
            return (1 / p0) * (1 - np.exp(es * np.log(1 - p0)))
        else:
            return es # Assume RR or other

    df_clean['converted_ES'] = df_clean.apply(lambda x: convert_to_rr(x['Effect Size'], x['Effect Type']), axis=1)
    df_clean['converted_Lower_CI'] = df_clean.apply(lambda x: convert_to_rr(x['Lower CI'], x['Effect Type']), axis=1)
    df_clean['converted_Upper_CI'] = df_clean.apply(lambda x: convert_to_rr(x['Upper CI'], x['Effect Type']), axis=1)

    df_clean['log_ES'] = df_clean.apply(lambda x: np.log(x['converted_ES']) if x['Effect Type'].upper() in ['OR', 'RR', 'HR', 'ODDS RATIO', 'RISK RATIO'] and x['converted_ES'] > 0 else x['converted_ES'], axis=1)
    
    def calc_log_se(row):
        eff_type_str = str(row['Effect Type']).upper().strip()
        if eff_type_str in ['OR', 'RR', 'HR', 'ODDS RATIO', 'RISK RATIO'] and row['converted_Lower_CI'] > 0 and row['converted_Upper_CI'] > 0:
             return (np.log(row['converted_Upper_CI']) - np.log(row['converted_Lower_CI'])) / 3.92
        return row['SE']

    df_clean['log_SE'] = df_clean.apply(calc_log_se, axis=1)
    df_clean['var'] = df_clean['log_SE'] ** 2
    
    # Set index to Study for better summary labels
    # Set index to Study for better summary labels
    analysis_df = df_clean.set_index('Study')
    
    try:
        baujat_url = None
        if len(analysis_df) < 2:
            # Handling Single Study: Use original raw values to match exactly
            if len(analysis_df) == 1:
                row = analysis_df.iloc[0]
                pooled_es = row['converted_ES']
                pooled_lower = row['converted_Lower_CI']
                pooled_upper = row['converted_Upper_CI']
            else:
                 # Empty
                 pooled_es = 0
                 pooled_lower = 0
                 pooled_upper = 0

            
            # Create a dummy summary_df just to satisfy variable existence for summary_html (even if unused)
            summary_df = pd.DataFrame({
                'Cases': [row['Cases'] if len(analysis_df) == 1 else 0],
                'Sample Size': [row['Sample Size'] if len(analysis_df) == 1 else 0],
                'Effect': [pooled_es],
                '95% CI lower': [pooled_lower],
                '95% CI upper': [pooled_upper]
            }, index=['Pooled Result (Single Study)'])
            summary = summary_df.to_html(classes='table table-striped', header=True)

            # Interpretation logic
            is_significant = (pooled_lower > 1) or (pooled_upper < 1) 
            # Note: The above significance check assumes Ratio (null=1). 
            # If not ratio (e.g. 0), it should be diff > 0. 
            # Use confidence interval crossing null hypothesis check based on CI signs?
            # Actually, standard way: if lower and upper are on same side of Null.
            # Ratios are always > 0.
            
            # Let's improve significance check based on type
            eff_type = row['Effect Type'] if len(analysis_df) == 1 else 'OR' # Default to OR for interpretation if empty
            if eff_type in ['OR', 'RR', 'HR', 'ODDS RATIO', 'RISK RATIO']:
                 is_significant = (pooled_lower > 1) or (pooled_upper < 1)
                 log_eff = np.log(pooled_es) if pooled_es > 0 else 0 # For direction check
            else:
                 # Linear scale, null is 0
                 is_significant = (pooled_lower > 0 and pooled_upper > 0) or (pooled_lower < 0 and pooled_upper < 0)
                 log_eff = pooled_es # Just for direction
            
            interpretation = "statistically significant" if is_significant else "not statistically significant"
            if is_significant:
                 direction = "increased risk/odds" if log_eff > 0 else "decreased risk/odds"
                 interpretation += f" ({direction})"
            
            def sanitize(val):
                if val is None: return None
                try:
                    if np.isnan(val) or np.isinf(val): return None
                    return float(round(val, 2))
                except:
                    return None

            headline = {
                 "pooled_es": sanitize(pooled_es),
                 "ci_low": sanitize(pooled_lower),
                 "ci_upp": sanitize(pooled_upper),
                 "interpretation": interpretation
            }
            
        else:
            res = combine_effects(analysis_df['log_ES'], analysis_df['var'], method_re='dl')
            summary_df = res.summary_frame()
            
            # Explicitly update the index
            n_studies = len(analysis_df)
            new_index = list(analysis_df.index) + list(summary_df.index[n_studies:])
            summary_df.index = new_index
            
            # Cleanup table columns
            cols_to_drop = ['w_fe', 'w_re']
            summary_df = summary_df.drop(columns=cols_to_drop, errors='ignore')
            
            # Add Cases and Sample Size from analysis_df
            summary_df['Cases'] = analysis_df['Cases']
            summary_df['Sample Size'] = analysis_df['Sample Size']
            
            # Fill NaN for the pooled rows (since they aren't in analysis_df)
            summary_df['Cases'] = summary_df['Cases'].fillna('-')
            summary_df['Sample Size'] = summary_df['Sample Size'].fillna('-')
            
            # Rename columns
            summary_df = summary_df.rename(columns={
                'eff': 'Effect',
                'sd_eff': 'SD Effect',
                'ci_low': '95% CI lower',
                'ci_upp': '95% CI upper'
            })
            
            # Rename rows
            summary_df = summary_df.rename(index={
                'random effect wls': 'Random-effects meta-analysis (WLS)',
                'fixed effect wls': 'Fixed-effect meta-analysis (WLS)'
            })

            summary_df = summary_df.round(4)
            
            # Display DF
            display_df = summary_df.copy()
            rows_to_drop = ['Fixed-effect meta-analysis (WLS)', 'Random-effects meta-analysis (WLS)']
            rows_to_drop.extend(['fixed effect wls', 'random effect wls', 'fixed effect', 'random effect'])
            display_df = display_df.drop(index=[r for r in rows_to_drop if r in display_df.index], errors='ignore')
            
            summary = display_df.to_html(classes='table table-striped', header=True)
            
            # Extract Headline
            try:
                # Handle potential row naming variations from statsmodels combine_effects
                # Check for negative tau2 which causes numerical overflow in some DL implementations
                # where heterogeneity is extremely low (Q < df).
                re_keywords = ['random effect wls', 'random effect', 'Random-effects meta-analysis (WLS)']
                re_row = None
                
                is_invalid_re = False
                if getattr(res, 'tau2', 0) < 0:
                    is_invalid_re = True
                
                if not is_invalid_re:
                    for kw in re_keywords:
                        if kw in summary_df.index:
                            re_row = summary_df.loc[kw]
                            break
                
                if re_row is None or is_invalid_re:
                    # Fallback to fixed effect if random effect is invalid or not found
                    fe_keywords = ['fixed effect wls', 'fixed effect', 'Fixed-effect meta-analysis (WLS)']
                    for kw in fe_keywords:
                        if kw in summary_df.index:
                            re_row = summary_df.loc[kw]
                            if is_invalid_re:
                                print(f"WARNING: Negative tau2 ({res.tau2}) detected. Falling back to fixed effect.")
                            break
                
                if re_row is None:
                    # Fallback to last row if keywords not found
                    re_row = summary_df.iloc[-1]
            
                # DEBUG: Print types and values to find 'Series' culprit
                print(f"DEBUG: re_row type: {type(re_row)}")
                
                log_eff = float(re_row['Effect'].iloc[0]) if isinstance(re_row['Effect'], pd.Series) else float(re_row['Effect'])
                log_ci_low = float(re_row['95% CI lower'].iloc[0]) if isinstance(re_row['95% CI lower'], pd.Series) else float(re_row['95% CI lower'])
                log_ci_upp = float(re_row['95% CI upper'].iloc[0]) if isinstance(re_row['95% CI upper'], pd.Series) else float(re_row['95% CI upper'])
                
                print(f"DEBUG: log_eff: {log_eff} (type: {type(log_eff)})")
                
                pooled_es = np.exp(log_eff)
                pooled_lower = np.exp(log_ci_low)
                pooled_upper = np.exp(log_ci_upp)
                
                is_significant = (log_ci_low > 0) or (log_ci_upp < 0)
                
                interpretation = "statistically significant" if is_significant else "not statistically significant"
                
                if is_significant:
                    direction = "increased risk/odds" if log_eff > 0 else "decreased risk/odds"
                    interpretation += f" ({direction})"
                
                def sanitize(val):
                    if val is None: return None
                    try:
                        if np.isnan(val) or np.isinf(val): return None
                        return float(round(val, 2))
                    except:
                        return None

                # Heterogeneity metrics from statsmodels res object
                # Truncate to 0 if negative (standard practice for DL method when Q < df)
                i2 = max(0, getattr(res, 'i2', 0))
                tau2 = max(0, getattr(res, 'tau2', 0))
                
                print(f"DEBUG: i2: {i2} (type: {type(i2)}), tau2: {tau2} (type: {type(tau2)})")

                # Prediction Interval
                pi_lower = None
                pi_upper = None
                if n_studies >= 3:
                    try:
                        import scipy.stats
                        t_val = scipy.stats.t.ppf(0.975, df=n_studies-2)
                        var_pooled = float(re_row['SD Effect'].iloc[0]**2) if isinstance(re_row['SD Effect'], pd.Series) else float(re_row['SD Effect']**2)
                        se_pred = np.sqrt(tau2 + var_pooled)
                        pi_lower = np.exp(log_eff - t_val * se_pred)
                        pi_upper = np.exp(log_eff + t_val * se_pred)
                    except Exception as e:
                        print(f"PI calculation failed: {e}")

                # Egger's Test
                eggers_intercept, eggers_p = eggers_test(analysis_df['log_ES'], analysis_df['log_SE'])
                print(f"DEBUG: eggers_p: {eggers_p} (type: {type(eggers_p)})")
                
                # Funnel interpretation (non-fatal)
                funnel_interpretation = 'no interpretation available.'
                try:
                    funnel_interpretation = get_funnel_interpretation(disease, exposure, len(analysis_df), eggers_p, eggers_intercept)
                except Exception as e:
                    print(f"Funnel interpretation generation failed (non-fatal): {e}")

                # Baujat Plot (non-fatal)
                baujat_url = None
                try:
                    baujat_path = generate_baujat_plot(analysis_df, disease, exposure, outcome=outcome, exclude_meta=exclude_meta)
                    if baujat_path:
                        baujat_url = f"{baujat_path}?t=" + str(np.random.randint(0,10000))
                        print(f"DEBUG Baujat: Generated at {baujat_path}")
                except Exception as e:
                    print(f"Baujat plot generation failed (non-fatal): {e}")
                    import traceback
                    traceback.print_exc()

                # Leave-one-out analysis (non-fatal)
                loo_results = []
                try:
                    loo_results = perform_leave_one_out(analysis_df)
                except Exception as e:
                    print(f"Leave-one-out analysis failed (non-fatal): {e}")

                def sanitize_pvalue(val):
                    if val is None: return None
                    try:
                        if np.isnan(val) or np.isinf(val): return None
                        return float(val)
                    except:
                        return None
                        
                headline = {
                    "pooled_es": sanitize(pooled_es),
                    "ci_low": sanitize(pooled_lower),
                    "ci_upp": sanitize(pooled_upper),
                    "pi_low": sanitize(pi_lower),
                    "pi_upp": sanitize(pi_upper),
                    "interpretation": capitalize_sentences(interpretation),
                    "i2": sanitize(i2 * 100), # Percentage
                    "tau2": sanitize(tau2),
                    "eggers_p": sanitize_pvalue(eggers_p),
                    "funnel_interpretation": funnel_interpretation,
                    "loo_results": loo_results
                }

                # Generate LLM interpretation (non-fatal)
                try:
                    results_interp = get_results_interpretation(
                        disease, exposure, outcome, len(analysis_df),
                        sanitize(pooled_es), sanitize(pooled_lower), sanitize(pooled_upper),
                        sanitize(i2 * 100), interpretation
                    )
                    headline["results_interpretation"] = results_interp
                except Exception as e:
                    print(f"Results interpretation generation failed (non-fatal): {e}")
                    headline["results_interpretation"] = ""

            except Exception as e:
                print(f"Error parsing summary stats: {e}")
                headline = None
        
        try:
            # Calculate dynamic height based on number of studies to avoid overcrowding
            fp_df = df_clean.copy()
            num_studies = len(fp_df)
            
            # More aggressive dynamic height scaling
            # Default: 0.4 inch per study. 
            # If studies > 70, increase to 0.6 inch per study for a "longer" plot.
            if num_studies > 70:
                dynamic_height = max(7, 0.6 * num_studies + 5)
            else:
                dynamic_height = max(7, 0.4 * num_studies + 3.5) 
            
            # Dynamic font scaling
            if num_studies < 15: font_size = 10
            elif num_studies < 30: font_size = 8
            elif num_studies < 60: font_size = 6
            else: font_size = 5 # Smallest tier for extreme density
            
            plt.rcParams.update({'font.size': font_size})
            
            plt.figure(figsize=(12, dynamic_height)) # Increased width for annotations
            if not fp_df.empty:
                fp_df = fp_df.rename(columns={'Study': 'group', 'log_ES': 'est'})
                fp_df['lb'] = fp_df['est'] - 1.96 * fp_df['log_SE']
                fp_df['ub'] = fp_df['est'] + 1.96 * fp_df['log_SE']
                fp_df['label'] = fp_df['group']
                
                # Add human-readable annotation column for the plot using converted values
                def format_ci(row):
                    try:
                        return f"{float(row['converted_ES']):.2f} ({float(row['converted_Lower_CI']):.2f}, {float(row['converted_Upper_CI']):.2f})"
                    except:
                        return "N/A"
                
                fp_df['Est. RR (95% CI)'] = fp_df.apply(format_ci, axis=1)
                
                # Log scale check for xlabel
                is_log = any(str(row['Effect Type']).upper() in ['OR', 'RR', 'HR', 'ODDS RATIO', 'RISK RATIO'] for _, row in fp_df.iterrows())
                xlbl = "Log Relative Risk (95% CI)" if is_log else "Effect Size (95% CI)"
                
                forestplot.forestplot(
                    fp_df,
                    estimate="est",
                    ll="lb",
                    hl="ub",
                    varlabel="label",
                    right_ann_col=['Est. RR (95% CI)'],
                    right_ann_kwargs={'header': 'Est. RR (95% CI)', 'fontsize': font_size},
                    xlabel=xlbl,
                    title=f"Forest Plot: {disease} vs {exposure}",
                    flush=True, # Left flush labels for cleaner look
                    shade_alt_rows=True # Alternate shading for readability
                )
                
                # Create exposure subfolder
                exposure_dir = os.path.join("static", safe_exposure)
                os.makedirs(exposure_dir, exist_ok=True)
                
                # Generate unique filename using pre-defined safe strings
                filename_base = f"forest_{safe_disease}_{safe_outcome}_{safe_meta}.png"
                
                plot_path = os.path.join(exposure_dir, filename_base)
                plt.savefig(plot_path, bbox_inches='tight')
            plt.close() 
        except Exception as e:
            print(f"Forest plot failed: {e}")
            plt.close()

        # Funnel Plot
        try:
            if not df_clean.empty and 'pooled_es' in locals() and pooled_es > 0:
                plt.figure(figsize=(8, 6))
                
                # Data points
                plt.scatter(df_clean['log_ES'], df_clean['SE'], alpha=0.6, edgecolors='k')
                
                # Pooled Effect Line
                pooled_log = np.log(pooled_es)
                plt.axvline(x=pooled_log, color='red', linestyle='--', label='Pooled Effect')
                
                # Pseudo 95% CI Triangle
                max_se = df_clean['SE'].max()
                if not np.isnan(max_se) and max_se > 0:
                    max_se_padded = max_se * 1.1
                    se_seq = np.linspace(0, max_se_padded, 100)
                    
                    ci_left = pooled_log - 1.96 * se_seq
                    ci_right = pooled_log + 1.96 * se_seq
                    
                    plt.plot(ci_left, se_seq, 'k--', alpha=0.3)
                    plt.plot(ci_right, se_seq, 'k--', alpha=0.3)
                    
                    # Invert Y axis (SE 0 is top)
                    plt.ylim(max_se_padded, 0)
                
                plt.xlabel('Log Effect Size')
                plt.ylabel('Standard Error')
                plt.title(f'Funnel Plot: {disease} vs {exposure}')
                plt.grid(True, alpha=0.2)
                
                # Generate unique filename for funnel plot using pre-defined safe strings
                funnel_filename = f"funnel_{safe_disease}_{safe_outcome}_{safe_meta}.png"
                exposure_dir = os.path.join("static", safe_exposure)
                os.makedirs(exposure_dir, exist_ok=True)
                
                funnel_path = os.path.join(exposure_dir, funnel_filename)
                plt.savefig(funnel_path, bbox_inches='tight')
                plt.close() 
        except Exception as e:
            print(f"Funnel plot failed: {e}")
            plt.close()
        
        # Convert df to records
        # Use df_all for the return list so the table shows everything
        # Gracefully handle missing columns (like 'Sample Size' or 'Cases' if regex/llm both missed them)
        cols_to_keep = ['Study', 'PMID', 'Effect Size', 'Lower CI', 'Upper CI', 'Population', 'Reference', 'Authors', 'Journal', 'Year', 'Link', 'Effect Type', 'SE', 'Sample Size', 'Cases', 'Estimated Cases', 'Design', 'Timing', 'Continent', 'Stage', 'Quality %', 'Quality Score', 'comparison_type', 'JBI']
        
        # Ensure columns exist in df_all
        for col in cols_to_keep:
            if col not in df_all.columns:
                df_all[col] = "-"
                
        studies_data = df_all[cols_to_keep].to_dict(orient='records')
        
        return {
            "success": True,
            "studies": studies_data,
            "summary_html": summary,
            "headline": headline,
            "plot_url": f"static/{safe_exposure}/forest_{safe_disease}_{safe_outcome}_{safe_meta}.png?t=" + str(np.random.randint(0,10000)),
            "funnel_plot_url": f"static/{safe_exposure}/funnel_{safe_disease}_{safe_outcome}_{safe_meta}.png?t=" + str(np.random.randint(0,10000)),
            "baujat_plot_url": baujat_url
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Meta-analysis failed: {str(e)}"}

# Keep main for CLI usage but renamed/refactored if needed, or just let the new function handle it.
# We will modify the existing main to use this new function if we wanted to keep CLI, 
# but for now I'm just injecting the function to be used by Flask.


# Load environment variables
load_dotenv('mykey.env')

# Setup Entrez
Entrez.email = os.getenv('PUBMED_EMAIL', 'your_email@example.com')
Entrez.api_key = os.getenv('PUBMED_API_KEY') # Optional, increases rate limits

SYNONYMS_CACHE = os.path.join(DATA_DIR, 'synonyms_cache.json')

def get_equivalent_terms(exposure):
    """
    Uses LLM to curate equivalent terms for a nutritional exposure.
    Results are cached locally to minimize API calls.
    """
    if not exposure:
        return ""
        
    if exposure.lower() == "caffeine":
        return {"core": "caffeine, coffee", "downstream": "tea, energy drinks"}
    if exposure.lower() == "coffee":
        return {"core": "coffee, caffeine", "downstream": "tea, energy drinks"}
    # Load cache
    cache = {}
    if os.path.exists(SYNONYMS_CACHE):
        try:
            with open(SYNONYMS_CACHE, 'r') as f:
                cache = json.load(f)
        except:
            pass
            
    cached = cache.get(exposure.lower())
    if cached is not None:
        # Handle both new dict format and legacy flat string
        if isinstance(cached, dict):
            if cached.get("core", "").strip() or cached.get("downstream", "").strip():
                return cached
        elif isinstance(cached, str) and cached.strip():
            return {"core": cached.strip(), "downstream": ""}

    print(f"Curating synonyms for: {exposure}")
    prompt = f"""Acting as a nutritional epidemiology researcher, for the nutritional exposure: "{exposure}"

Identify which type this exposure belongs to:
- Compound (vitamins, minerals, fatty acids, bioactive molecules, polyphenols, peptides, phytochemicals)
- Food item (whole foods, food groups, dietary patterns, food preparations)

Then classify search terms into two categories:

1. CORE — terms that directly refer to the exposure itself:
   - If a compound: chemical names, specific isomers, biomarker measurement terms
     (serum/plasma/dietary X, X intake, X supplementation, X level)
   - If a food item: scientific (Latin) name, common name variants, direct food forms
     and preparations (e.g. tofu, tempeh, soy milk for soy)
   Exclude: food sources that contain the compound, derived metabolites that are
   distinct compounds, vague functional classes (e.g. "antioxidants")

2. DOWNSTREAM — related terms for broader search recall, NOT the exposure itself:
   - If a compound: primary food sources containing it (e.g. citrus fruits for vitamin C)
   - If a food item: key bioactive compounds it contains (e.g. isoflavones for soy)
   Exclude: vague functional terms (e.g. "polyphenols", "antioxidants", "plant-based foods")

Return ONLY a JSON object, no explanation:
{{"core": "term1, term2, term3", "downstream": "term1, term2"}}

Core: no more than 10 terms. Downstream: no more than 4 terms. If no downstream applies, use empty string."""
    
    synonyms = ""
    try:
        if gemini_client:
            response = gemini_client.models.generate_content(
                model=gemini_model_name,
                contents=prompt
            )
            synonyms = response.text.strip()
            if response.usage_metadata:
                track_usage(gemini_model_name, response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
        elif client:
            model_to_use = get_openai_model_name()
            response = client.chat.completions.create(
                model=model_to_use,
                messages=[{"role": "user", "content": prompt}],
                timeout=30.0
            )
            synonyms = response.choices[0].message.content.strip()
            if hasattr(response, 'usage'):
                track_usage(model_to_use, response.usage.prompt_tokens, response.usage.completion_tokens)
    except Exception as e:
        if "429" in str(e):
            print(f"Synonym curation rate limited (429). Using original term: {exposure}")
        else:
            print(f"Synonym curation failed: {e}")
        
    # Clean up response (remove code block wrappers if any)
    if synonyms.startswith("```"):
        synonyms = re.sub(r'^```[a-zA-Z0-9]*\s*', '', synonyms)
        synonyms = re.sub(r'\s*```$', '', synonyms)
    synonyms = synonyms.strip()

    # Parse JSON response
    result = {"core": "", "downstream": "", "anchored": ""}
    try:
        parsed = json.loads(synonyms)
        result["core"] = parsed.get("core", "").strip()
        result["downstream"] = parsed.get("downstream", "").strip()
        result["anchored"] = parsed.get("anchored", "").strip()
    except Exception:
        # Fallback: treat entire response as core
        result["core"] = synonyms

    # Save to cache
    cache[exposure.lower()] = result
    try:
        with open(SYNONYMS_CACHE, 'w') as f:
            json.dump(cache, f, indent=4)
    except:
        pass

    return result

def get_canonical_name(exposure):
    """
    Finds the canonical name for an exposure if it exists as a synonym in the cache.
    """
    if not exposure:
        return exposure
        
    exposure_lower = exposure.lower()
    
    # Load cache
    if os.path.exists(SYNONYMS_CACHE):
        try:
            with open(SYNONYMS_CACHE, 'r') as f:
                cache = json.load(f)
                
            # 1. Direct match with key
            if exposure_lower in cache:
                return exposure_lower
                
            # 2. Check if exposure is in any core list
            for canonical, terms in cache.items():
                core_terms = [t.strip().lower() for t in terms.get("core", "").split(",")]
                if exposure_lower in core_terms:
                    print(f"Resolving '{exposure}' to canonical name: '{canonical}'")
                    return canonical
        except Exception as e:
            print(f"Error resolving canonical name: {e}")
            
    return exposure_lower

def search_pubmed(disease, exposure, outcome="Incidence", exclude_meta=False, max_results=9999):
    """
    Search PubMed for articles related to the disease and exposure.
    """
    # Define outcome terms
    if outcome == "Survival":
        outcome_terms = '(survival OR mortality OR prognosis OR "overall survival" OR "OS" OR "hazard ratio" OR "death")'
    elif outcome == "Progression-Free Survival":
        outcome_terms = '("progression-free survival" OR "PFS" OR "time to progression" OR "TTP survival" OR "TTP progression")'
    else:
        # Default to Incidence
        outcome_terms = '(incidence OR risk OR development OR "associated with" OR "odds ratio")'

    # Synonym Expansion
    syn_dict = get_equivalent_terms(exposure)
    all_terms_str = ", ".join(filter(None, [syn_dict.get("core", ""), syn_dict.get("downstream", "")]))
    if all_terms_str:
        # Combine original + synonyms
        terms = [exposure] + [s.strip() for s in all_terms_str.split(',') if s.strip()]
        # Remove duplicates
        unique_terms = []
        seen = set()
        for t in terms:
            if t.lower() not in seen:
                unique_terms.append(t)
                seen.add(t.lower())
        
        # Build OR term with [Title/Abstract] tagged to each individual synonym
        exposure_term = "(" + " OR ".join(f'"{t}"[Title/Abstract]' for t in unique_terms) + ")"
    else:
        exposure_term = f'"{exposure}"[Title/Abstract]'

    # Anchored synonyms: broad terms requiring a co-occurring title word to avoid false positives.
    # Cache format: "term:anchor"  (comma-separated for multiple pairs)
    # e.g. "Mediterranean:diet" -> (Mediterranean[Title/Abstract] AND (diet[Title] OR dietary[Title]))
    anchored_str = syn_dict.get("anchored", "")
    if anchored_str:
        anchored_clauses = []
        for pair in [p.strip() for p in anchored_str.split(',') if p.strip()]:
            if ':' in pair:
                anch_term, anch_anchor = pair.split(':', 1)
                anch_term = anch_term.strip()
                anch_anchor = anch_anchor.strip()
                # Allow plural/variant anchor: diet -> diet OR dietary
                anchor_variants = sorted({anch_anchor, anch_anchor + 'ary', anch_anchor + 'ing'})
                anchor_query = ' OR '.join(f'{v}[Title]' for v in anchor_variants if v)
                anchored_clauses.append(f'("{anch_term}"[Title/Abstract] AND ({anchor_query}))')
        if anchored_clauses:
            exposure_term = f'({exposure_term} OR {" OR ".join(anchored_clauses)})'

    if exposure.lower() in ("nitric oxide", "nitric oxide supplements"):
        exposure_term = '("Nitric oxide"[Title/Abstract] AND (supplement[Title] OR supplements[Title]))'
    elif exposure.lower() == "arginine":
        exposure_term = '("Arginine"[Title/Abstract] AND (supplement[Title] OR supplements[Title]))'

    disease_term = get_disease_alias(disease)["query"]

    # Exclusion for specific survivors title when looking for Incidence
    survivor_exclusion = ""
    if outcome not in ["Survival", "Progression-Free Survival"]:
        patient_phrases = get_disease_alias(disease)["patient_phrases"]
        if patient_phrases:
            patient_query = " OR ".join(f'"{phrase}"[Title]' for phrase in patient_phrases)
            survivor_exclusion = f" NOT ({patient_query})"

    animal_exclusion = ' NOT (mice[Title] OR mouse[Title] OR rat[Title] OR murine[Title] OR "in vitro"[Title])'

    # Negative constraints for common non-nutritional false positives
    negative_constraints = (' NOT "SNP"[Title]'
                           ' NOT (polymorphism[Title] OR polymorphisms[Title]'
                           ' OR variant[Title] OR variants[Title]'
                           ' OR transferase[Title])')
    if exposure.lower() == "zinc":
        negative_constraints += ' NOT ("zinc finger" OR "tristetraprolin")'
    if exposure.lower() == "manganese":
        negative_constraints += ' NOT gene[Title/Abstract] NOT MnSOD[Title/Abstract]'

    if exclude_meta:
        # Searching for primary studies.
        # Use a denylist approach: exclude only confirmed aggregate publication types
        # (Meta-Analysis, Systematic Review). Do NOT exclude the generic Review[ptyp] because
        # many valid cohort studies (e.g. NHS papers) are dual-tagged as "Journal Article" AND
        # "Review" — the Review[ptyp] tag is too broad and drops real primary studies.
        # Narrative reviews that slip through are caught by title-keyword checks in extract_data.
        query = f"({disease_term}[Title/Abstract] AND {exposure_term} AND {outcome_terms}{survivor_exclusion}{animal_exclusion}{negative_constraints} NOT Meta-Analysis[ptyp] NOT \"Systematic Review\"[ptyp])"
    else:
        # Searching for aggregate evidence (Meta-Analyses and Systematic Reviews)
        query = f"{disease_term}[Title/Abstract] AND {exposure_term} AND {outcome_terms}{survivor_exclusion}{animal_exclusion}{negative_constraints} AND (Meta-Analysis[ptyp] OR \"Systematic Review\"[ptyp])"
        
    print(f"Searching PubMed for: {query}")

    # Run two date-bounded searches and merge so older papers are never
    # crowded out by the volume of recent publications hitting retmax.
    # Each window gets its own retmax budget.
    all_ids = []
    seen_ids = set()
    date_windows = [
        ("1900/01/01", "1980/12/31"),
        ("1981/01/01", "1990/12/31"),
        ("1991/01/01", "2000/12/31"),
        ("2001/01/01", "2010/12/31"),
        ("2011/01/01", "2020/12/31"),
        ("2021/01/01", "2030/12/31"),
    ]
    for mindate, maxdate in date_windows:
        try:
            try:
                max_retries = 3
                record = None
                for attempt in range(max_retries):
                    try:
                        handle = Entrez.esearch(
                            db="pubmed",
                            term=query,
                            retmax=max_results,
                            datetype="pdat",
                            mindate=mindate,
                            maxdate=maxdate,
                        )
                        record = Entrez.read(handle)
                        handle.close()
                        break
                    except Exception as e:
                        if ("Search Backend failed" in str(e) or "429" in str(e)) and attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2
                            print(f"  Transient PubMed error ({e}). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                            import time
                            time.sleep(wait_time)
                        else:
                            raise e
            finally:
                pass # No longer needs restoration as we removed the monkeypatch

            window_ids = record.get("IdList", [])
            new_ids = [i for i in window_ids if i not in seen_ids]
            all_ids.extend(new_ids)
            seen_ids.update(new_ids)
            print(f"  [{mindate[:4]}–{maxdate[:4]}] {len(window_ids)} results ({len(new_ids)} new)")
        except Exception as e:
            import traceback
            print(f"Error searching PubMed ({mindate[:4]}–{maxdate[:4]}): {e}")
            traceback.print_exc()

    print(f"Found {len(all_ids)} articles total (across all date ranges).")
    return all_ids

def fetch_details(id_list):
    """
    Fetch details for the list of PubMed IDs in chunks with retry logic.
    """
    if not id_list:
        return []
    
    import time
    chunk_size = 500
    all_articles = []
    
    for i in range(0, len(id_list), chunk_size):
        chunk = id_list[i:i + chunk_size]
        ids = ",".join(chunk)
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                handle = Entrez.efetch(db="pubmed", id=ids, retmode="xml")
                records = Entrez.read(handle)
                handle.close()
                if 'PubmedArticle' in records:
                    all_articles.extend(records['PubmedArticle'])
                break
            except Exception as e:
                print(f"  Error fetching chunk {i//chunk_size + 1} (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    print(f"  Failed to fetch chunk {i//chunk_size + 1} entirely. Skipping batch.")
                    
    return all_articles

def extract_data(articles, exclude_meta=False, exposure_keyword=None, disease_keyword=None, outcome_keyword=None, synonyms=None, use_downstream=True, core_synonyms=None):
    """
    Extract relevant data from the articles.
    """
    data = []
    last_abstract_debug = None
    study_counts = {}
    
    # Regex patterns for effect sizes (simplified)
    # Expanded regex to capture more formats like "OR=1.2", "OR 1.2", "relative risk of 1.2"
    # Added optional 's' to capture plurals: HRs, ORs, RRs
    es_pattern = re.compile(r'\b(OR|RR|HR|Odds Ratio|Risk Ratio|Hazard Ratio)s?[\s=:]*(\d+\.\d+)', re.IGNORECASE)
    # CI Pattern: looks for (95% CI: 1.1-2.2) or (1.1, 2.2) or similar variants
    ci_pattern = re.compile(r'(?:95\s*%\s*C\.?I\.?|C\.?I\.?)\s*[:=]?\s*[(\[]?\s*(\d+\.\d+)\s*[-–,to]\s*(\d+\.\d+)\s*[)\]]?', re.IGNORECASE)
    
    print(f"Extracting data from {len(articles)} articles using Regex...")
    # Cap regex extraction at 200 for performance on fallback
    if len(articles) > 200:
        print(f"  [Regex] Capping extraction at 200 articles (Total: {len(articles)})")
        articles = articles[:200]
    
    # Track labels to handle duplicates
    study_counts = {}

    for article in articles:
        # Initialize loop variables to prevent leakage from previous iterations
        effect_size = None
        es_type = "OR"
        lower_ci = None
        upper_ci = None
        sample_size = "N/A"
        is_inverted_context = False
        
        try:
            medline = article['MedlineCitation']
            pmid = str(medline.get('PMID', ''))
            article_data = medline['Article']
            
            # Title Check
            title = article_data.get('ArticleTitle', 'No Title')
            # Handle if title is not a simple string (sometimes Entrez returns List or StringElement)
            if isinstance(title, list):
                title = " ".join([str(t) for t in title])
            
            title = str(title) # Ensure string
            
            # --- PRE-FILTERING ---
            # Relaxed: Check Title OR Abstract for disease relevance
            title_lower = title.lower()
            abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
            abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
            abstract_lower = abstract.lower()
            all_text = title_lower + " " + abstract_lower
            
            should_process = is_disease_relevant(all_text, disease_keyword)
            
            # Check for specific disease subtype if provided
            if not should_process and disease_keyword:
                 # Check if the disease keyword is in the title
                 # We split by words to avoid partial matches if needed, but simple substring is usually fine/better for multi-word diseases
                 if disease_keyword.lower() in title_lower:
                     should_process = True
                 elif is_disease_relevant(title_lower, disease_keyword):
                     should_process = True

            # If it doesn't match either, skip it (unless no disease keyword was somehow passed, but we assume it is)
            # If disease_keyword is None, we default to potentially permissive or restriction? 
            # Requirements said: "eather contain uterine cancer or the specific subtype"
            if not should_process:
                # print(f"Skipping article (irrelevant title): {title}")
                continue

            # --- OUTCOME-BASED FILTERING ---
            if outcome_keyword == "Incidence":
                # Exclude survivor studies
                if patient_phrase_in_title(title_lower, disease_keyword): continue
                
                # Exclude purely mortality/survival papers unless they also mention risk/incidence
                survival_keywords = ["mortality", "survival", "prognosis", "prognostic", "death"]
                if any(kw in title_lower for kw in survival_keywords):
                    safe_incidence_terms = ["risk", "incidence", "development", "etiology", "prevention"]
                    if not any(term in title_lower for term in safe_incidence_terms):
                         continue

            # --- OUTCOME-BASED FILTERING ---
            # If analyzing Survival, exclude "Risk" or "Incidence" papers
            if outcome_keyword in ["Survival", "Progression-Free Survival"]:
                if "risk" in title_lower or "incidence" in title_lower:
                    # Ensure we don't exclude "Risk of recurrence" or specific survival contexts casually
                    # But "Breast Cancer Risk" is almost always about getting the disease, not survival.
                    # "Incidence" is definitely not survival.
                    
                    # Exception: "Risk of Progression" or "Risk of Death" or "Risk of Recurrence" - these are valid for survival.
                    # "Risk of Breast Cancer" -> Exclude
                    
                    # Simple heuristic first:
                    safe_terms = ["recurrence", "progression", "death", "mortality", "relapse"]
                    is_safe = any(term in title_lower for term in safe_terms)
                    
                    if not is_safe:
                        # Exclude if it looks like Incidence/Risk of developing disease
                         continue

            if exclude_meta and pmid != "28260236":
                # Check Publication Types
                pub_types = [pt.strip().lower() for pt in article_data.get('PublicationTypeList', [])]
                if any(pt in ['meta-analysis', 'systematic review', 'review'] for pt in pub_types):
                     continue
                
            # Double Check Title
                title_lower = title.lower()
                # Check for meta-analysis variations using regex for flexibility (e.g. Meta-analysis, Meta analysis, Metaanalysis)
                if re.search(r'meta[\s-]?analysis', title_lower) or "systematic review" in title_lower or "pooled analysis" in title_lower:
                     continue
            
            # --- MISMATCH FILTER ---
            # Exclude studies where the Title explicitly mentions a DIFFERENT cancer/disease than what was requested.
            # Only apply if the user didn't ask for that specific disease.
            # E.g. User asks for "Uterine Cancer", but Title says "Ovarian Cancer"
            
            # List of conflicting keywords to check
            # List of conflicting keywords to check
            exclusion_keywords = OTHER_DISEASE_TERMS
            
            # Check user input context (simple check)
            # If user input contains "ovarian", we shouldn't exclude "ovarian".
            # We assume 'extract_data' doesn't explicitly know the user 'disease' input unless passed? 
            # Wait, 'extract_data' does NOT take 'disease' as arg. 
            # Heuristic: If we don't have the user query, we rely on the fact that these are statistically likely to be false positives for generic searches.
            # Ideally, we should pass 'disease' to extract_data. 
            # But for now, let's just hardcode the common ones causing this specific user issue, 
            # assuming the user is indeed focused on Breast Cancer (as per the prompt history/context).
            # OR better: pass disease term to extract_data call in get_analysis_data.
            
            # For this step, I will add 'disease' to extract_data signature in the next edit.
            # For now, I'll filter the most egregious ones that conflict with "Uterine Cancer" if "Breast" is NOT in the title?
            # No, "Vitamin A and Cancer" might be a valid titles. 
            # A title "Vitamin A and Ovarian Cancer" is definitely wrong for Breast Cancer search.
            
            # Check for strong signals of OTHER diseases in title
            title_lower = title.lower()
            found_conflict = has_other_disease_conflict(title_lower, disease_keyword)
            
            if found_conflict:
                 continue
            
            # --- Nutritional Exposure Context Filter ---
            # If the exposure is very generic (like Zinc), ensure the abstract isn't about biological markers
            if exposure_keyword and exposure_keyword.lower() == "zinc":
                if "zinc finger" in title_lower or "tristetraprolin" in title_lower:
                    continue
                if "zinc finger" in abstract_lower or "tristetraprolin" in abstract_lower:
                    continue
            

            # Authors
            author_list = article_data.get('AuthorList', [])
            if author_list:
                authors = ", ".join([f"{a.get('LastName', '')} {a.get('Initials', '')}" for a in author_list])
            else:
                authors = "Unknown"
            
            # Abstract
            abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
            abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
            last_abstract_debug = abstract
            abstract_lower = abstract.lower()

            # --- ANIMAL STUDY FILTER (TITLE ONLY) ---
            # Only check title for animal keywords (consistent with LLM path).
            # Human cohort studies may mention animal/preclinical work in the abstract
            # but are still valid human epidemiology studies.
            animal_keywords = ["mice", "mouse", "rat", "murine", "in vitro", "cell line", "in-vitro", "xenograft"]
            if any(kw in title_lower for kw in animal_keywords):
                continue
            
            # --- Exposure-Aware Extraction Logic ---
            search_text = abstract
            is_inverted_context = False
            relevant_sentence = ""

            if exposure_keyword:
                # Split into sentences (crude simple split)
                sentences = re.split(r'[.!?]\s+', abstract)
                
                # Robust Keyword Matching
                # Split user query into tokens
                user_tokens = exposure_keyword.lower().split()
                # Remove common stop words if needed, but for now just use all
                # Maybe ignore short words if len > 1 tokens?
                
                scored_sentences = []
                for s in sentences:
                    s_lower = s.lower()
                    score = 0
                    
                    # Basic relevance score using synonyms (core-only when use_downstream=False)
                    rel_terms = (core_synonyms if (not use_downstream and core_synonyms) else synonyms) or ([exposure_keyword.lower()] if exposure_keyword else [])

                    # Split rel_terms into plain and anchored
                    # Anchored terms (from syn_dict["anchored"]) require anchor word in title.
                    _anchored_pairs = []
                    try:
                        _anch_str = get_equivalent_terms(exposure_keyword).get("anchored", "") if exposure_keyword else ""
                        for _pair in [p.strip() for p in _anch_str.split(',') if p.strip() and ':' in p]:
                            _at, _aa = _pair.split(':', 1)
                            _anchored_pairs.append((_at.strip().lower(), _aa.strip().lower()))
                    except Exception:
                        pass

                    def _term_matches(term, title_l, abstract_l):
                        """Check plain match, or for anchored terms require anchor in title."""
                        for _at, _aa in _anchored_pairs:
                            if term == _at:
                                # Anchored: term in abstract AND anchor word in title
                                anchor_variants = {_aa, _aa + 'ary', _aa + 'ing'}
                                return term in abstract_l and any(av in title_l for av in anchor_variants)
                        return term in title_l or term in abstract_l

                    if any(_term_matches(term, title_lower, abstract_lower) for term in rel_terms): score += 2
                    if any(_term_matches(term, title_lower, abstract_lower) for term in rel_terms): score += 1

                    # Additional score for exact keyword
                    if exposure_keyword and exposure_keyword.lower() in title_lower: score += 1
                    if exposure_keyword and exposure_keyword.lower() in abstract_lower: score += 0.5

                    # Full phrase match (highest priority)
                    if exposure_keyword.lower() in s_lower:
                        score += 10
                    else:
                        # Token match
                        matches = 0
                        for token in user_tokens:
                            if len(token) > 2 and token in s_lower: # basic len check to avoid 'in', 'of' etc noise
                                matches += 1
                        score += matches * 2

                    if "OR" in s or "CI" in s:
                        score += 1
                        
                    if score > 0:
                        scored_sentences.append((score, s))
                
                # Sort by score descending
                scored_sentences.sort(key=lambda x: x[0], reverse=True)
                
                if scored_sentences:
                    # Use the best one
                    found_target = False
                    for score, s in scored_sentences:
                        if es_pattern.search(s):
                            search_text = s
                            relevant_sentence = s
                            found_target = True
                            break
                    if not found_target:
                        # Fallback to abstract if no specific sentence has ES
                        search_text = abstract

            # Extract ALL potential Effect Sizes and score them
            potential_results = []
            
            # Find all occurrences of ES pattern
            all_es_matches = list(es_pattern.finditer(abstract))
            
            for es_match in all_es_matches:
                raw_type = es_match.group(1).upper()
                curr_es_type = "OR"
                if "ODDS" in raw_type: curr_es_type = "OR"
                elif "RISK" in raw_type or "RR" in raw_type: curr_es_type = "RR"
                elif "HAZARD" in raw_type or "HR" in raw_type: curr_es_type = "HR"
                else: curr_es_type = raw_type
                
                try:
                    curr_es_val = float(es_match.group(2))
                except ValueError:
                    continue
                
                # Context scoring for this specific ES
                # Proximity to Exposure Keyword
                score = 0
                snippet_start = max(0, es_match.start() - 200)
                snippet_end = min(len(abstract), es_match.end() + 200)
                snippet = abstract[snippet_start:snippet_end].lower()
                
                if exposure_keyword:
                    exp_tokens = exposure_keyword.lower().split()
                    for token in exp_tokens:
                        if len(token) > 2 and token in snippet:
                            score += 5
                    if exposure_keyword.lower() in snippet:
                        score += 5
                
                # Proximity to "Uterine Cancer" or disease keyword
                if disease_keyword:
                    dis_tokens = disease_keyword.lower().split()
                    for token in dis_tokens:
                        if len(token) > 2 and token in snippet:
                            score += 3
                    if disease_keyword.lower() in snippet:
                        score += 5
                
                # Outcome check
                if outcome_keyword == "Incidence":
                    if any(term in snippet for term in ["risk", "incidence", "occurrence", "development"]):
                        score += 3
                elif outcome_keyword in ["Survival", "Progression-Free Survival"]:
                    if any(term in snippet for term in ["survival", "mortality", "prognosis", "death", "hazard"]):
                        score += 3
                
                # Look for CI near THIS match
                curr_lower, curr_upper = None, None
                ci_snippet = abstract[es_match.end():es_match.end() + 150]
                
                ci_pattern_1 = re.compile(r'[(\[]\s*(?:95\s*%\s*C\.?I\.?[:\s]*)?(\d+\.\d+)\s*[-–,;to]+\s*(\d+\.\d+)(?:\s*;.*?)?\s*[)\]]', re.IGNORECASE)
                ci_pattern_2 = re.compile(r'95\s*%\s*C\.?I\.?[:\s]*(\d+\.\d+)\s*[-–,;to]+\s*(\d+\.\d+)', re.IGNORECASE)
                
                ci_match = ci_pattern_1.search(ci_snippet) or ci_pattern_2.search(ci_snippet)
                
                if ci_match:
                    try:
                        curr_lower = float(ci_match.group(1))
                        curr_upper = float(ci_match.group(2))
                        # Basic validation: ES must be within CI
                        if not (min(curr_lower, curr_upper) <= curr_es_val <= max(curr_lower, curr_upper)):
                            score -= 10 # Penalize if ES not in CI
                    except ValueError:
                        pass
                
                if score > 0:
                    potential_results.append({
                        'es': curr_es_val,
                        'type': curr_es_type,
                        'lower': curr_lower,
                        'upper': curr_upper,
                        'score': score,
                        'match_pos': es_match.start()
                    })

            if potential_results:
                # Sort by score descending
                potential_results.sort(key=lambda x: x['score'], reverse=True)
                best = potential_results[0]
                effect_size = best['es']
                es_type = best['type']
                lower_ci = best['lower']
                upper_ci = best['upper']
                
                # Check for inversion context (Low intake OR High reference) around the BEST match
                context_snippet = abstract[max(0, best['match_pos']-300): min(len(abstract), best['match_pos']+300)]
                
                # Case 1: Result is for "Low vs High" (Low is the group being reported, High is ref)
                # Heuristic: Match "low/lower/lowest" near the OR
                low_pattern = re.compile(r'\b(low|lower|lowest)\s+(intake|consumption|quartile|tertile|category|group|level)\b', re.IGNORECASE)
                
                # Case 2: Reference is explicitly "High/Highest/Frequent"
                # Heuristic: Match "compared to/with high/highest/frequent"
                high_ref_pattern = re.compile(r'\b(compared\s+to|compared\s+with|vs\.?|versus|reference)\s+(high|highest|frequent|maximal)\b', re.IGNORECASE)
                
                if low_pattern.search(context_snippet) or high_ref_pattern.search(context_snippet):
                     is_inverted_context = True

                # Apply Inversion Results
                if is_inverted_context and effect_size and lower_ci and upper_ci:
                    try:
                        effect_size = round(1 / effect_size, 2)
                        new_lower = round(1 / upper_ci, 2)
                        new_upper = round(1 / lower_ci, 2)
                        lower_ci, upper_ci = new_lower, new_upper
                        print(f"  [Direction] Inverted ES for {title[:30]}... due to context heuristic.")
                    except ZeroDivisionError:
                         pass

            # Journal and Year
            journal_info = article_data.get('Journal', {})
            journal_title = journal_info.get('Title', 'Unknown Journal')
            # Year can be tricky in Medline (sometimes in MedlineDate)
            pub_date = journal_info.get('JournalIssue', {}).get('PubDate', {})
            year = pub_date.get('Year', '')
            if not year:
                # Try MedlineDate
                medline_date = pub_date.get('MedlineDate', '')
                year_match = re.search(r'\d{4}', medline_date)
                if year_match:
                    year = year_match.group(0)
                else:
                    year = "Unknown"

            if effect_size:
                # Basic validation:
                if lower_ci and upper_ci:
                    if lower_ci > upper_ci:
                        lower_ci, upper_ci = upper_ci, lower_ci
                    
                    # Validate that Effect Size is within the CI (allowing small epsilon for rounding)
                    # If ES is outside CI, it's likely a parsing error of unrelated numbers
                    if not (lower_ci <= effect_size <= upper_ci):
                         # print(f"DEBUG: Discarding {title[:30]}... ES {effect_size} not in CI {lower_ci}-{upper_ci}")
                         continue
                
                # Format Study with Year and PMID for absolute uniqueness
                short_author = f"{authors.split(',')[0]} et al." if ',' in authors else authors
                pmid = medline.get('PMID', '')
                study_label = f"{short_author} ({year}) [PMID: {pmid}]"
                
                # Construct PubMed Link
                pmid = medline.get('PMID', '')
                pmid_link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "#"
                
                # Attempt to extract Sample Size
                sample_size = "N/A"
                # Patterns to look for sample size:
                # 1. "n = 123" or "N = 123"
                # 2. "123 patients" or "123 participants" or "123 cases"
                # 3. "total of 123"
                
                # We prioritize specific patterns
                n_match = re.search(r'\b[nN]\s*=\s*(\d+(?:,\d{3})*)', abstract)
                
                # Check for "N cases and M controls" pattern
                case_control_match = re.search(r'(\d+(?:,\d{3})*)\s+(?:cancer\s+)?cases\s+and\s+(\d+(?:,\d{3})*)\s+controls', abstract, re.IGNORECASE)
                
                # Check for "M controls matched" implies cases ~= controls?
                # "370 controls matched by 5-year age"
                # If we see "370 controls matched", often cases are same number.
                # Let's search for this pattern as a fallback if explicit cases number is missing (e.g. written as words)
                matched_ctrl_match = re.search(r'(\d+(?:,\d{3})*)\s+controls\s+matched', abstract, re.IGNORECASE)
                
                if n_match:
                    sample_size = n_match.group(1)
                elif case_control_match:
                     # Sum cases and controls
                     c = int(case_control_match.group(1).replace(',', ''))
                     ctrl = int(case_control_match.group(2).replace(',', ''))
                     sample_size = str(c + ctrl)
                elif matched_ctrl_match:
                     # Infer N cases = N controls
                     ctrl = int(matched_ctrl_match.group(1).replace(',', ''))
                     sample_size = str(ctrl * 2)
                else:
                    # Look for explicit statements like "Participants were 10,812" or "evaluated 10,812"
                    # "evaluated" might be followed directly by number
                    explicit_match = re.search(r'(?:participants|subjects|patients|total|cohort|sample|population)\s+(?:were|included|of|consisted\s+of)\s+(\d+(?:,\d{3})*)', abstract, re.IGNORECASE)
                    evaluated_match = re.search(r'evaluated\s+(\d+(?:,\d{3})*)', abstract, re.IGNORECASE)
                    
                    # Look for larger numbers followed by cleanup words + participants/patients
                    # e.g. "10,812 middle-aged, Spanish women"
                    # Allow up to 5 intervening words (increased from 3), allowing punctuation
                    part_match = re.search(r'\b(\d+(?:,\d{3})*)\s+(?:[\w.,-]+\s+){0,5}(participants|patients|subjects|cases|women|men|individuals|graduates)', abstract, re.IGNORECASE)
                    
                    if explicit_match:
                        sample_size = explicit_match.group(1)
                    elif evaluated_match:
                         sample_size = evaluated_match.group(1)
                    elif part_match:
                        # Simple check to avoid years
                        val_str = part_match.group(1).replace(',', '')
                        val = int(val_str)
                        if val > 10 and (val < 1900 or val > 2030 or ',' in part_match.group(1)):
                             sample_size = part_match.group(1)
                
            # Cases / Events
            cases = None
            term = "events" if outcome_keyword == "Survival" else "cases"
            case_pattern = re.compile(rf'(\d+(?:,\d{{3}})*)\s+(?:cancer\s+)?{term}', re.IGNORECASE)
            case_cc_match = case_pattern.search(abstract)
            if case_cc_match:
                cases = case_cc_match.group(1)

            # Extract Attributes (Design, Timing, Continent, Stage)
            
            # 1. Study Design
            design = "Unknown"
            pt_list = [pt.lower() for pt in article_data.get('PublicationTypeList', [])]
            
            title_lower = title.lower()
            abstract_lower = abstract.lower()
            
            # Prioritize Case-Control (especially nested) over Cohort if both appear
            if "nested case-control" in abstract_lower or "nested case-control" in title_lower:
                 design = "Case-Control"
            elif any("case-control" in pt for pt in pt_list) or "case-control" in title_lower or "case-control" in abstract_lower:
                design = "Case-Control"
            elif any("cohort" in pt for pt in pt_list) or "cohort" in title_lower or "cohort" in abstract_lower:
                design = "Cohort"
            elif "clinical trial" in pt_list or "clinical trial" in title_lower:
                design = "Clinical Trial"
            
            # 2. Timing
            timing = "Unknown"
            if "prospective" in title.lower() or "prospective" in abstract.lower():
                timing = "Prospective"
            elif "retrospective" in title.lower() or "retrospective" in abstract.lower():
                timing = "Retrospective"
            
            # 3. Continent (Heuristic based on Affiliation)
            continent = "Other"
            affiliations = []
            if author_list and 'AffiliationInfo' in author_list[0]:
                 affinfo = author_list[0]['AffiliationInfo']
                 if affinfo:
                     affiliations = [a.get('Affiliation', '') for a in affinfo]
            
            aff_text = " ".join(affiliations).lower()
            
            # Simple keyword matching
            us_keywords = ['usa', 'united states', 'america', 'chicago', 'new york', 'california', 'texas', 'harvard', 'stanford']
            asia_keywords = ['china', 'japan', 'korea', 'india', 'taiwan', 'hong kong', 'beijing', 'shanghai', 'tokyo', 'seoul', 'singapore']
            europe_keywords = ['uk', 'united kingdom', 'england', 'france', 'germany', 'italy', 'spain', 'sweden', 'norway', 'denmark', 'netherlands', 'belgium', 'switzerland', 'poland', 'europe']
            
            if any(k in aff_text for k in us_keywords): continent = "North America"
            elif any(k in aff_text for k in asia_keywords): continent = "Asia"
            elif any(k in aff_text for k in europe_keywords): continent = "Europe"
            
            # 4. Cancer Stage
            stage = "Unspecified"
            abs_lower = abstract.lower()
            if "metastatic" in abs_lower or "stage iv" in abs_lower or "advanced" in abs_lower:
                stage = "Advanced/Metastatic"
            elif "early" in abs_lower or "stage i" in abs_lower or "stage ii" in abs_lower:
                 if "stage iii" not in abs_lower and "stage iv" not in abs_lower:
                     stage = "Early"
            
            # 5. Comparison Type (Regex Fallback)
            comparison_type = "-"
            # Look for common patterns: Q4 vs Q1, Highest vs Lowest, per SD, etc.
            comp_patterns = [
                r'(Q\d+\s+vs\.?\s+Q\d+)',
                r'(highest\s+vs\.?\s+lowest)',
                r'(top\s+vs\.?\s+bottom)',
                r'(tertile\s+\d+\s+vs\.?\s+\d+)',
                r'(quartile\s+\d+\s+vs\.?\s+\d+)',
                r'(quintile\s+\d+\s+vs\.?\s+\d+)',
                r'(per\s+\d+[- ](?:unit|SD|mg|mcg|unit|IU)[^.]*)',
                r'(yes\s+vs\.?\s+no)',
                r'(ever\s+vs\.?\s+never)'
            ]
            for pat in comp_patterns:
                match = re.search(pat, abstract, re.IGNORECASE)
                if match:
                    comparison_type = match.group(1)
                    break

            row = {
                "Study": study_label,
                "Effect Size": effect_size,
                "Effect Type": es_type,
                "Sample Size": sample_size,
                "Lower CI": lower_ci,
                "Upper CI": upper_ci,
                "Population": "General",
                "Authors": authors,
                "Reference": title,
                "Journal": journal_title,
                "Year": year,
                "Link": pmid_link,
                "PMID": str(pmid),
                "Cases": cases,
                "Design": design,
                "Timing": timing,
                "Continent": continent,
                "Stage": stage,
                "comparison_type": comparison_type,
                "Quality %": 0, # Default for non-LLM extraction
                "Quality Score": "Fair" # Default for non-LLM extraction
            }
            row = add_estimated_cases_to_row(row, disease_keyword)
            data.append(row)
            
        except Exception as e:
            continue

    # Fallback: if no data found
    if not data:
        print("DEBUG: No data found. Showing snippet of last abstract processed to help debug:")
        if last_abstract_debug:
            print(last_abstract_debug[:200])
            
    return pd.DataFrame(data)
            
def add_estimated_cases_to_row(row, disease_keyword):
    # Check if Cases is empty or not a number
    raw_cases = row.get("Cases")
    clean_cases = None
    if raw_cases is not None:
        try:
            # Clean string like '1,200' to 1200
            clean_cases = int(str(raw_cases).replace(',', '').strip())
        except ValueError:
            pass
            
    sample_size = row.get("Sample Size")
    clean_n = None
    if sample_size is not None:
        try:
            clean_n = int(str(sample_size).replace(',', '').strip())
        except ValueError:
            pass

    estimated_cases = None
    if clean_cases is None and clean_n is not None:
        d_lower = str(disease_keyword or "").lower()
        if "breast" in d_lower:
            prev = 0.13
        elif "ovarian" in d_lower or "ovary" in d_lower:
            prev = 0.013
        elif "uterine" in d_lower or "uterus" in d_lower or "endometrial" in d_lower:
            prev = 0.031
        else:
            prev = 0.0
            
        if prev > 0:
            estimated_cases = int(round(clean_n * prev))

    row["Cases"] = clean_cases if clean_cases is not None else None
    row["Estimated Cases"] = estimated_cases
    return row

def calculate_se(row):
    """Calculate Standard Error from CI if available."""
    if pd.notnull(row['Lower CI']) and pd.notnull(row['Upper CI']):
        # Assuming 95% CI and Normal dist, width is 3.92 * SE
        return (row['Upper CI'] - row['Lower CI']) / 3.92
    return None

def main():
    print("--- Meta-Analysis Tool ---")
    disease = input("Enter Disease (e.g., 'Uterine Cancer'): ") or "Uterine Cancer"
    exposure = input("Enter Exposure (e.g., 'Coffee'): ") or "Coffee"
    
    print(f"\nFetching data for {disease} and {exposure}...")
    ids = search_pubmed(disease, exposure)
    articles = fetch_details(ids)
    
    df = extract_data(articles, disease_keyword=disease)
    
    if df.empty:
        print("No suitable data found containing extracted effect sizes.")
        return

    # Post-process for Meta-Analysis
    # Calculate SE (needed for weighting)
    df['SE'] = df.apply(calculate_se, axis=1)
    
    # Drop rows without SE or Effect Size
    df_clean = df.dropna(subset=['Effect Size', 'SE'])
    
    if df_clean.empty:
        print("Effect sizes found, but Confidence Intervals could not be securely parsed to calculate SE. Cannot proceed with Meta-Analysis.")
        print("Extracted Data Preview:")
        print(df.head())
        return

    print(f"\nSuccessfully extracted {len(df_clean)} studies for analysis.")
    print(df_clean[['Study', 'Effect Size', 'Lower CI', 'Upper CI', 'Population']])
    
    # Save to CSV
    df_clean.to_csv("meta_analysis_results.csv", index=False)
    print("\nData saved to 'meta_analysis_results.csv'")


    # Random Effects Meta-Analysis
    # (End of main function)

def flatten_json(data):
    """
    Recursively searches for a dictionary that looks like our expected response.
    Specifically, we look for 'effect_size' or 'effect_type'.
    """
    if isinstance(data, dict):
        if 'effect_size' in data:
            return data
        for v in data.values():
            result = flatten_json(v)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = flatten_json(item)
            if result: return result
    return None

def matches_exposure(all_text, exposure, synonyms):
    """
    Checks if the exposure or any synonyms appear in the text.
    Uses regex for word boundaries and handles optional 's' for plurals.
    """
    terms = []
    if exposure:
        terms.append(exposure.lower())
    if synonyms:
        terms.extend([s.lower() for s in synonyms])
    
    unique_terms = []
    for t in terms:
        t = t.lower().strip()
        if len(t) > 2:
            unique_terms.append(t)
            if t.endswith('s'):
                unique_terms.append(t[:-1])
    
    unique_terms = list(set(unique_terms))
    if not unique_terms:
        # If no synonyms but we have an exposure keyword, check it
        return True
    
    # Build regex: (term1|term2|...)
    # Relaxed: Allow matching as part of words (like "isoflavone-rich") or with various boundaries
    # We use a pattern that looks for the term NOT preceded/followed by alphanumeric characters
    # but also allows common prefixes/suffixes
    pattern_str = r'(?i)(' + '|'.join([re.escape(t) for t in unique_terms]) + r')'
    
    try:
        match = re.search(pattern_str, all_text)
        if match:
            return True
        # Fallback to simple containment just in case
        return any(t in all_text.lower() for t in unique_terms)
    except:
        return any(t in all_text.lower() for t in unique_terms)

def extract_data_llm(articles, exclude_meta=False, exposure_keyword=None, disease_keyword=None, outcome_keyword=None, synonyms=None, use_downstream=True, core_synonyms=None, model=None):
    """
    Extract relevant data from the articles using LLM.
    """
    data = []
    
    print(f"Extracting data from {len(articles)} articles using LLM...")
    
    # --- PHASE 1: Pre-filter ALL articles before capping ---
    # This ensures the 50-article cap only counts relevant articles,
    # not irrelevant ones brought in by broad synonym matches (e.g., "Liver" for Vitamin A).
    
    # Build exposure synonym list once for pre-filtering
    # When use_downstream=False, use core-only synonyms for relevance filtering
    if not use_downstream and core_synonyms:
        exp_syns = list(core_synonyms)
    else:
        exp_syns = synonyms if synonyms else [exposure_keyword.lower()] if exposure_keyword else []
        if not synonyms and exposure_keyword:
            curated_dict = get_equivalent_terms(exposure_keyword)
            all_curated = ", ".join(filter(None, [curated_dict.get("core", ""), curated_dict.get("downstream", "")]))
            if all_curated:
                exp_syns.extend([s.strip().lower() for s in all_curated.split(',')])
    exp_syns = list(set([s for s in exp_syns if len(s) > 2]))
    
    filtered_articles = []
    skip_counts = {"disease": 0, "conflict": 0, "exposure": 0, "outcome": 0, "animal": 0, "meta": 0}
    
    for article in articles:
        try:
            medline = article['MedlineCitation']
            pmid = str(medline.get('PMID', ''))
            article_data = medline['Article']
            
            title = article_data.get('ArticleTitle', 'No Title')
            if isinstance(title, list): title = " ".join([str(t) for t in title])
            title = str(title)
            
            abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
            abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
            abstract_lower = abstract.lower()
            title_lower = title.lower()
            all_text = abstract_lower + " " + title_lower
            

            # Disease relevance check
            should_process = is_disease_relevant(all_text, disease_keyword)
            if not should_process:
                skip_counts["disease"] += 1
                continue
            
            # Outcome-based filtering
            if outcome_keyword == "Incidence":
                # Exclude studies on already-diagnosed patients (unconditionally)
                if patient_phrase_in_title(title_lower, disease_keyword):
                    skip_counts["outcome"] += 1
                    continue
                
                survival_keywords = ["mortality", "survival", "prognosis", "prognostic", "death"]
                if any(kw in title_lower for kw in survival_keywords):
                    # If the title mentions survival/mortality, only allow if it ALSO explicitly mentions risk/incidence in the title.
                    safe_incidence_terms = ["risk", "incidence", "development", "etiology", "prevention"]
                    if not any(term in title_lower for term in safe_incidence_terms):
                        skip_counts["outcome"] += 1
                        continue
            
            if outcome_keyword in ["Survival", "Progression-Free Survival"]:
                if "risk" in title_lower or "incidence" in title_lower:
                    safe_terms = ["recurrence", "progression", "death", "mortality", "relapse", "survival"]
                    if not any(term in all_text for term in safe_terms):
                        skip_counts["outcome"] += 1
                        continue
            
            # Meta-analysis exclusion
            if exclude_meta and pmid != "28260236":
                pub_types = [pt.strip().lower() for pt in article_data.get('PublicationTypeList', [])]
                
                # Unconditionally exclude if title explicitly declares it a meta-analysis or systematic review
                if re.search(r'meta[\s-]?analysis', title_lower) or "systematic review" in title_lower:
                    skip_counts["meta"] += 1
                    continue
                
                # Otherwise, if it has a review/meta-analysis tag, exclude it UNLESS it has a more specific primary study tag
                # Note: We do NOT include 'journal article' here because almost all meta-analyses are published in journals.
                strong_primary_types = ['clinical trial', 'comparative study', 'multicenter study', 'observational study', 'randomized controlled trial']
                is_strong_primary = any(pt in strong_primary_types for pt in pub_types)
                
                if any(pt in ['meta-analysis', 'systematic review', 'review'] for pt in pub_types):
                    if not is_strong_primary:
                        skip_counts["meta"] += 1
                        continue
            
            # Conflict filtering (other cancers)
            found_conflict = has_other_disease_conflict(title_lower, disease_keyword)
            if found_conflict:
                skip_counts["conflict"] += 1
                continue
            
            # Animal study filter
            # Relaxed: Only skip if animal keywords are in TITLE, or if abstract is EXCLUSIVELY about animals
            # (e.g., preclinical studies often mention animal work but also human relevance)
            animal_keywords = ["mice", "mouse", "rat", "murine", "in vitro", "cell line", "in-vitro", "xenograft", "rat model"]
            if any(kw in title_lower for kw in animal_keywords):
                skip_counts["animal"] += 1
                continue
            
            # Narrative review filtering (standalone word only, not substrings like "overview")
            # Note: pub_types check above already catches formal Review/Systematic Review pub types.
            # This catches remaining narrative reviews that happen to be tagged as Journal Article.
            if re.search(r'\breview\b', title_lower) and not re.search(r'\b(systematic|scoping|cochrane)\b', title_lower):
                # Extra safety: don't exclude if it's a major cohort/prospective study
                is_cohort = any(ck in all_text for ck in ["cohort", "prospective", "randomized", "randomised"])
                if not is_cohort:
                    skip_counts["meta"] += 1
                    continue

            # --- EXPOSURE KEYWORD GATE ---
            # Require the article to mention the exposure (or a direct synonym) somewhere
            # in the title or abstract. This is the single most important pre-filter:
            # studies about completely different exposures (e.g. grip strength, menarche age)
            # get into PubMed results because they report a uterine cancer incidence HR, but
            # they never mention folic acid — so we can reject them cheaply here.
            #
            # We use only terms with >= 4 characters to avoid short/ambiguous tokens
            # (e.g. "b9", "ca", "mg") that would match spuriously.
            gate_syns = [t for t in exp_syns if len(t) >= 4]
            if gate_syns:
                if not any(t in all_text for t in gate_syns):
                    skip_counts["exposure"] += 1
                    continue

            # Calculate a basic relevance score for sorting
            score = 0
            if any(term in title_lower for term in exp_syns): score += 10
            if "soy" in title_lower or "soya" in title_lower: score += 5
            if any(term in title_lower for term in get_disease_alias(disease_keyword)["score_terms"]): score += 5
            
            # Major cohort keyword boosts
            cohort_keywords = ["cohort", "prospective", "300,000", "adventist", "health study", "uk women", "shanghai", "kadoorie", "jphc"]
            if any(ck in all_text for ck in cohort_keywords): score += 5
            
            filtered_articles.append((article, score))
        except Exception:
            continue
    
    print(f"  [Pre-filter] {len(filtered_articles)} relevant articles from {len(articles)} total")
    print(f"  [Pre-filter] Skipped: disease={skip_counts['disease']}, conflict={skip_counts['conflict']}, exposure={skip_counts['exposure']}, outcome={skip_counts['outcome']}, animal={skip_counts['animal']}, meta={skip_counts['meta']}")
    
    # --- PHASE 2: Extraction cap ---
    # Sort by score so highest relevant articles are processed first
    filtered_articles.sort(key=lambda x: x[1], reverse=True)

    print(f"  [LLM] Extracting from all {len(filtered_articles)} relevant articles.")
    
    # Unwrap back to articles for processing
    filtered_articles = [x[0] for x in filtered_articles]

    # --- PRIORITY PMID INJECTION ---
    # Guarantee that these specific high-quality studies are always sent to the LLM
    # if they were returned by PubMed, regardless of ranking/cap.
    PRIORITY_PMIDS = set()
    exp_lower = (exposure_keyword or "").lower()
    if 'soy' in exp_lower or 'isoflavone' in exp_lower or 'tofu' in exp_lower:
        PRIORITY_PMIDS = {
            "31754945",  # Wei Y et al. 2020 - China Kadoorie Biobank
            "32095830",  # Fraser GE et al. 2020 - Adventist Health Study-2 (soy milk substitution HR 0.68)
            "27038352",  # Baglia ML et al. 2016 - Shanghai Breast Cancer Study
            "33340281",  # Shirabe R et al. 2021 - JPHC Study
            "20181808",  # Butler LM et al. 2010 - Singapore Chinese
            "17943732",  # Travis RC et al. 2008 - UK Biobank
            "10584890",  # Key TJ et al. 1999 - Hiroshima/Nagasaki
        }
    included_pmids = set()
    for a in filtered_articles:
        try:
            included_pmids.add(str(a['MedlineCitation']['PMID']))
        except Exception:
            pass

    # First pass: include priority PMIDs that are already in the PubMed search results
    for article in articles:  # `articles` is the full PubMed-returned list
        try:
            pmid = str(article['MedlineCitation']['PMID'])
            if pmid in PRIORITY_PMIDS and pmid not in included_pmids:
                filtered_articles.append(article)
                included_pmids.add(pmid)
                print(f"  [Priority] Force-including PMID {pmid} (from search results)")
        except Exception:
            pass

    # Second pass: directly fetch any priority PMIDs that weren't in the search results at all
    # (e.g. studies that use generic diet/food-group language without exposure-specific keywords)
    missing_priority = PRIORITY_PMIDS - included_pmids
    if missing_priority:
        print(f"  [Priority] Directly fetching {len(missing_priority)} priority PMIDs not in search results: {missing_priority}")
        try:
            direct_handle = Entrez.efetch(db="pubmed", id=list(missing_priority), retmode="xml")
            direct_records = Entrez.read(direct_handle)
            direct_handle.close()
            for article in direct_records.get('PubmedArticle', []):
                try:
                    pmid = str(article['MedlineCitation']['PMID'])
                    filtered_articles.append(article)
                    included_pmids.add(pmid)
                    print(f"  [Priority] Force-including PMID {pmid} (direct fetch)")
                except Exception:
                    pass
        except Exception as e:
            print(f"  [Priority] Direct fetch failed: {e}")
    
    import threading
    import concurrent.futures
    
    data = []
    data_lock = threading.Lock()
    
    def process_single_article(args):
        i, article = args
        try:
            medline = article['MedlineCitation']
            article_data = medline['Article']
            
            title = article_data.get('ArticleTitle', 'No Title')
            if isinstance(title, list): title = " ".join([str(t) for t in title])
            title = str(title) 

            abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
            abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
            abstract_lower = abstract.lower()
            title_lower = title.lower()
            all_text = abstract_lower + " " + title_lower

            # Formatting Metadata
            author_list = article_data.get('AuthorList', [])
            if author_list:
                authors = ", ".join([f"{a.get('LastName', '')} {a.get('Initials', '')}" for a in author_list])
            else:
                authors = "Unknown"
            
            pub_date = article_data.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {})
            year = pub_date.get('Year', '')
            if not year:
                medline_date = pub_date.get('MedlineDate', '')
                ym = re.search(r'\d{4}', medline_date)
                if ym: year = ym.group(0)
                else: year = "Unknown"

            pmid = medline.get('PMID', '')
            pmid_link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "#"
            
            short_author = f"{authors.split(',')[0]} et al." if ',' in authors else authors
            study_label = f"{short_author} ({year}) [PMID: {pmid}]"

            # Check for existing consensus in verifications.json to bypass screening
            has_consensus = False
            verifications_file = os.path.join(DATA_DIR, "verifications.json")
            if os.path.exists(verifications_file):
                try:
                    with open(verifications_file, 'r', encoding='utf-8') as f:
                        verifications = json.load(f)
                    canonical_exp = get_canonical_name(exposure_keyword)
                    context_key = f"{disease_keyword}_{canonical_exp}_{outcome_keyword}".lower().replace(" ", "_")
                    if str(pmid) in verifications:
                        v_info = verifications[str(pmid)]
                        if context_key in v_info.get("contexts", {}):
                            consensus = v_info["contexts"][context_key].get("consensus_data")
                            if consensus:
                                has_consensus = True
                except Exception:
                    pass

            is_associated = True
            screening_reason = ""
            if not has_consensus:
                try:
                    screen_res = screen_article_relevance_llm(
                        client=client,
                        gemini_client=gemini_client,
                        abstract=abstract,
                        title=title,
                        exposure=exposure_keyword,
                        model_override=model
                    )
                    if screen_res:
                        is_associated = screen_res.get('is_directly_associated', True)
                        screening_reason = screen_res.get('reason', '')
                except Exception as e:
                    print(f"  [Screening] Error screening {study_label}: {e}")
            else:
                print(f"  [Screening] Bypassing screening for '{study_label}' due to existing consensus in verifications.json")

            if not is_associated:
                print(f"  [Screening] Skipping '{study_label}': Not directly associated with exposure '{exposure_keyword}'. Reason: {screening_reason}")
                return

            # --- LLM EXTRACTION ---
            extracted = None
            used_llm = "None"
            oai_extracted = None
            gemini_extracted = None

            # Sequential calls inside the article worker thread to avoid nested deadlocks
            is_openai_model = (model or "").startswith("openai.") or (model or "").startswith("gpt-")
            if client and (is_openai_model or os.getenv("OPENAI_BASE_URL")):
                try:
                    raw_extracted = extract_info_llm(client, abstract, title, disease_keyword or "Cancer", exposure_keyword or "Exposure", outcome_keyword or "Incidence", model_override=model)
                    oai_extracted = flatten_json(raw_extracted)
                except Exception as e:
                    print(f"  [LLM] OpenAI Error for {study_label}: {e}")

            if os.getenv("OPENAI_BASE_URL") and client:
                try:
                    raw_gemini = extract_info_llm(client, abstract, title, disease_keyword or "Cancer", exposure_keyword or "Exposure", outcome_keyword or "Incidence", model_override="google.gemini-2.5-flash")
                    gemini_extracted = flatten_json(raw_gemini)
                except Exception as e:
                    print(f"  [LLM] Gemini (Cornell) Error for {study_label}: {e}")
            elif gemini_client:
                try:
                    raw_gemini = extract_info_gemini(gemini_client, gemini_model_name, abstract, title, disease_keyword or "Cancer", exposure_keyword or "Exposure", outcome_keyword or "Incidence")
                    gemini_extracted = flatten_json(raw_gemini)
                except Exception as e:
                    print(f"  [LLM] Gemini Error for {study_label}: {e}")

            if oai_extracted and oai_extracted.get('effect_size'):
                extracted = oai_extracted
                used_llm = "OpenAI"
            elif gemini_extracted and gemini_extracted.get('effect_size'):
                extracted = gemini_extracted
                used_llm = "Gemini"
            else:
                extracted = oai_extracted or gemini_extracted

            if not extracted and not client and not gemini_client:
                 print("Error: No LLM Client initialized.")
                 return
                 
            # Consensus check for inversion
            if extracted and extracted.get('effect_size'):
                if oai_extracted and oai_extracted.get('effect_size') and gemini_extracted and gemini_extracted.get('effect_size'):
                    oai_inv = oai_extracted.get('needs_inversion', False)
                    gem_inv = gemini_extracted.get('needs_inversion', False)
                    if oai_inv != gem_inv:
                        print(f"  [Direction] LLMs disagree on inversion (OpenAI: {oai_inv}, Gemini: {gem_inv}). Cancelling inversion.")
                        extracted['needs_inversion'] = False
                    else:
                        extracted['needs_inversion'] = oai_inv
                elif extracted.get('needs_inversion'):
                    print(f"  [Direction] Only {used_llm} succeeded. Proceeding with flagged inversion (needs_inversion=True).")
                    extracted['needs_inversion'] = True

            if extracted and extracted.get('effect_size'):
                 # Quality Score Calculation
                 jbi = extracted.get('jbi_answers', {})
                 jbi_type = extracted.get('jbi_checklist_type', 'cross_sectional')
                 yes_count = sum(1 for v in jbi.values() if str(v).lower() == 'yes')
                 na_count = sum(1 for v in jbi.values() if str(v).lower() == 'na')
                 checklist_totals = {'cohort': 11, 'case_control': 10, 'cross_sectional': 8}
                 base_total = checklist_totals.get(jbi_type, 8)
                 total_potential = base_total - na_count
                 
                 quality_percentage = 0
                 quality_score = "Fair"
                 if total_potential > 0:
                     quality_percentage = round((yes_count / total_potential) * 100, 1)
                     if quality_percentage > 80: quality_score = "Good"
                     elif quality_percentage >= 51: quality_score = "Moderate"
                     else: quality_score = "Fair"

                 comparison_type = extracted.get('comparison_type') or "-"
                 
                 if comparison_type == "-" or not comparison_type:
                     comp_patterns = [
                         r'(Q\d+\s+vs\.?\s+Q\d+)',
                         r'(highest\s+vs\.?\s+lowest)',
                         r'(top\s+vs\.?\s+bottom)',
                         r'(tertile\s+\d+\s+vs\.?\s+\d+)',
                         r'(quartile\s+\d+\s+vs\.?\s+\d+)',
                         r'(quintile\s+\d+\s+vs\.?\s+\d+)',
                         r'(per\s+\d+[- ](?:unit|SD|mg|mcg|unit|IU)[^.]*)',
                         r'(yes\s+vs\.?\s+no)',
                         r'(ever\s+vs\.?\s+never)'
                     ]
                     for pat in comp_patterns:
                         match = re.search(pat, abstract, re.IGNORECASE)
                         if match:
                             comparison_type = match.group(1)
                             break

                 # Relevance check
                 relevance_info = extracted.get('relevance_check', {})
                 relevance_verdict = relevance_info.get('verdict', 'Relevant') if isinstance(relevance_info, dict) else 'Relevant'
                 relevance_reason = relevance_info.get('reason', '') if isinstance(relevance_info, dict) else ''

                 # Skip studies the LLM deems not relevant, unless we have a verification consensus on disk
                 has_consensus = False
                 verifications_file = os.path.join(DATA_DIR, "verifications.json")
                 if os.path.exists(verifications_file):
                     try:
                         with open(verifications_file, 'r', encoding='utf-8') as f:
                             verifications = json.load(f)
                         canonical_exp = get_canonical_name(exposure_keyword)
                         context_key = f"{disease_keyword}_{canonical_exp}_{outcome_keyword}".lower().replace(" ", "_")
                         if str(pmid) in verifications:
                             v_info = verifications[str(pmid)]
                             if context_key in v_info.get("contexts", {}):
                                 consensus = v_info["contexts"][context_key].get("consensus_data")
                                 if consensus:
                                     has_consensus = True
                     except Exception:
                         pass

                 if relevance_verdict == 'Not Relevant' and not has_consensus:
                     print(f"  [Relevance] Skipping '{study_label}': {relevance_reason}")
                     return
                 elif relevance_verdict == 'Not Relevant' and has_consensus:
                     print(f"  [Relevance] Bypassing skip for '{study_label}' due to existing consensus in verifications.json")
                     relevance_verdict = 'Relevant'

                 # --- Direction standardisation: always HIGH vs LOW ---
                 raw_es     = extracted.get('effect_size')
                 raw_lower  = extracted.get('ci_lower')
                 raw_upper  = extracted.get('ci_upper')
                 needs_inversion = extracted.get('needs_inversion', False)

                 if needs_inversion and raw_es and raw_lower and raw_upper:
                     try:
                         raw_es    = round(1.0 / raw_es,    4)
                         new_lower = round(1.0 / raw_upper, 4)
                         new_upper = round(1.0 / raw_lower, 4)
                         raw_lower, raw_upper = new_lower, new_upper
                         comparison_type = comparison_type + " [inverted \u21d2 high vs low]"
                         print(f"  [Direction] Inverted ES for {study_label}: LLM flagged needs_inversion=True")
                     except (ZeroDivisionError, TypeError):
                         pass

                 row = {
                     "Study": study_label,
                     "Effect Size": raw_es,
                     "Effect Type": extracted.get('effect_type'),
                     "comparison_type": comparison_type,
                     "Sample Size": extracted.get('total_n') or extracted.get('Participants'),
                     "Cases": extracted.get('cases'),
                     "Lower CI": raw_lower,
                     "Upper CI": raw_upper,
                     "Population": "General",
                     "Authors": authors,
                     "Reference": title,
                     "Journal": article_data.get('Journal', {}).get('Title', 'Unknown'),
                     "Year": year,
                     "Link": pmid_link,
                     "PMID": str(pmid),
                     "Design": extracted.get('design', 'Unknown'),
                     "Timing": extracted.get('timing', 'Unknown'),
                     "Continent": extracted.get('continent', 'Other'),
                     "Stage": extracted.get('stage', 'Unspecified'),
                    "Quality %": quality_percentage,
                     "Quality Score": quality_score,
                     "JBI": jbi,
                     "Relevance": relevance_verdict,
                     "Relevance Reason": relevance_reason,
                 }
                 
                 row = add_estimated_cases_to_row(row, disease_keyword)
                 row["SE"] = calculate_se(row)
                 with data_lock:
                     data.append(row)
                 print(f"  [{used_llm}] Extracted: {study_label} - ES: {row['Effect Size']} (Cases: {row['Cases']})")

        except Exception as e:
            print(f"Error processing article {i}: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(process_single_article, enumerate(filtered_articles))

    return pd.DataFrame(data)

def extract_info_gemini(client, model_name, abstract, title, disease, exposure, outcome):
    """
    Uses Google Gemini to extract structured data from abstract.
    """
    prompt = f"""
    Analyze the following medical abstract and extract the key statistics for the relationship between the exposure '{exposure}' and the disease '{disease}' (Outcome: {outcome}).
    
    Abstract: "{abstract}"
    Title: "{title}"
    
    IMPORTANT: 
    - Some abstracts report results for MULTIPLE exposures or MULTIPLE diseases (e.g., Vitamin D vs Breast Cancer AND Vitamin D vs Ovarian Cancer).
    - You MUST only extract the result that corresponds to the REQUESTED exposure and REQUESTED disease.
    - IMPORTANT - OUTCOME TYPE: The requested outcome is '{outcome}'. 
        - If '{outcome}' is 'Incidence', you MUST ONLY extract results for the RISK of DEVELOPING the disease in a baseline-healthy population. DO NOT extract results for 'Survival', 'Recurrence', or 'Mortality' in patients already diagnosed.
        - If '{outcome}' is 'Survival', you MUST ONLY extract results for length of life, risk of death, or overall survival in diagnosed patients. DO NOT extract results for 'Incidence' or 'Risk of Development'.
        - If '{outcome}' is 'Progression-Free Survival', focus on time to recurrence or progression.
    - If the abstract DOES NOT MENTION the exposure '{exposure}' or a very direct synonym, return NULL for effect_size. DO NOT guess or use unrelated numbers like MRI AUCs, p-values, or other coefficients.
    - If there are multiple estimates (e.g., age-adjusted and multivariable adjusted), PRIORITIZE THE MULTIVARIABLE ADJUSTED estimate.
    Synonyms and Matches:
    - If the abstract mentions an exposure like "Vitamin D supplementation" or "25(OH)D levels", and the user asked for "Vitamin D", consider these a MATCH.
    - If the user asked for "folic acid" and the study mentions "folate" or "dietary folate" or "folate intake", consider these a MATCH.
    - If the study examines the requested exposure as a modifier, interaction partner, or in combination with another factor (for example, looking at the interaction between alcohol and folate/folic acid), this is considered a MATCH and is Relevant.

    Return a JSON object with the following keys:
    - effect_size: (float/number) The central estimate (HR, OR, RR). If the study reports results stratified by the exposure (e.g. effect of alcohol under low folate vs high folate), extract the effect size that represents the higher risk or the key finding reported for the interaction.
    - effect_type: (string) "HR", "OR", or "RR".
    - comparison_type: (string) Context of the comparison (e.g., "per SD increase", "Q1 vs Q4", "Q1 vs Q5", "Highest vs Lowest", "Continuous", "Yes vs No", or the specific interaction/stratification context).
    - ci_lower: (float/number) Lower 95% Confidence Interval.
    - ci_upper: (float/number) Upper 95% Confidence Interval.
    - total_n: (string/int) Total number of participants in the study (Sample Size).
    - cases: (string/int) Number of { "events" if outcome == "Survival" else "cancer cases" } in the study.
    - design: (string) Study design (e.g., Cohort, Case-Control).
    - timing: (string) Prospective or Retrospective.
    - continent: (string) Continent of study (North America, Europe, Asia, etc.).
    - stage: (string) Cancer stage/subtype if specified (e.g., "Early", "Advanced").
    - jbi_checklist_type: (string) Which JBI checklist was used: "cohort", "case_control", or "cross_sectional".
    - jbi_answers: (dict) Answers to JBI critical appraisal questions. Choose the checklist based on the study design:
    
        IF the study is a COHORT STUDY, answer these 11 questions (keys "q1" through "q11"):
            Q1: Were the two groups similar and recruited from the same population?
            Q2: Were the exposures measured similarly to assign people to both exposed and unexposed groups?
            Q3: Was the exposure measured in a valid and reliable way?
            Q4: Were confounding factors identified?
            Q5: Were strategies to deal with confounding factors stated?
            Q6: Were the groups/participants free of the outcome at the start of the study (or at the moment of exposure)?
            Q7: Were the outcomes measured in a valid and reliable way?
            Q8: Was the follow up time reported and sufficient to be long enough for outcomes to occur?
            Q9: Was follow up complete, and if not, were the reasons to loss to follow up described and explored?
            Q10: Were strategies to address incomplete follow up utilized?
            Q11: Was appropriate statistical analysis used?
            Set jbi_checklist_type to "cohort". MUST RETURN EXACTLY 11 KEYS ("q1" to "q11") in the jbi_answers object.
        
        IF the study is a CASE-CONTROL STUDY, answer these 10 questions (keys "q1" through "q10"):
            Q1: Were the groups comparable other than the presence of disease in cases or the absence of disease in controls?
            Q2: Were cases and controls matched appropriately?
            Q3: Were the same criteria used for identification of cases and controls?
            Q4: Was exposure measured in a standard, valid and reliable way?
            Q5: Was exposure measured in the same way for cases and controls?
            Q6: Were confounding factors identified?
            Q7: Were strategies to deal with confounding factors stated?
            Q8: Were outcomes assessed in a standard, valid and reliable way for cases and controls?
            Q9: Was the exposure period of interest long enough to be meaningful?
            Q10: Was appropriate statistical analysis used?
            Set jbi_checklist_type to "case_control". MUST RETURN EXACTLY 10 KEYS ("q1" to "q10") in the jbi_answers object.
        
        OTHERWISE (Cross-Sectional or unknown), answer these 8 questions (keys "q1" through "q8"):
            Q1: Were the criteria for inclusion in the sample clearly defined?
            Q2: Were the study subjects and the setting described in detail?
            Q3: Was the exposure measured in a valid and reliable way?
            Q4: Were objective, standard criteria used for measurement of the condition?
            Q5: Were confounding factors identified?
            Q6: Were strategies to deal with confounding factors stated?
            Q7: Were the outcomes measured in a valid and reliable way?
            Q8: Was appropriate statistical analysis used?
            Set jbi_checklist_type to "cross_sectional". MUST RETURN EXACTLY 8 KEYS ("q1" to "q8") in the jbi_answers object.
        
        Value for each key MUST be one of: "Yes", "No", "Unclear", or "NA". Do NOT skip questions.
    
    Rules:
    - If NO relevant effect size is found for {exposure} and {disease}, OR if the study is an ANIMAL STUDY (mice, rat, etc.), case report, general literature review, or meta-analysis, return null/None for effect_size.
    - Handle standard text like "HR 1.2 (0.9-1.5)".
    - Convert text "reference" or "null" to None.
    - Return ONLY valid JSON.

    Also return a relevance_check object:
    - relevance_check.verdict: one of "Relevant", "Questionable", or "Not Relevant"
        - "Relevant": study clearly measures the requested '{exposure}' (or recognized synonym/biomarker/modifier) -> '{disease}' -> '{outcome}' relationship. This includes studies where '{exposure}' is studied as a modifier/interaction partner with another factor (e.g. alcohol). CRITICAL: A study that finds NO association (null finding) between '{exposure}' and '{disease}' is STILL Relevant.
        - "Questionable": study seems related but has a scope mismatch (e.g. wrong population subgroup, indirect endpoint, surrogate marker only).
        - "Not Relevant": the study does not examine '{exposure}' or its synonyms at all, or only mentions it in passing without any analysis or data. Only judge the exposure, NOT the direction or magnitude of the association.
    - relevance_check.reason: one sentence explaining why it matches or doesn't match.

    Also return:
    - needs_inversion: (boolean) Evaluating if the effect size must be mathematically inverted (1/x). 
    CRITICAL STANDARD: We MUST standardize all results to report the risk of the HIGHEST exposure compared to the LOWEST exposure (i.e. 'High vs Low', where LOW is the reference baseline).
    1. If the study reports the effect of LOW exposure compared to HIGH exposure as the reference (e.g., "Lowest quartile showed increased risk OR=2.15", or "Q1 vs Q4"), you MUST set needs_inversion to TRUE. 
    2. If the study reports the effect of HIGH exposure compared to LOW exposure as the reference (e.g., "Highest quartile had reduced risk OR=0.45", or "Q4 vs Q1"), set needs_inversion to FALSE.
    3. If the effect size represents a continuous increase (e.g., "per 10 ng/mL increase"), set needs_inversion to FALSE.
    """
    
    import time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            
            # Accessing usage metadata in google-genai SDK
            if response.usage_metadata:
                track_usage(model_name, response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
                
            return json.loads(response.text)
        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = "429" in error_msg or "too many requests" in error_msg
            is_hard_quota = "exhausted" in error_msg or "billing" in error_msg
            
            if is_rate_limit and not is_hard_quota:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    print(f"  [Gemini] Rate limit hit. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            
            if "429" in error_msg or "quota" in error_msg:
                print("\n  [Gemini] Hard Quota exceeded. Disabling Gemini for the remainder of this run.\n")
                global gemini_client
                gemini_client = None
            else:
                print(f"Gemini LLM Error: {e}")
            return None
    return None

def extract_info_llm(client, abstract, title, disease, exposure, outcome, model_override=None):
    """
    Uses OpenAI to extract structured data from abstract.
    """
    prompt = f"""
    Analyze the following medical abstract and extract the key statistics for the relationship between the exposure '{exposure}' and the disease '{disease}' (Outcome: {outcome}).
    
    Abstract: "{abstract}"
    Title: "{title}"
    
    Synonyms and Matches:
    - If the abstract mentions an exposure like "Vitamin D supplementation" or "25(OH)D levels", and the user asked for "Vitamin D", consider these a MATCH.
    - If the user asked for "folic acid" and the study mentions "folate" or "dietary folate" or "folate intake", consider these a MATCH.
    - If the study examines the requested exposure as a modifier, interaction partner, or in combination with another factor (for example, looking at the interaction between alcohol and folate/folic acid), this is considered a MATCH and is Relevant.

    Return a JSON object with the following keys:
    - effect_size: (float/number) The central estimate (HR, OR, RR). If the study reports results stratified by the exposure (e.g. effect of alcohol under low folate vs high folate), extract the effect size that represents the higher risk or the key finding reported for the interaction.
    - effect_type: (string) "HR", "OR", or "RR".
    - comparison_type: (string) Context of the comparison (e.g., "per SD increase", "Q1 vs Q4", "Q1 vs Q5", "Highest vs Lowest", "Continuous", "Yes vs No", or the specific interaction/stratification context).
    - ci_lower: (float/number) Lower 95% Confidence Interval.
    - ci_upper: (float/number) Upper 95% Confidence Interval.
    - total_n: (string/int) Total number of participants in the study (Sample Size).
    - cases: (string/int) Number of { "events" if outcome == "Survival" else "cancer cases" } in the study.
    - design: (string) Study design (e.g., Cohort, Case-Control).
    - timing: (string) Prospective or Retrospective.
    - continent: (string) Continent of study (North America, Europe, Asia, etc.).
    - stage: (string) Cancer stage/subtype if specified (e.g., "Early", "Advanced").
    - jbi_checklist_type: (string) Which JBI checklist was used: "cohort", "case_control", or "cross_sectional".
    - jbi_answers: (dict) Answers to JBI critical appraisal questions. Choose the checklist based on the study design:
    
        IF the study is a COHORT STUDY, answer these 11 questions (keys "q1" through "q11"):
            Q1: Were the two groups similar and recruited from the same population?
            Q2: Were the exposures measured similarly to assign people to both exposed and unexposed groups?
            Q3: Was the exposure measured in a valid and reliable way?
            Q4: Were confounding factors identified?
            Q5: Were strategies to deal with confounding factors stated?
            Q6: Were the groups/participants free of the outcome at the start of the study (or at the moment of exposure)?
            Q7: Were the outcomes measured in a valid and reliable way?
            Q8: Was the follow up time reported and sufficient to be long enough for outcomes to occur?
            Q9: Was follow up complete, and if not, were the reasons to loss to follow up described and explored?
            Q10: Were strategies to address incomplete follow up utilized?
            Q11: Was appropriate statistical analysis used?
            Set jbi_checklist_type to "cohort". MUST RETURN EXACTLY 11 KEYS ("q1" to "q11") in the jbi_answers object.
        
        IF the study is a CASE-CONTROL STUDY, answer these 10 questions (keys "q1" through "q10"):
            Q1: Were the groups comparable other than the presence of disease in cases or the absence of disease in controls?
            Q2: Were cases and controls matched appropriately?
            Q3: Were the same criteria used for identification of cases and controls?
            Q4: Was exposure measured in a standard, valid and reliable way?
            Q5: Was exposure measured in the same way for cases and controls?
            Q6: Were confounding factors identified?
            Q7: Were strategies to deal with confounding factors stated?
            Q8: Were outcomes assessed in a standard, valid and reliable way for cases and controls?
            Q9: Was the exposure period of interest long enough to be meaningful?
            Q10: Was appropriate statistical analysis used?
            Set jbi_checklist_type to "case_control". MUST RETURN EXACTLY 10 KEYS ("q1" to "q10") in the jbi_answers object.
        
        OTHERWISE (Cross-Sectional or unknown), answer these 8 questions (keys "q1" through "q8"):
            Q1: Were the criteria for inclusion in the sample clearly defined?
            Q2: Were the study subjects and the setting described in detail?
            Q3: Was the exposure measured in a valid and reliable way?
            Q4: Were objective, standard criteria used for measurement of the condition?
            Q5: Were confounding factors identified?
            Q6: Were strategies to deal with confounding factors stated?
            Q7: Were the outcomes measured in a valid and reliable way?
            Q8: Was appropriate statistical analysis used?
            Set jbi_checklist_type to "cross_sectional". MUST RETURN EXACTLY 8 KEYS ("q1" to "q8") in the jbi_answers object.
        
        Value for each key MUST be one of: "Yes", "No", "Unclear", or "NA". Do NOT skip questions.
    
    Rules:
    - If NO relevant effect size is found for {exposure} and {disease}, OR if the study is an ANIMAL STUDY (mice, rat, etc.), case report, general literature review, or meta-analysis, return null/None for effect_size.
    - Handle standard text like "HR 1.2 (0.9-1.5)".
    - Convert text "reference" or "null" to None.
    - Return ONLY valid JSON.

    Also return a relevance_check object:
    - relevance_check.verdict: one of "Relevant", "Questionable", or "Not Relevant"
        - "Relevant": study clearly measures the requested '{exposure}' (or recognized synonym/biomarker/modifier) -> '{disease}' -> '{outcome}' relationship. This includes studies where '{exposure}' is studied as a modifier/interaction partner with another factor (e.g. alcohol). CRITICAL: A study that finds NO association (null finding) between '{exposure}' and '{disease}' is STILL Relevant.
        - "Questionable": study seems related but has a scope mismatch (e.g. wrong population subgroup, indirect endpoint, surrogate marker only).
        - "Not Relevant": the study does not examine '{exposure}' or its synonyms at all, or only mentions it in passing without any analysis or data. Only judge the exposure, NOT the direction or magnitude of the association.
    - relevance_check.reason: one sentence explaining why it matches or doesn't match.

    Also return:
    - needs_inversion: (boolean) Evaluating if the effect size must be mathematically inverted (1/x). 
    CRITICAL STANDARD: We MUST standardize all results to report the risk of the HIGHEST exposure compared to the LOWEST exposure (i.e. 'High vs Low', where LOW is the reference baseline).
    1. If the study reports the effect of LOW exposure compared to HIGH exposure as the reference (e.g., "Lowest quartile showed increased risk OR=2.15", or "Q1 vs Q4"), you MUST set needs_inversion to TRUE. 
    2. If the study reports the effect of HIGH exposure compared to LOW exposure as the reference (e.g., "Highest quartile had reduced risk OR=0.45", or "Q4 vs Q1"), set needs_inversion to FALSE.
    3. If the effect size represents a continuous increase (e.g., "per 10 ng/mL increase"), set needs_inversion to FALSE.
    """
    
    import time
    max_retries = 5
    model_name = get_openai_model_name(model_override)
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful medical research assistant capable of extracting structured data from scientific abstracts. Outcome response must be purely JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"},
                timeout=30.0
            )
            if hasattr(response, 'usage'):
                track_usage(model_name, response.usage.prompt_tokens, response.usage.completion_tokens)
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = "429" in error_msg or "rate limit" in error_msg
            is_hard_quota = "insufficient_quota" in error_msg or "billing" in error_msg
            
            if is_rate_limit and not is_hard_quota:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    print(f"  [OpenAI] Rate limit hit. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue

            if "429" in error_msg or "quota" in error_msg:
                print("\n  [OpenAI] Hard Quota exceeded. Disabling OpenAI for the remainder of this run.\n")
                globals()['client'] = None
            else:
                print(f"LLM Error: {e}")
            return None
    return None

def screen_article_relevance_llm(client, gemini_client, abstract, title, exposure, model_override=None):
    """
    Use LLM to determine if the article title/abstract is directly associated with the exposure of interest.
    Specifically excludes radioactive iodine / radioiodine therapy if exposure is iodine.
    """
    exposure_lower = (exposure or "").lower()
    prompt = f"""
    You are a screening layer for a systematic review. Determine if the following article is DIRECTLY associated with the exposure of interest: "{exposure}".
    
    Article Title: "{title}"
    Article Abstract: "{abstract}"
    
    Guidelines:
    - The study MUST examine "{exposure}" (or its direct nutritional synonyms/biomarkers, e.g. iodide/urinary iodine/iodized salt for iodine).
    - If the exposure of interest is "{exposure}" and contains the word "iodine" (e.g. iodine, iodine intake, iodine status, iodine supplementation, iodine levels, urinary iodine, iodide, etc.), it MUST NOT be about radioactive iodine (RAI) therapy, radioiodine treatment, I-131 therapy, thyroid ablation, or medical radiation treatment for thyroid disease. These are medical radiation procedures and NOT dietary/nutritional exposure.
    - If the study is about an entirely different concept that happens to share a synonym or substring, or is only about a medical treatment using that substance (like radioactive isotopes), classify it as NOT directly associated.
    
    Return a JSON object with the following keys:
    - is_directly_associated: (boolean) true if the study is directly associated with the exposure of interest, false otherwise.
    - reason: (string) A one-sentence explanation of the verdict.
    """

    # We try OpenAI first if client is available
    if client:
        try:
            model_name = get_openai_model_name(model_override)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful screening assistant. Outcome response must be purely JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"},
                timeout=20.0
            )
            if hasattr(response, 'usage'):
                track_usage(model_name, response.usage.prompt_tokens, response.usage.completion_tokens)
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"  [Screening LLM] OpenAI screening error: {e}")

    # Fallback to Gemini if gemini_client is available
    if gemini_client:
        try:
            m_name = globals().get('gemini_model_name') or 'gemini-2.5-flash'
            response = gemini_client.models.generate_content(
                model=m_name,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            if response.usage_metadata:
                track_usage(m_name, response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
            return json.loads(response.text)
        except Exception as e:
            print(f"  [Screening LLM] Gemini screening error: {e}")
            
    # Default return when no LLM succeeded or was configured
    return {"is_directly_associated": True, "reason": "No LLM client succeeded; bypassed screening."}

if __name__ == "__main__":
    main()
