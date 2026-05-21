import os
import json
import pandas as pd
import numpy as np
from statsmodels.stats.meta_analysis import combine_effects
import warnings

# Suppress runtime warnings from meta-analysis
warnings.filterwarnings('ignore')

import meta_analysis

# Use standardized genetic filter from meta_analysis.py 
is_genetic = meta_analysis.is_genetic

def main():
    results_dir = 'Cached_results'
    all_results = []
    
    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} not found.")
        return

    folders = os.listdir(results_dir)
    print(f"Folders in {results_dir}: {len(folders)}")
    
    blacklist = ['multivitamin']
    
    for folder in folders:
        if folder in blacklist:
            continue
            
        # print(f"Processing: {folder}")
        file_path = os.path.join(results_dir, folder, 'breast_cancer_incidence_true_all.json')
        if not os.path.exists(file_path):
            # print(f"File not found: {file_path}")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            studies = data.get('studies', [])
            if not studies:
                continue
                
            df = pd.DataFrame(studies)
            
            # Filter Genetic
            df = df[~df.apply(is_genetic, axis=1)].copy()
            if df.empty:
                continue
                
            # Numeric conversion
            for col in ['Effect Size', 'Lower CI', 'Upper CI', 'Sample Size', 'Cases']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.strip(), errors='coerce')
            
            # Valid studies filter (must have ES, CI, and Cases > 50)
            df_valid = df[
                (df['Effect Size'] > 0) & 
                (df['Lower CI'] > 0) & 
                (df['Upper CI'] > 0) &
                (df['Cases'] >= 50)
            ].copy()
            
            if len(df_valid) == 0:
                continue
                
            # print(f"  {folder}: studies with cases>50: {len(df_valid)}")
                
            # Prep for meta-analysis
            y = np.log(df_valid['Effect Size'].values)
            se = (np.log(df_valid['Upper CI'].values) - np.log(df_valid['Lower CI'].values)) / (2 * 1.96)
            
            # Filter invalid SE
            mask = (se > 1e-6) & (~np.isnan(se))
            if not np.any(mask):
                continue
            y = y[mask]
            se = se[mask]
            df_final = df_valid[mask]
            
            if len(y) == 0:
                continue
                
            # Random Effects Meta-Analysis (DerSimonian-Laird)
            if len(y) == 1:
                pooled_es = float(np.exp(y[0]))
                ci_l = float(df_final.iloc[0]['Lower CI'])
                ci_u = float(df_final.iloc[0]['Upper CI'])
                i2 = 0.0
            else:
                res = combine_effects(y, se**2, method_re="dl")
                summary_df = res.summary_frame()
                
                # Robust extraction of random effect row
                re_keywords = ['random effect wls', 'random effect', 'Random-effects meta-analysis (WLS)']
                re_row = None
                for kw in re_keywords:
                    if kw in summary_df.index:
                        re_row = summary_df.loc[kw]
                        break
                
                if re_row is None:
                    re_row = summary_df.iloc[-1]
                
                # Handle cases where re_row might be a Series or DataFrame
                try:
                    log_eff = float(re_row['eff'].iloc[0]) if isinstance(re_row['eff'], pd.Series) else float(re_row['eff'])
                    log_ci_low = float(re_row['ci_low'].iloc[0]) if isinstance(re_row['ci_low'], pd.Series) else float(re_row['ci_low'])
                    log_ci_upp = float(re_row['ci_upp'].iloc[0]) if isinstance(re_row['ci_upp'], pd.Series) else float(re_row['ci_upp'])
                except:
                    log_eff = float(re_row['eff'])
                    log_ci_low = float(re_row['ci_low'])
                    log_ci_upp = float(re_row['ci_upp'])

                pooled_es = float(np.exp(log_eff))
                ci_l = float(np.exp(log_ci_low))
                ci_u = float(np.exp(log_ci_upp))
                
                # Handle i2 being a scalar or a 1-element array
                try:
                    i2 = float(res.i2.item() * 100)
                except:
                    i2 = float(res.i2 * 100)
                
            all_results.append({
                "Exposure": folder,
                "n_studies": int(len(y)),
                "total_articles": int(len(studies)),
                "Pooled ES": pooled_es,
                "CI Low": ci_l,
                "CI Upp": ci_u,
                "I2": i2,
                "Total N": float(df_final['Sample Size'].sum()),
                "N cases": float(df_final['Cases'].sum())
            })
            
        except Exception as e:
            msg = str(e)
            if "not found" not in msg:
                print(f"Error processing {folder}: {e}")
            continue
            
    print(f"Total exposures processed: {len(all_results)}")
    if all_results:
        results_df = pd.DataFrame(all_results)
        print("Exposures with at least one viable study:")
        print(results_df[['Exposure', 'n_studies']].sort_values(by='n_studies', ascending=False).to_string())
        
        # Robust filter (> 10 studies)
        robust_df = results_df[results_df['n_studies'] > 10].copy()
        
        if not robust_df.empty:
            print("\n--- Top 5 Increased Risk (> 10 studies) ---")
            top_risk = robust_df.sort_values(by="Pooled ES", ascending=False).head(5)
            print(top_risk.to_json(orient='records', indent=4))
            
            print("\n--- Top 5 Protective (> 10 studies) ---")
            top_protective = robust_df.sort_values(by="Pooled ES", ascending=True).head(5)
            print(top_protective.to_json(orient='records', indent=4))
        else:
            print("No exposures met the > 10 studies criteria.")
    else:
        print("No results found.")

if __name__ == '__main__':
    main()
