import json
import os

def merge_caches(canonical_path, synonym_path):
    if not os.path.exists(canonical_path):
        print(f"Canonical path {canonical_path} not found.")
        return
    if not os.path.exists(synonym_path):
        print(f"Synonym path {synonym_path} not found.")
        return

    with open(canonical_path, 'r', encoding='utf-8') as f:
        canonical_data = json.load(f)
    with open(synonym_path, 'r', encoding='utf-8') as f:
        synonym_data = json.load(f)

    canonical_studies = canonical_data.get('studies', [])
    synonym_studies = synonym_data.get('studies', [])

    # Map existing PMIDs in canonical
    canonical_pmids = {str(s.get('PMID')) for s in canonical_studies if s.get('PMID')}
    
    merged_count = 0
    for s in synonym_studies:
        pmid = str(s.get('PMID'))
        if pmid and pmid not in canonical_pmids:
            # Check for "in vitro" in title (to fix the older dhea run artifacts)
            title = str(s.get('Reference', '')).lower()
            if 'in vitro' in title or 'in-vitro' in title:
                print(f"Skipping in-vitro study: {pmid}")
                continue
            
            canonical_studies.append(s)
            canonical_pmids.add(pmid)
            merged_count += 1
    
    print(f"Merged {merged_count} new studies into {canonical_path}")
    
    canonical_data['studies'] = canonical_studies
    # We should probably clear meta-analysis stats to force a re-calculate if used, 
    # but app.py re-calculates if studies change anyway.
    
    with open(canonical_path, 'w', encoding='utf-8') as f:
        json.dump(canonical_data, f, indent=4)

if __name__ == '__main__':
    c_path = r'c:\Users\mde4023\Downloads\MetaMamm\Cached_results\dehydroepiandrosterone\breast_cancer_incidence_true_all.json'
    s_path = r'c:\Users\mde4023\Downloads\MetaMamm\Cached_results\dhea\breast_cancer_incidence_true_all.json'
    merge_caches(c_path, s_path)
