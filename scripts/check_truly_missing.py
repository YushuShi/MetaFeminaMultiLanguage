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
    
    no_folder = []
    empty_folder = []
    has_any_cache = []
    
    for exposure in exposures:
        safe_exposure = exposure.lower().replace(" ", "_")
        exposure_dir = os.path.join(CACHE_DIR, safe_exposure)
        
        if not os.path.exists(exposure_dir):
            no_folder.append(exposure)
        else:
            files = [f for f in os.listdir(exposure_dir) if f.endswith('.json')]
            if not files:
                empty_folder.append(exposure)
            else:
                has_any_cache.append(exposure)
            
    print(f"Total exposures: {len(exposures)}")
    print(f"Has some cache: {len(has_any_cache)}")
    print(f"No folder at all: {len(no_folder)}")
    print(f"Empty folder: {len(empty_folder)}")
    
    truly_missing = no_folder + empty_folder
    if truly_missing:
        print("\nTruly missing exposures (No JSON at all):")
        for m in truly_missing:
            print(f"  - {m}")

if __name__ == '__main__':
    check()
