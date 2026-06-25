import os
import sys
import json
import shutil
import pandas as pd
import numpy as np

# Ensure parent directory is in sys.path so we can import meta_analysis
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import meta_analysis

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

def merge_screening_stats(stats1, stats2):
    if not stats1:
        return stats2
    if not stats2:
        return stats1
    
    merged = {}
    for key in ['total_fetched', 'after_prefilter', 'llm_screened_in', 'llm_screened_out', 'consensus_bypassed', 'extracted']:
        val1 = stats1.get(key, 0)
        val2 = stats2.get(key, 0)
        # Handle string or float
        try:
            val1 = int(val1) if val1 is not None else 0
        except:
            val1 = 0
        try:
            val2 = int(val2) if val2 is not None else 0
        except:
            val2 = 0
        merged[key] = val1 + val2

    # Merge prefilter_skip dict
    ps1 = stats1.get('prefilter_skip', {})
    ps2 = stats2.get('prefilter_skip', {})
    merged_ps = {}
    all_skip_keys = set(ps1.keys()).union(set(ps2.keys()))
    for k in all_skip_keys:
        v1 = ps1.get(k, 0)
        v2 = ps2.get(k, 0)
        merged_ps[k] = v1 + v2
    merged['prefilter_skip'] = merged_ps
    return merged

def merge_cancer_cache(filename, disease):
    print(f"\nProcessing {disease} ({filename})...")
    fermented_path = os.path.join('Cached_results', 'fermented_foods', filename)
    non_alcoholic_path = os.path.join('Cached_results', 'non-alcoholic_fermented_foods', filename)
    
    studies1 = []
    stats1 = None
    if os.path.exists(fermented_path):
        try:
            with open(fermented_path, 'r', encoding='utf-8') as f:
                data1 = json.load(f)
            studies1 = data1.get('studies', [])
            stats1 = data1.get('screening_stats')
            print(f"Loaded {len(studies1)} studies from fermented_foods cache.")
        except Exception as e:
            print(f"Error reading fermented_foods cache: {e}")
            
    studies2 = []
    stats2 = None
    if os.path.exists(non_alcoholic_path):
        try:
            with open(non_alcoholic_path, 'r', encoding='utf-8') as f:
                data2 = json.load(f)
            studies2 = data2.get('studies', [])
            stats2 = data2.get('screening_stats')
            print(f"Loaded {len(studies2)} studies from non-alcoholic_fermented_foods cache.")
        except Exception as e:
            print(f"Error reading non-alcoholic_fermented_foods cache: {e}")
            
    # Deduplicate and merge studies by PMID
    pmid_to_study = {}
    for s in studies1 + studies2:
        pmid = str(s.get('PMID', ''))
        if not pmid:
            continue
        if pmid not in pmid_to_study:
            pmid_to_study[pmid] = s
        else:
            # Merge fields if missing
            existing = pmid_to_study[pmid]
            for k, v in s.items():
                if v is not None and v != "" and v != "-" and (existing.get(k) is None or existing.get(k) in ["", "-"]):
                    existing[k] = v
                    
    merged_studies = list(pmid_to_study.values())
    print(f"Total merged studies: {len(merged_studies)}")
    
    if not merged_studies:
        # No studies found, write error JSON
        res = {
            "error": "No relevant evidence was identified in the reviewed sources.",
            "last_run": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    else:
        # Run meta-analysis on merged studies
        df_merged = pd.DataFrame(merged_studies)
        
        # Ensure numeric columns
        for col in ['Effect Size', 'Lower CI', 'Upper CI', 'SE']:
            if col in df_merged.columns:
                df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce')
                
        # Perform meta-analysis
        # This will save the forest plot and funnel plot to static/fermented_foods
        res = meta_analysis.perform_meta_analysis(
            df_merged,
            disease,
            "Fermented foods",
            outcome="Incidence",
            exclude_meta=True
        )
        
        # Merge screening stats
        merged_stats = merge_screening_stats(stats1, stats2)
        res['screening_stats'] = merged_stats
        res['last_run'] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        
    # Ensure target folder exists
    os.makedirs(os.path.dirname(fermented_path), exist_ok=True)
    sanitized_res = sanitize_data(res)
    with open(fermented_path, 'w', encoding='utf-8') as f:
        json.dump(sanitized_res, f, indent=4)
    print(f"Saved merged cache file to {fermented_path}")

def main():
    files_to_merge = [
        ("breast_cancer_incidence_true_all.json", "Breast Cancer"),
        ("ovarian_cancer_incidence_true_all.json", "Ovarian Cancer"),
        ("uterine_cancer_incidence_true_all.json", "Uterine Cancer")
    ]
    
    for filename, disease in files_to_merge:
        merge_cancer_cache(filename, disease)
        
    # Clean up non-alcoholic_fermented_foods cache folder
    na_cache_dir = os.path.join('Cached_results', 'non-alcoholic_fermented_foods')
    if os.path.exists(na_cache_dir):
        print(f"\nDeleting obsolete cache directory: {na_cache_dir}")
        shutil.rmtree(na_cache_dir)
        
    # Clean up non-alcoholic_fermented_foods static folder
    na_static_dir = os.path.join('static', 'non_alcoholic_fermented_foods')
    if os.path.exists(na_static_dir):
        print(f"Deleting obsolete static plots directory: {na_static_dir}")
        shutil.rmtree(na_static_dir)

if __name__ == "__main__":
    main()
