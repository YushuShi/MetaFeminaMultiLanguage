import json
import os

def check():
    exposures_path = 'static/exposures.json'
    if not os.path.exists(exposures_path):
        print(f"Could not find {exposures_path}")
        return

    with open(exposures_path, 'r') as f:
        exposures = json.load(f)
    
    CACHE_DIR = 'Cached_results'
    disease = 'Breast cancer'
    outcome = 'Incidence'
    exclude_meta = True
    use_downstream = True
    
    safe_analysis = f"{disease}_{outcome}_{exclude_meta}_all".lower().replace(" ", "_")
    
    missing = []
    found = []
    
    for exposure in exposures:
        safe_exposure = exposure.lower().replace(" ", "_")
        cache_path = os.path.join(CACHE_DIR, safe_exposure, f"{safe_analysis}.json")
        
        if os.path.exists(cache_path):
            found.append(exposure)
        else:
            missing.append(exposure)
            
    print(f"Total exposures: {len(exposures)}")
    print(f"Found in cache: {len(found)}")
    print(f"Missing from cache: {len(missing)}")
    
    if missing:
        print("\nMissing exposures:")
        for m in missing:
            print(f"  - {m}")

if __name__ == '__main__':
    check()
