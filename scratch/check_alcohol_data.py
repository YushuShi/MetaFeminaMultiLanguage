import os
import json
import pandas as pd
import numpy as np

results_dir = 'Cached_results'
exposure = 'alcohol'

for disease in ['breast', 'ovarian', 'uterine']:
    file_name = f'{disease}_cancer_incidence_true_core.json'
    file_path = os.path.join(results_dir, exposure, file_name)
    if not os.path.exists(file_path):
        print(f"{disease}: {file_name} not found")
        continue
        
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    studies = data.get('studies', [])
    if not studies:
        print(f"{disease}: No studies in JSON")
        continue
        
    df = pd.DataFrame(studies)
    
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
    
    print(f"{disease}: Total studies = {len(studies)}, Valid (Cases >= 50) = {len(df_valid)}")
