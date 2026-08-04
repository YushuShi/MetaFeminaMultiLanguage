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
            
            # Crowdsourced reports are advisory only and do not alter exports.
            cleaned_studies = [dict(s, exclusions=0) for s in studies]

            if not cleaned_studies:
                continue

            df = pd.DataFrame(cleaned_studies)
            
            # Numeric conversion
            for col in ['Effect Size', 'Lower CI', 'Upper CI', 'Cases', 'Sample Size', 'Estimated Cases']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.strip(), errors='coerce')
            
            # Filter Cases >= 50 (Standardized)
            cases_col = df['Cases'].fillna(df.get('Estimated Cases', np.nan)) if 'Cases' in df.columns else df.get('Estimated Cases', np.nan)
            df_valid = df[
                (df['Effect Size'] > 0) & 
                (df['Lower CI'] > 0) & 
                (df['Upper CI'] > 0) &
                (cases_col >= 50)
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
            
        except Exception as e:
            print(f"Error on {folder}: {e}")
            continue
            
    if not all_results:
        print("No results to export.")
        return
        
    results_df = pd.DataFrame(all_results)
    results_df = results_df.sort_values(by="Pooled RR", ascending=True)
    
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
    export_df = results_df[columns_to_export]
    
    os.makedirs('Plot', exist_ok=True)
    output_file = os.path.join('Plot', 'exposures_meta_analysis_breast_combined.xlsx')
    export_df.to_excel(output_file, index=False)
    print(f"Exported {len(export_df)} exposures to {output_file}")

if __name__ == '__main__':
    main()
