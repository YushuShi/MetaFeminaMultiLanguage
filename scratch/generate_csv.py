import json
import pandas as pd
import os
import meta_analysis

exposures_file = '../static/exposures.json'
try:
    with open(exposures_file, 'r') as f:
        exposures = json.load(f)
except Exception as e:
    # If run from root
    exposures_file = 'static/exposures.json'
    with open(exposures_file, 'r') as f:
        exposures = json.load(f)

results = []
disease = 'Breast cancer'
outcome = 'Incidence'
exclude_meta = True

for exposure in exposures:
    # Resolve canonical name first
    canonical_exposure = meta_analysis.get_canonical_name(exposure)
    safe_exposure = canonical_exposure.lower().replace(" ", "_")
    downstream_tag = "all"
    safe_analysis = f"{disease}_{outcome}_{exclude_meta}_{downstream_tag}".lower().replace(" ", "_")
    
    cache_path = os.path.join("Cached_results", safe_exposure, f"{safe_analysis}.json")
    if not os.path.exists(cache_path):
        continue
    
    try:
        with open(cache_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {cache_path}: {e}")
        continue
        
    if 'studies' not in data or not data['studies']:
        continue
        
    df = pd.DataFrame(data['studies'])
    
    if 'Cases' not in df.columns:
        continue
        
    def is_valid_cases(row):
        try:
            val = row.get('Cases')
            if pd.isna(val) or val is None:
                return False
            # Check for "more than 50 cases" (> 50)
            return float(str(val).replace(',', '')) > 50
        except:
            return False

    df_filtered = df[df.apply(is_valid_cases, axis=1)].copy()
    
    if len(df_filtered) == 0:
        continue
        
    for col in ['Effect Size', 'Lower CI', 'Upper CI', 'SE']:
        if col in df_filtered.columns:
            df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce')
    
    df_clean = df_filtered.dropna(subset=['Effect Size', 'SE'])
    if len(df_clean) == 0:
        continue
        
    try:
        meta_result = meta_analysis.perform_meta_analysis(df_clean, disease, exposure, outcome=outcome, exclude_meta=exclude_meta, df_all=df_clean)
        headline = meta_result.get('headline')
        
        if headline:
            results.append({
                'Exposure': exposure,
                'Effect Size': headline.get('pooled_es'),
                'I^2': headline.get('i2'),
                'Eggers P-Value': headline.get('eggers_p'),
                'Number of Studies': len(df_clean)
            })
    except Exception as e:
        print(f"Meta-analysis failed for {exposure}: {e}")

df_results = pd.DataFrame(results)
df_results.to_csv('exposure_results.csv', index=False)
print(f"Successfully generated exposure_results.csv with {len(results)} rows.")
