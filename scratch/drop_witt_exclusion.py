import json
import os
import sys

# Ensure parent directory is in sys.path so we can import app and meta_analysis
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app

def main():
    verifications_file = 'data/verifications.json'
    
    with open(verifications_file, 'r', encoding='utf-8') as f:
        verifications = json.load(f)
        
    pmid = "19711189"
    context_key = "breast_cancer_fish_oil_incidence"
    
    if pmid in verifications:
        context_excl = verifications[pmid].get("context_exclusions", {})
        if context_key in context_excl:
            print(f"Current exclusion flag for {pmid} ({context_key}): {context_excl[context_key]}")
            context_excl[context_key] = 0
            print("Changed exclusion flag to 0.")
        else:
            print(f"Context key {context_key} not found in exclusions for PMID {pmid}.")
    else:
        print(f"PMID {pmid} not found in verifications.")
        
    with open(verifications_file, 'w', encoding='utf-8') as f:
        json.dump(verifications, f, indent=4)
    print(f"Saved {verifications_file}")
    
    # Run update cache
    print("Updating cache for Breast cancer, Fish oil, Incidence...")
    app.update_cache_from_verifications("Breast cancer", "Fish oil", "Incidence")
    
    # Also update omega-3 fatty acids since Witt et al. is in its cache too.
    # Wait, does the user want us to update omega-3 fatty acids?
    # The request says: "Witt et al. with fish oil breast cancer".
    # Let's check if Witt et al has an exclusion flag under omega-3 fatty acids in verifications.json.
    # We saw in the verifications.json view that 19711189 only has:
    # "context_exclusions": { "breast_cancer_fish_oil_incidence": 2 }
    # So there is no exclusion flag for omega-3 fatty acids. So we only need to update fish oil cache.
    # Let's run it!
    print("Verification and cache update completed successfully.")

if __name__ == "__main__":
    main()
