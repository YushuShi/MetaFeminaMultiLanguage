import os
import json
import pandas as pd
import numpy as np
import warnings
import meta_analysis

# Suppress runtime warnings from meta-analysis
warnings.filterwarnings('ignore')

def main():
    results_dir = 'Cached_results'
    all_results = []
    
    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} not found.")
        return

    folders = os.listdir(results_dir)
    print(f"Found {len(folders)} exposure folders.")
    
    blacklist = ['multivitamin']
    
    # Load verifications once
    verifications = {}
    if os.path.exists('data/verifications.json'):
        try:
            with open('data/verifications.json', 'r') as vf:
                verifications = json.load(vf)
        except: pass

    for folder in folders:
        if folder in blacklist:
            continue
            
        file_path = os.path.join(results_dir, folder, 'breast_cancer_incidence_true_all.json')
        if not os.path.exists(file_path):
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            studies = data.get('studies', [])
            if not studies:
                continue
            
            # Application of verifications (Matches logic in app.py)
            canonical_exp = meta_analysis.get_canonical_name(folder)
            context_key = f"breast_cancer_{canonical_exp}_incidence".lower().replace(" ", "_")
            
            cleaned_studies = []
            for s in studies:
                pmid = str(s.get('PMID'))
                v_info = verifications.get(pmid, {})
                
                # Check for context exclusions (>= 2 flags)
                if v_info.get('context_exclusions', {}).get(context_key, 0) >= 2:
                    continue
                
                # Apply consensus or latest submission
                ctx_info = v_info.get('contexts', {}).get(context_key, {})
                consensus = ctx_info.get('consensus_data')
                submissions = ctx_info.get('submissions', [])
                
                if consensus:
                    for k, v in consensus.items():
                        if v is not None and v != "" and v != "Not specified":
                            s[k] = v
                elif submissions:
                    latest = submissions[-1]['data']
                    for k, v in latest.items():
                        if v is not None and v != "" and v != "Not specified":
                            s[k] = v
                
                cleaned_studies.append(s)

            if not cleaned_studies:
                continue

            df = pd.DataFrame(cleaned_studies)
            
            # Numeric conversion
            for col in ['Effect Size', 'Lower CI', 'Upper CI', 'Cases', 'Sample Size']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.strip(), errors='coerce')
            
            # Filter Cases >= 50 (Standardized)
            df_valid = df[
                (df['Effect Size'] > 0) & 
                (df['Lower CI'] > 0) & 
                (df['Upper CI'] > 0) &
                (df['Cases'] >= 50)
            ].copy()
            
            if len(df_valid) == 0:
                continue
                
            # Perform meta_analysis via shared library
            # Note: We pass folder as the exposure for label consistency
            res_dict = meta_analysis.perform_meta_analysis(df_valid, 'Breast Cancer', folder)
            headline = res_dict.get('headline')
            
            if not headline:
                continue

            all_results.append({
                "Exposure": folder,
                "$n$ studies": int(len(df_valid)),
                "Pooled ES": headline.get('pooled_es', 0.0),
                "CI Low": headline.get('ci_low', 0.0),
                "CI Upp": headline.get('ci_upp', 0.0),
                "$I^2$ (%)": round(headline.get('i2', 0.0), 1),
                "Total $N$": int(df_valid['Sample Size'].sum() if 'Sample Size' in df_valid.columns else 0),
                "N cases": int(df_valid['Cases'].sum() if 'Cases' in df_valid.columns else 0)
            })
            
        except Exception as e:
            print(f"Error on {folder}: {e}")
            continue
            
    if not all_results:
        print("No results to export.")
        return
        
    # Delete obsolete fixed results if they exist
    output_file = 'exposures_meta_analysis_final_FIXED.xlsx'
    if os.path.exists(output_file):
        try:
            os.remove(output_file)
            print(f"Removed obsolete file: {output_file}")
        except Exception as e:
            print(f"Failed to remove {output_file}: {e}")

if __name__ == '__main__':
    main()
