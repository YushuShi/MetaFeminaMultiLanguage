import os
import pandas as pd

def check_file(filename):
    if not os.path.exists(filename):
        print(f"Error: {filename} does not exist!")
        return
        
    try:
        # Since pandas read_excel failed earlier, let's try using openpyxl directly
        # or load via pandas if it works now.
        df = pd.read_excel(filename)
        print(f"File {filename}:")
        print(f"  Shape: {df.shape}")
        print(f"  Columns: {df.columns.tolist()}")
        print(f"  First 3 exposures: {df['Exposure'].head(3).tolist()}")
    except Exception as e:
        # Fallback to file size if engine fails
        size = os.path.getsize(filename)
        print(f"File {filename} exists. Size: {size} bytes. (Failed to parse: {e})")

def main():
    files = [
        'exposures_meta_analysis_uterine_combined.xlsx',
        'exposures_meta_analysis_uterine_FIXED.xlsx',
        'exposures_meta_analysis_ovarian_combined.xlsx',
        'exposures_meta_analysis_ovarian_FIXED.xlsx'
    ]
    
    for f in files:
        check_file(f)

if __name__ == '__main__':
    main()
