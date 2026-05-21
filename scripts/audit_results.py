import os
import json

def audit_results():
    exposures_path = 'static/exposures.json'
    cache_root = 'Cached_results'
    
    if not os.path.exists(exposures_path):
        print("Error: static/exposures.json not found")
        return
        
    with open(exposures_path, 'r') as f:
        exposures = json.load(f)
        
    outcomes = ["Incidence", "Survival", "Progression-Free Survival"]
    
    results_summary = {} # exposure -> set of outcomes found
    
    for exposure in exposures:
        results_summary[exposure] = set()
        safe_exposure = exposure.lower().replace(" ", "_").replace("/", "_")
        exposure_dir = os.path.join(cache_root, safe_exposure)
        
        if os.path.exists(exposure_dir):
            files = os.listdir(exposure_dir)
            for f in files:
                if not f.endswith(".json"): continue
                fname = f.lower()
                for outcome in outcomes:
                    if outcome.lower() in fname:
                        results_summary[exposure].add(outcome)
                        
    # Analysis
    missing_exposures = [e for e, o in results_summary.items() if not o]
    partially_filled = [e for e, o in results_summary.items() if o and len(o) < len(outcomes)]
    complete = [e for e, o in results_summary.items() if len(o) == len(outcomes)]
    
    print(f"Total defined exposures: {len(exposures)}")
    print(f"Exposures with NO results: {len(missing_exposures)}")
    print(f"Exposures with PARTIAL results: {len(partially_filled)}")
    print(f"Exposures with COMPLETE results: {len(complete)}")
    
    if complete:
        print("\n--- Complete Exposures (All 3 outcomes) ---")
        for e in complete:
            print(f"- {e}")
        print("\n--- Top 20 Missing Exposures ---")
        for e in missing_exposures[:20]:
            print(f"- {e}")
            
    if partially_filled:
        print("\n--- Partially Filled (Missing specific outcomes) ---")
        for e in partially_filled[:20]:
            missing = [o for o in outcomes if o not in results_summary[e]]
            print(f"- {e} (Missing: {', '.join(missing)})")

if __name__ == "__main__":
    audit_results()
