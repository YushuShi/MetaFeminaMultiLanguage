import json
import os

def check_cache():
    exposures_path = 'static/exposures.json'
    cache_dir = 'Cached_results'
    
    if not os.path.exists(exposures_path):
        print(f"Error: {exposures_path} not found.")
        return
        
    with open(exposures_path, 'r') as f:
        exposures = json.load(f)
        
    uncached = []
    for e in exposures:
        # App's safe naming logic: exposure.lower().replace(" ", "_")
        safe_name = e.lower().replace(" ", "_")
        exposure_path = os.path.join(cache_dir, safe_name)
        
        is_cached = False
        if os.path.exists(exposure_path):
            # Check if directory contains any .json files
            files = [f for f in os.listdir(exposure_path) if f.endswith('.json')]
            if files:
                is_cached = True
                
        if not is_cached:
            uncached.append(e)
            
    print(json.dumps(uncached, indent=2))

if __name__ == "__main__":
    check_cache()
