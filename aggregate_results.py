import os
import json
import pandas as pd
import numpy as np
from statsmodels.stats.meta_analysis import combine_effects
import meta_analysis

# Use standardized genetic filter
is_genetic = meta_analysis.is_genetic

def main():
    root_dir = r'c:\Users\mde4023\Downloads\MetaMamm\Cached_results'
    exposures_json_path = r'c:\Users\mde4023\Downloads\MetaMamm\static\exposures.json'
    all_results = []
    
    if not os.path.exists(root_dir):
        print(f"Error: Directory {root_dir} does not exist.")
        return

    # Source of truth for exposures
    if os.path.exists(exposures_json_path):
        with open(exposures_json_path, 'r') as f:
            allowed_exposures = [e.lower().replace(" ", "_").strip() for e in json.load(f)]
    else:
        allowed_exposures = None

    for exposure_dir in os.listdir(root_dir):
        # Exclude if not in master exposures list (e.g., valine was dropped)
        if allowed_exposures is not None and exposure_dir.lower() not in allowed_exposures:
            continue
            
        exposure_path = os.path.join(root_dir, exposure_dir)
        if not os.path.isdir(exposure_path):
            continue
            
        # Find any JSON matching breast_cancer_incidence
        json_files = [f for f in os.listdir(exposure_path) if 'breast_cancer_incidence' in f.lower() and f.endswith('.json')]
        if not json_files:
            continue
            
        # Priority: _true_all.json > _true.json > others
        selected_file = None
        if 'breast_cancer_incidence_true_all.json' in json_files:
            selected_file = 'breast_cancer_incidence_true_all.json'
        elif 'breast_cancer_incidence_true.json' in json_files:
            selected_file = 'breast_cancer_incidence_true.json'
        else:
            json_files.sort()
            selected_file = json_files[0]
            
        path = os.path.join(exposure_path, selected_file)
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            studies = data.get('studies', [])
            if not studies:
                continue
                
            df_studies = pd.DataFrame(studies)
            
            # Robust numeric conversion and basic filtering
            for col in ['Effect Size', 'Lower CI', 'Upper CI']:
                if col in df_studies.columns:
                    df_studies[col] = pd.to_numeric(df_studies[col], errors='coerce')
            
            # Filter for valid numeric results and positive CI bounds
            df_studies = df_studies[
                (df_studies['Effect Size'] > 0) & 
                (df_studies['Lower CI'] > 0) & 
                (df_studies['Upper CI'] > 0) &
                (df_studies['Upper CI'] > df_studies['Lower CI'])
            ].dropna(subset=['Effect Size', 'Lower CI', 'Upper CI']).copy()
            
            # Filter Genetic Studies
            df_studies = df_studies[~df_studies.apply(is_genetic, axis=1)].copy()
            
            if df_studies.empty:
                continue

            # Filter studies by N > 100
            filtered_rows = []
            for _, row in df_studies.iterrows():
                try:
                    n_val = row.get('Sample Size')
                    n = 0
                    if pd.notnull(n_val):
                        if isinstance(n_val, (int, float)):
                            n = float(n_val)
                        else:
                            n_str = str(n_val).replace(',', '').strip()
                            if n_str.lower() not in ['not specified', 'reference', 'na', 'none', '']:
                                n = float(n_str)
                    
                    if n > 100:
                        filtered_rows.append(row)
                except:
                    continue
            
            if not filtered_rows:
                continue
                
            df_final = pd.DataFrame(filtered_rows)
            
            # Log-transformation
            log_es = np.log(df_final['Effect Size'])
            log_low = np.log(df_final['Lower CI'])
            log_upp = np.log(df_final['Upper CI'])
            log_se = (log_upp - log_low) / 3.92
            
            # Filter out zero SE studies (likely data extraction errors like CI 1.0-1.0)
            valid_mask = log_se > 1e-6
            log_es = log_es[valid_mask]
            log_se = log_se[valid_mask]
            
            if len(log_es) < 1:
                continue

            print(f"Processing {exposure_dir}: {len(log_es)} studies...")

            if len(log_es) == 1:
                # Single study result
                idx = log_es.index[0]
                res_dict = {
                    "Exposure": exposure_dir,
                    "n_studies": 1,
                    "pooled_es": float(df_final.loc[idx, 'Effect Size']),
                    "ci_low": float(df_final.loc[idx, 'Lower CI']),
                    "ci_upp": float(df_final.loc[idx, 'Upper CI']),
                    "i2": 0.0
                }
            else:
                # Meta-analysis
                variances = log_se**2
                res = combine_effects(log_es.values, variances.values, method_re='dl', use_t=False)
                summary = res.summary_frame().iloc[-1] # Random effects row
                
                # Check for negative tau2 (dl can sometimes be wonky in statsmodels)
                if getattr(res, 'tau2', 0) < 0:
                    summary = res.summary_frame().iloc[0] # Fixed effect fallback
                
                res_dict = {
                    "Exposure": exposure_dir,
                    "n_studies": len(log_es),
                    "pooled_es": np.exp(float(summary['eff'])),
                    "ci_low": np.exp(float(summary['ci_low'])),
                    "ci_upp": np.exp(float(summary['ci_upp'])),
                    "i2": max(0, getattr(res, 'i2', 0)) * 100
                }
            
            all_results.append(res_dict)
                
        except Exception as e:
            print(f"Error processing {exposure_dir}: {e}")
            
    if all_results:
        summary_df = pd.DataFrame(all_results)
        cols = ['Exposure', 'n_studies', 'pooled_es', 'ci_low', 'ci_upp', 'i2']
        summary_df = summary_df[cols]
        output_file = 'breast_cancer_effect_sizes_N100.xlsx'
        summary_df.to_excel(output_file, index=False)
        print(f"\nSuccessfully saved results to {output_file}")
    else:
        print("No results found to aggregate.")

if __name__ == '__main__':
    main()
