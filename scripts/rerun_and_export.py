import os
import sys
import json
import re
import pandas as pd
import numpy as np
import warnings

# Add parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
import meta_analysis

# Suppress runtime warnings from meta-analysis
warnings.filterwarnings('ignore')

def update_cache_files(disease, outcome="Incidence", exclude_meta=True):
    print(f"\n==========================================")
    print(f"Updating cache files for {disease}...")
    print(f"==========================================")
    
    results_dir = 'Cached_results'
    if not os.path.exists(results_dir):
        print(f"Error: {results_dir} not found.")
        return
        
    folders = os.listdir(results_dir)
    print(f"Found {len(folders)} folders in Cached_results.")
    
    # Load verifications once
    verifications = {}
    if os.path.exists('data/verifications.json'):
        try:
            with open('data/verifications.json', 'r', encoding='utf-8') as vf:
                verifications = json.load(vf)
        except Exception as e:
            print(f"Error loading verifications.json: {e}")
            
    updated_count = 0
    total_processed = 0
    
    for folder in folders:
        # Resolve canonical name and check files
        canonical_exp = meta_analysis.get_canonical_name(folder)
        safe_exposure = app.safe_path_component(canonical_exp)
        
        # Build path to cache file
        # format of filename: uterine_cancer_incidence_true_all.json
        safe_disease = app.safe_path_component(disease)
        safe_outcome = app.safe_path_component(outcome)
        filename = f"{safe_disease}_{safe_outcome}_{str(exclude_meta).lower()}_all.json"
        
        file_path = os.path.join(results_dir, folder, filename)
        if not os.path.exists(file_path):
            continue
            
        total_processed += 1
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                
            if "studies" not in cache:
                continue
                
            studies = cache.get("studies", [])
            context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
            
            # Apply verifications
            cache_updated = False
            for study in studies:
                pmid = str(study.get("PMID"))
                v_info = verifications.get(pmid, {})
                
                # Check for context exclusions
                context_excl = v_info.get('context_exclusions', {})
                exclusion_val = context_excl.get(context_key, 0)
                if study.get("exclusions", 0) != exclusion_val:
                    study["exclusions"] = exclusion_val
                    cache_updated = True
                    
                # Apply consensus or latest submission
                contexts = v_info.get('contexts', {})
                current_context_data = contexts.get(context_key, {})
                consensus = current_context_data.get('consensus_data')
                submissions = current_context_data.get('submissions', [])
                
                overlay_data = None
                if consensus:
                    overlay_data = consensus
                elif submissions:
                    overlay_data = submissions[-1]['data']
                    
                if overlay_data:
                    for key, val in overlay_data.items():
                        if val is not None and val != "" and val != "Not specified":
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
                                
            # Re-run meta analysis on updated/existing studies
            # Only include valid studies (exclusions < 2)
            valid_studies = [s for s in studies if s.get('exclusions', 0) < 2]
            df_new = pd.DataFrame(valid_studies)
            
            if len(df_new) > 0:
                # Ensure numeric precision
                for col in ['Effect Size', 'Lower CI', 'Upper CI', 'SE', 'Cases', 'Sample Size']:
                    if col in df_new.columns:
                        df_new[col] = pd.to_numeric(df_new[col].astype(str).str.replace(',', '').str.strip(), errors='coerce')
                
                # We can perform the meta-analysis again to regenerate the forest plot, funnel plot, and baujat plot on disk
                # and update the headline and summary html.
                new_meta = meta_analysis.perform_meta_analysis(df_new, disease, folder, outcome=outcome, exclude_meta=exclude_meta)
                
                # Update key result fields in cache
                for key in ['headline', 'summary_html', 'plot_url', 'funnel_plot_url', 'baujat_plot_url']:
                    cache[key] = new_meta.get(key)
            else:
                cache['headline'] = None
                cache['summary_html'] = None
                cache['plot_url'] = None
                cache['funnel_plot_url'] = None
                cache['baujat_plot_url'] = None
                
            # Save updated cache safely
            cache_str = json.dumps(app.sanitize_data(cache), indent=4)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cache_str)
                
            updated_count += 1
            if cache_updated:
                print(f"  Updated cache and plots for: {folder}")
                
        except Exception as e:
            print(f"  Error updating {folder}: {e}")
            
    print(f"Processed {total_processed} cache files. Saved updates for {updated_count} files.")


