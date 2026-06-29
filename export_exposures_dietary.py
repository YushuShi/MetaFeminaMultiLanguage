import os
import json
import pandas as pd
import numpy as np
import warnings
import meta_analysis

# Suppress runtime warnings from meta-analysis
warnings.filterwarnings('ignore')

DISEASES = {
    "breast": {
        "file_pattern": "breast_cancer_incidence_true_all.json",
        "disease_label": "Breast Cancer",
        "context_template": "breast_cancer_{}_incidence",
        "output_file": "exposures_meta_analysis_final_combined.xlsx",
    },
    "ovarian": {
        "file_pattern": "ovarian_cancer_incidence_true_all.json",
        "disease_label": "Ovarian Cancer",
        "context_template": "ovarian_cancer_{}_incidence",
        "output_file": "exposures_meta_analysis_ovarian_combined.xlsx",
    },
    "uterine": {
        "file_pattern": "uterine_cancer_incidence_true_all.json",
        "disease_label": "Uterine Cancer",
        "context_template": "uterine_cancer_{}_incidence",
        "output_file": "exposures_meta_analysis_uterine_combined.xlsx",
    },
}

def run_export(disease_key, disease_config):
    results_dir = 'Cached_results'
    all_results = []

    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} not found.")
        return

    folders = os.listdir(results_dir)
    print(f"\n{'='*60}")
    print(f"  {disease_config['disease_label']}  —  {len(folders)} exposure folders")
    print(f"{'='*60}")

    blacklist = ['multivitamin']

    # Load verifications once
    verifications = {}
    if os.path.exists('data/verifications.json'):
        try:
            with open('data/verifications.json', 'r') as vf:
                verifications = json.load(vf)
        except:
            pass

    for folder in folders:
        if folder in blacklist:
            continue

        file_path = os.path.join(results_dir, folder, disease_config['file_pattern'])
        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            studies = data.get('studies', [])
            if not studies:
                continue

            # Application of verifications (matches logic in app.py)
            canonical_exp = meta_analysis.get_canonical_name(folder)
            context_key = disease_config['context_template'].format(canonical_exp).lower().replace(" ", "_")

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

            # ── Use all available exposure quantifications ──
            # (No filtering by exposure_measurement_type)

            if len(df) == 0:
                continue

            # Numeric conversion
            for col in ['Effect Size', 'Lower CI', 'Upper CI', 'Cases', 'Sample Size', 'Estimated Cases']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.strip(), errors='coerce')

            # Filter Cases >= 50 (standardised)
            cases_col = df['Cases'].fillna(df.get('Estimated Cases', np.nan)) if 'Cases' in df.columns else df.get('Estimated Cases', np.nan)
            df_valid = df[
                (df['Effect Size'] > 0) &
                (df['Lower CI'] > 0) &
                (df['Upper CI'] > 0) &
                (cases_col >= 50)
            ].copy()

            if len(df_valid) == 0:
                continue

            # Perform meta-analysis via shared library
            res_dict = meta_analysis.perform_meta_analysis(df_valid, disease_config['disease_label'], folder)
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
            print(f"  Error on {folder}: {e}")
            continue

    if not all_results:
        print(f"  No results for {disease_config['disease_label']}.")
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
    output_file = os.path.join('Plot', disease_config['output_file'])
    export_df.to_excel(output_file, index=False)
    print(f"  OK Exported {len(export_df)} exposures -> {output_file}")


def main():
    for key, config in DISEASES.items():
        run_export(key, config)
    print("\nDone.")


if __name__ == '__main__':
    main()
