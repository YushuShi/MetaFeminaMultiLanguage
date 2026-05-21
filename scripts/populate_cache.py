import os
import json
import time
from datetime import datetime

# Import 'app' modules to use its logic
import app

def main():
    exposures_path = 'static/exposures.json'
    if not os.path.exists(exposures_path):
        print(f"Could not find {exposures_path}")
        return

    with open(exposures_path, 'r') as f:
        exposures = json.load(f)
    
    disease = "Breast cancer"
    outcome = "Incidence"
    exclude_meta = True
    use_downstream = True

    print(f"Loaded {len(exposures)} exposures. Checking cache for Disease='{disease}', Outcome='{outcome}'...")
    
    missing_count = 0

    for i, exposure in enumerate(exposures):
        cache_path = app.get_cache_path(disease, exposure, outcome, exclude_meta, use_downstream)
        if os.path.exists(cache_path):
            continue
        missing_count += 1
        
    print(f"Found {missing_count} exposures missing from cache.")

    for i, exposure in enumerate(exposures):
        cache_path = app.get_cache_path(disease, exposure, outcome, exclude_meta, use_downstream)
        if os.path.exists(cache_path):
            print(f"[{i+1}/{len(exposures)}] SKIP (Cached): {exposure}")
            continue
        
        print(f"[{i+1}/{len(exposures)}] RUN: {exposure}")
        try:
            # We must be careful about context switching if meta_analysis changes cwd, but it shouldn't.
            result = app.meta_analysis.get_analysis_data(disease, exposure, outcome=outcome, exclude_meta=exclude_meta, use_downstream=use_downstream)
            
            is_empty = result.get("error") == "No relevant evidence was identified in the reviewed sources."
            if "error" not in result or is_empty:
                result['last_run'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                app.save_json(cache_path, result)
                print(f"  -> Saved successfully.")
            else:
                print(f"  -> Error returned: {result.get('error')}")
                
            time.sleep(2)  # Avoid rate limits for Gemini/PubMed
        except Exception as e:
            print(f"  -> Exception: {e}")

if __name__ == '__main__':
    main()