def export_disease_results(disease, disease_label, outcome="Incidence", exclude_meta=True):
    print(f"\n==========================================")
    print(f"Exporting Excel sheets for {disease}...")
    print(f"==========================================")
    
    results_dir = 'Cached_results'
    folders = os.listdir(results_dir)
    
    blacklist = ['multivitamin']
    
    # Load verifications once
    verifications = {}
    if os.path.exists('data/verifications.json'):
        try:
            with open('data/verifications.json', 'r', encoding='utf-8') as vf:
                verifications = json.load(vf)
        except: pass
        
    all_combined_results = []
    all_fixed_results = []
    
    for folder in folders:
        if folder in blacklist:
            continue
            
        safe_disease = app.safe_path_component(disease)
        safe_outcome = app.safe_path_component(outcome)
        filename = f"{safe_disease}_{safe_outcome}_{str(exclude_meta).lower()}_all.json"
        file_path = os.path.join(results_dir, folder, filename)
        
        if not os.path.exists(file_path):
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            studies = data.get('studies', [])
            if not studies:
                continue
                
            # Filter verifications and exclusions
            canonical_exp = meta_analysis.get_canonical_name(folder)
            context_key = f"{disease}_{canonical_exp}_{outcome}".lower().replace(" ", "_")
            
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
            for col in ['Effect Size', 'Lower CI', 'Upper CI', 'Cases', 'Sample Size', 'Estimated Cases']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.strip(), errors='coerce')
                    
            # Filter Cases >= 50
            cases_col = df['Cases'].fillna(df.get('Estimated Cases', np.nan)) if 'Cases' in df.columns else df.get('Estimated Cases', np.nan)
            df_valid = df[
                (df['Effect Size'] > 0) & 
                (df['Lower CI'] > 0) & 
                (df['Upper CI'] > 0) &
                (cases_col >= 50)
            ].copy()
            
            if len(df_valid) == 0:
                continue
                
            # Perform meta-analysis
            res_dict = meta_analysis.perform_meta_analysis(df_valid, disease, folder)
            headline = res_dict.get('headline')
            
            if not headline:
                continue
                
            # Format results for Combined Excel (style of export_exposures_excel.py)
            all_combined_results.append({
                "Exposure": folder,
                "number studies": int(len(df_valid)),
                "Pooled RR": headline.get('pooled_es', 0.0),
                "lower CI RR": headline.get('ci_low', 0.0),
                "upper CI RR": headline.get('ci_upp', 0.0),
                "lower PI RR": headline.get('pi_low'),
                "upper PI RR": headline.get('pi_upp'),
                "I^2 (%)": round(headline.get('i2', 0.0), 1),
                "eggers p-value": headline.get('eggers_p'),
                "total N": int(df_valid['Sample Size'].sum() if 'Sample Size' in df_valid.columns else 0),
                "total Cases": int((df_valid['Cases'].fillna(df_valid.get('Estimated Cases', 0))).sum() if 'Cases' in df_valid.columns else 0)
            })
            
            # Format results for FIXED Excel (style of export_exposures_refreshed.py)
            all_fixed_results.append({
                "Exposure": folder,
                "$n$ studies": int(len(df_valid)),
                "Pooled ES": headline.get('pooled_es', 0.0),
                "CI Low": headline.get('ci_low', 0.0),
                "CI Upp": headline.get('ci_upp', 0.0),
                "$I^2$ (%)": round(headline.get('i2', 0.0), 1),
                "Total $N$": int(df_valid['Sample Size'].sum() if 'Sample Size' in df_valid.columns else 0),
                "N cases": int((df_valid['Cases'].fillna(df_valid.get('Estimated Cases', 0))).sum() if 'Cases' in df_valid.columns else 0)
            })
            
        except Exception as e:
            print(f"  Error on {folder}: {e}")
            continue
            
    # Write combined results
    if all_combined_results:
        combined_df = pd.DataFrame(all_combined_results)
        combined_df = combined_df.sort_values(by="Pooled RR", ascending=True)
        columns_to_export = [
            "Exposure", 
            "number studies", 
            "Pooled RR", 
            "lower CI RR",
            "upper CI RR",
            "lower PI RR",
            "upper PI RR",
            "I^2 (%)", 
            "eggers p-value",
            "total N", 
            "total Cases"
        ]
        export_df = combined_df[columns_to_export]
        output_file_combined = f'exposures_meta_analysis_{disease_label}_combined.xlsx'
        export_df.to_excel(output_file_combined, index=False)
        print(f"  Exported {len(export_df)} exposures to {output_file_combined}")
    else:
        print(f"  No combined results to export for {disease}.")
        
    # Delete obsolete fixed results if they exist
    output_file_fixed = f'exposures_meta_analysis_{disease_label}_FIXED.xlsx'
    if os.path.exists(output_file_fixed):
        try:
            os.remove(output_file_fixed)
            print(f"  Removed obsolete file: {output_file_fixed}")
        except Exception as e:
            print(f"  Failed to remove {output_file_fixed}: {e}")

def main():
    diseases = [
        ("Uterine cancer", "uterine"),
        ("Ovarian cancer", "ovarian")
    ]
    
    for disease, label in diseases:
        update_cache_files(disease)
        export_disease_results(disease, label)
        
    print("\nAll tasks completed successfully!")

if __name__ == '__main__':
    main()
