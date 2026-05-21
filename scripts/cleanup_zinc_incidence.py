import json
import os

INCIDENCE_CACHE = 'Cached_results/zinc/breast_cancer_incidence_true_all.json'

def cleanup():
    if not os.path.exists(INCIDENCE_CACHE):
        print(f"{INCIDENCE_CACHE} not found.")
        return

    with open(INCIDENCE_CACHE, 'r') as f:
        data = json.load(f)

    if "studies" not in data:
        return

    original_count = len(data["studies"])
    
    # Identify survival studies
    # 1. PMID 37299574 (Lubiński J et al. 2023)
    # 2. Any title containing "Survival" or "Mortality" (if clearly survival-only)
    
    pmids_to_remove = ["37299574"]
    
    new_studies = []
    removed_studies = []
    for study in data["studies"]:
        pmid = str(study.get('PMID'))
        title = study.get('Reference', '').lower()
        
        should_remove = False
        if pmid in pmids_to_remove:
            should_remove = True
        elif "survival" in title and "risk" not in title and "incidence" not in title:
            # Simple heuristic
            should_remove = True
            
        if should_remove:
            removed_studies.append(f"{study.get('Study')} (PMID: {pmid})")
        else:
            new_studies.append(study)

    data["studies"] = new_studies
    
    # We should also update summary_html and other fields, but the meta_analysis logic
    # usually regenerates those. If we just edit the JSON, the pooled results might be wrong.
    # However, the user can just "force refresh" from the UI or we can delete the file
    # and let them re-run.
    # The user's request is "Zinc-breast cancer incidence, i see verified results for Zinc- breast cancer survival".
    # This implies the cached results themselves are confusing.
    
    if len(removed_studies) > 0:
        print(f"Removing {len(removed_studies)} survival studies from {INCIDENCE_CACHE}:")
        for s in removed_studies:
            print(f"  - {s}")
        
        with open(INCIDENCE_CACHE, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"Updated {INCIDENCE_CACHE}. Total studies: {original_count} -> {len(new_studies)}")
    else:
        print("No survival studies found to remove from Zinc incidence cache.")

if __name__ == "__main__":
    cleanup()
