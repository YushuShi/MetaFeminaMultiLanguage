import pandas as pd
import os

def main():
    file = 'exposures_meta_analysis_breast_combined.xlsx'
    if not os.path.exists(file):
        print(f"File {file} not found.")
        return
        
    try:
        df = pd.read_excel(file)
        print("Excel File Loaded:")
        print(f"Shape: {df.shape}")
        print("Columns:", df.columns.tolist())
        print("First 5 rows:")
        print(df.head().to_string())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
