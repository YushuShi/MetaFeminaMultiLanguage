import json
import os

BASE_DIR = r"c:\Users\mde4023\Downloads\MetaFemina"
old_path = os.path.join(BASE_DIR, "Cached_results", "mediterranean_diet", "breast_cancer_incidence_true_all_old.json")
new_path = os.path.join(BASE_DIR, "Cached_results", "mediterranean_diet", "breast_cancer_incidence_true_all.json")

if os.path.exists(old_path):
    with open(old_path, 'r', encoding='utf-8') as f:
        old_data = json.load(f)
else:
    old_data = {}

if os.path.exists(new_path):
    with open(new_path, 'r', encoding='utf-8') as f:
        new_data = json.load(f)
else:
    new_data = {}

old_pmids = [s.get("PMID") for s in old_data.get("studies", [])]
new_pmids = [s.get("PMID") for s in new_data.get("studies", [])]

added_pmids = set(new_pmids) - set(old_pmids)
print(f"Number of new studies in new cache not in old cache: {len(added_pmids)}")
for pmid in added_pmids:
    study_name = next(s.get("Study") for s in new_data.get("studies", []) if s.get("PMID") == pmid)
    print(f" - PMID: {pmid} ({study_name})")
