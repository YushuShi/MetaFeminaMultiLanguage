import pandas as pd
import numpy as np

# Replicate the cleaning logic of PlotsPaper.R
raw = pd.read_excel('Plot/exposures_meta_analysis_breast_combined.xlsx')
raw.columns = [
  "Exposure", "n_studies", "pooled_es_num",
  "ci_low", "ci_high",
  "pi_low", "pi_high",
  "I2", "eggers_p",
  "Total_N", "N_cases"
]

# sig and direction
raw['sig'] = np.where((raw['ci_high'] < 1) | (raw['ci_low'] > 1), "Significant", "Not significant")
raw['direction'] = np.select(
    [raw['pooled_es_num'] < 1, raw['pooled_es_num'] > 1],
    ['Protective', 'Harmful'],
    default='Neutral'
)

# Read group map from PlotsPaper.R
# We will just parse group_map from the R file
import re
group_map = {}
with open('Plot/PlotsPaper.R', 'r', encoding='utf-8') as f:
    content = f.read()

# find group_map <- tribble( ... )
tribble_match = re.search(r'group_map <- tribble\(\s*~Exposure,\s*~Group,\s*(.*?)\s*\)', content, re.DOTALL)
if tribble_match:
    rows = tribble_match.group(1).split('\n')
    for row in rows:
        row = row.strip()
        if not row:
            continue
        # Format is "exposure", "Group",
        m = re.match(r'"([^"]+)",\s*"([^"]+)",?', row)
        if m:
            group_map[m.group(1)] = m.group(2)

print(f"Loaded {len(group_map)} mappings from PlotsPaper.R")

# Merge
raw['Group'] = raw['Exposure'].map(group_map).fillna('Other')

# Filter n_studies > 1
df_filtered = raw[raw['n_studies'] > 1]

# Let's print out all rows in the 'Metabolites & Amino Acids' group
print("\n--- Metabolites & Amino Acids exposures in excel: ---")
met_amino = df_filtered[df_filtered['Group'] == 'Metabolites & Amino Acids']
print(met_amino[['Exposure', 'n_studies', 'pooled_es_num', 'direction']])

print("\n--- All Protective exposures: ---")
print(df_filtered[df_filtered['direction'] == 'Protective']['Exposure'].tolist())

print("\n--- All Harmful exposures: ---")
print(df_filtered[df_filtered['direction'] == 'Harmful']['Exposure'].tolist())

print("\n--- All Neutral exposures: ---")
print(df_filtered[df_filtered['direction'] == 'Neutral']['Exposure'].tolist())
