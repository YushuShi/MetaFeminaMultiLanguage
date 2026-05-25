import os
import sys
import json
import time
from datetime import datetime
import warnings

# Add parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
import meta_analysis

# Suppress runtime warnings from meta-analysis
warnings.filterwarnings('ignore')

LOG_FILE = 'data/full_refresh_run.log'

def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")

def run_refresh():
    exposures_path = 'static/exposures.json'
    if not os.path.exists(exposures_path):
        log(f"Error: {exposures_path} not found.")
        return
        
    with open(exposures_path, 'r') as f:
        exposures = json.load(f)
        
    diseases = ["Uterine cancer", "Ovarian cancer"]
    outcome = "Incidence"
    exclude_meta = True
    use_downstream = True
    model = 'openai.gpt-4o'
    
    log(f"Starting full refresh for {len(exposures)} exposures and 2 diseases ({diseases}).")
    
    total_runs = len(exposures) * len(diseases)
    current_run = 0
    
    for exposure in exposures:
        for disease in diseases:
            current_run += 1
            log(f"[{current_run}/{total_runs}] REFRESH: {disease} vs {exposure}")
            
            try:
                # Call meta-analysis pipeline to fetch from PubMed and extract via LLM
                canonical_exposure = meta_analysis.get_canonical_name(exposure)
                result = meta_analysis.get_analysis_data(
                    disease, 
                    canonical_exposure, 
                    outcome=outcome, 
                    exclude_meta=exclude_meta, 
                    use_downstream=use_downstream, 
                    model=model
                )
                
                is_empty = result.get("error") == "No relevant evidence was identified in the reviewed sources."
                if "error" not in result or is_empty:
                    result['last_run'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    target_cache_path = app.get_cache_path(disease, exposure, outcome, exclude_meta, use_downstream, model)
                    app.save_json(target_cache_path, result)
                    log(f"  -> Saved fresh cache to {target_cache_path}")
                    
                    # Immediately apply verifications to overlay consensus/exclusions and regenerate plots
                    app.update_cache_from_verifications(disease, exposure, outcome)
                    log(f"  -> Applied verifications and regenerated plots.")
                else:
                    log(f"  -> Error returned: {result.get('error')}")
                
                # Check study count to determine sleep duration
                num_studies = len(result.get('studies', []))
                if num_studies > 0:
                    time.sleep(3.0)  # Sleep longer if we made LLM API calls
                else:
                    time.sleep(1.0)
                    
            except Exception as e:
                log(f"  -> Exception occurred: {e}")
                time.sleep(2.0)

    log("Full refresh run completed. Now running final Excel exports...")
    
    # Import and run rerun_and_export to generate the updated Excel sheets
    try:
        import scripts.rerun_and_export as rex
        for disease, label in [("Uterine cancer", "uterine"), ("Ovarian cancer", "ovarian")]:
            rex.export_disease_results(disease, label)
        log("Excel sheets exported successfully.")
    except Exception as e:
        log(f"Failed to export Excel sheets: {e}")
        
    log("All tasks finished successfully!")

if __name__ == '__main__':
    run_refresh()
