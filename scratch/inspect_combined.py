import pandas as pd
import os

def inspect_file(path):
    print(f"\n==========================================")
    print(f"Inspecting file: {path}")
    print(f"==========================================")
    if not os.path.exists(path):
        print(f"File {path} does not exist!")
        return

    try:
        df = pd.read_excel(path)
        print(f"Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        print("\nAll exposures in file:")
        print(df.to_string(index=False))
        
        # Check for NaN values or any formatting issues
        nan_counts = df.isna().sum()
        if nan_counts.sum() > 0:
            print("\nWarning: Found NaN values:")
            print(nan_counts[nan_counts > 0])
    except Exception as e:
        print(f"Error reading file: {e}")

def main():
    files = [
        'Plot/exposures_meta_analysis_ovarian_combined.xlsx',
        'Plot/exposures_meta_analysis_uterine_combined.xlsx'
    ]
    for f in files:
        inspect_file(f)

if __name__ == '__main__':
    main()
