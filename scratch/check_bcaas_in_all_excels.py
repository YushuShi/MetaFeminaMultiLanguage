import pandas as pd
import os

files = [
    'exposures_meta_analysis_breast_combined.xlsx',
    'exposures_meta_analysis_uterine_combined.xlsx',
    'exposures_meta_analysis_ovarian_combined.xlsx'
]

for f in files:
    path = os.path.join('Plot', f)
    if os.path.exists(path):
        df = pd.read_excel(path)
        # Rename columns to be consistent
        df.columns = [c.strip() for c in df.columns]
        # find matching rows
        # The first column might have a slightly different header name, so use df.columns[0]
        exp_col = df.columns[0]
        match = df[df[exp_col].astype(str).str.lower().str.strip() == 'bcaas']
        if not match.empty:
            print(f"\n--- {f} contains bcaas: ---")
            print(match[[exp_col, df.columns[1], df.columns[2]]])
        else:
            print(f"\n--- {f} does NOT contain bcaas ---")
