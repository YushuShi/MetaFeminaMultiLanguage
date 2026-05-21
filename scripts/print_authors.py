import json

with open('c:/Users/mde4023/Downloads/MetaMamm/Cached_results/lycopene/breast_cancer_incidence_true.json', 'r', encoding='utf-8') as f:
    data_selected = json.load(f)

items = data_selected.values() if isinstance(data_selected, dict) else data_selected

for idx, std in enumerate(items):
    if not isinstance(std, dict):
        continue
    pmid = std.get('PMID')
    year = std.get('Publication Year')
    authors = std.get('Authors')
    title = std.get('Title')
    print(f"{idx+1}. PMID: {pmid} | Year: {year} | Authors: {authors}")
