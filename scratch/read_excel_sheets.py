import pandas as pd
import os

def main():
    files = {
        "Breast Cancer": "exposures_meta_analysis_final_combined.xlsx",
        "Ovarian Cancer": "exposures_meta_analysis_ovarian_combined.xlsx",
        "Uterine Cancer": "exposures_meta_analysis_uterine_combined.xlsx"
    }
    
    print("--- Checking Excel Sheets for Chocolate ---")
    for cancer, filename in files.items():
        if os.path.exists(filename):
            try:
                df = pd.read_excel(filename)
                match = df[df['Exposure'].astype(str).str.lower() == 'chocolate']
                if not match.empty:
                    print(f"\n{cancer} ({filename}): Found Chocolate!")
                    print(match.to_string(index=False))
                else:
                    print(f"\n{cancer} ({filename}): Chocolate NOT listed (0 relevant studies, as expected).")
            except Exception as e:
                print(f"Error reading {filename}: {e}")
        else:
            print(f"File {filename} not found.")

if __name__ == "__main__":
    main()
