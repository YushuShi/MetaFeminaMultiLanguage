
import export_exposures_excel
import os
import sys

# Monkey patch the output file name
export_exposures_excel.main()

# Wait, I should just modify the script or run it with an override.
# The script has output_file = 'exposures_meta_analysis_final.xlsx' hardcoded at line 144.

with open('export_exposures_excel.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_content = content.replace("'exposures_meta_analysis_final.xlsx'", "'exposures_meta_analysis_standardized.xlsx'")

with open('export_exposures_refreshed.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Created export_exposures_refreshed.py with new output filename.")
