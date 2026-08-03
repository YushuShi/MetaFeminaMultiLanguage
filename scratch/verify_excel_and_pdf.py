import os
import time
import pandas as pd

excel_files = [
    "Plot/exposures_meta_analysis_breast_combined.xlsx",
    "Plot/exposures_meta_analysis_ovarian_combined.xlsx",
    "Plot/exposures_meta_analysis_uterine_combined.xlsx"
]

print("=== Checking Excel Files for Alcohol ===")
for f in excel_files:
    if os.path.exists(f):
        df = pd.read_excel(f)
        matches = df[df["Exposure"].str.lower() == "alcohol"]
        if not matches.empty:
            print(f"  [FOUND] '{f}' contains Alcohol:")
            print(matches[["Exposure", "number studies", "Pooled RR"]])
        else:
            print(f"  [ERROR] '{f}' does NOT contain Alcohol")
    else:
        print(f"  [ERROR] '{f}' not found")

print("\n=== Checking Generated PDF Files ===")
pdf_files = [
    "Plot/forest_protective_breast.pdf",
    "Plot/forest_harmful_breast.pdf",
    "Plot/forest_protective_ovarian.pdf",
    "Plot/forest_harmful_ovarian.pdf",
    "Plot/forest_protective_uterine.pdf",
    "Plot/forest_harmful_uterine.pdf",
    "Plot/forest_protective_breast_dietary.pdf",
    "Plot/forest_harmful_breast_dietary.pdf",
    "Plot/forest_protective_ovarian_dietary.pdf",
    "Plot/forest_harmful_ovarian_dietary.pdf",
    "Plot/forest_protective_uterine_dietary.pdf",
    "Plot/forest_harmful_uterine_dietary.pdf",
    "Plot/comparison_dumbbell.pdf",
    "Plot/plot_es_vs_heterogeneity.pdf",
    "Plot/plot_eggers_vs_heterogeneity.pdf"
]

for f in pdf_files:
    if os.path.exists(f):
        mtime = os.path.getmtime(f)
        mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        print(f"  [OK] '{f}' last modified: {mtime_str}")
    else:
        print(f"  [ERROR] '{f}' not found")
