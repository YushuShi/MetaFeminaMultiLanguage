import pandas as pd
import numpy as np

# Replicate the cleaning logic of PlotsPaper.R
raw = pd.read_excel('Plot/exposures_meta_analysis_final_combined.xlsx')
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
import re
group_map = {}
with open('Plot/PlotsPaper.R', 'r', encoding='utf-8') as f:
    content = f.read()

tribble_match = re.search(r'group_map <- tribble\(\s*~Exposure,\s*~Group,\s*(.*?)\s*\)', content, re.DOTALL)
if tribble_match:
    rows = tribble_match.group(1).split('\n')
    for row in rows:
        row = row.strip()
        if not row:
            continue
        m = re.match(r'"([^"]+)",\s*"([^"]+)",?', row)
        if m:
            group_map[m.group(1)] = m.group(2)

raw['Group'] = raw['Exposure'].map(group_map).fillna('Other')

# group_order from PlotsPaper.R
group_order = [
  "Carotenoids",
  "Vitamins A, C, D, E, K",
  "B Vitamins",
  "Antioxidants",
  "Minerals & Trace Elements",
  "Polyphenols & Flavonoids",
  "Fruits & Vegetables",
  "Fermented Foods & Probiotics",
  "Fatty Acids & Lipids",
  "Phytoestrogens",
  "Herbal & Botanical",
  "Dietary Patterns",
  "Metabolites & Amino Acids",
  "Hormones & Endogenous"
]

# Filter n_studies > 1
df_filtered = raw[raw['n_studies'] > 1].copy()

# Set group categories and sort
df_filtered['Group'] = pd.Categorical(df_filtered['Group'], categories=group_order + ['Other'], ordered=True)

for direction in ["Protective", "Harmful"]:
    print(f"\n================= {direction} prepared data =================")
    df_dir = df_filtered[df_filtered['direction'] == direction].copy()
    df_dir = df_dir.sort_values(by=['Group', 'pooled_es_num'])
    print(df_dir[['Exposure', 'Group', 'n_studies', 'pooled_es_num', 'ci_low', 'ci_high']])
