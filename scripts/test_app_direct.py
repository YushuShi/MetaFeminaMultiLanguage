import requests
import time
import threading
import os

# We don't want to start the whole flask app in another thread because it's complex,
# but we can import it and call the functions directly.

import app as flask_app
import meta_analysis

def test_app_logic():
    print("Testing app logic directly...")
    disease = "Breast Cancer"
    exposure = "Mediterranean diet"
    outcome = "Incidence"
    exclude_meta = False
    
    try:
        # Call the underlying function used by app.py
        print(f"Calling meta_analysis.get_analysis_data for {exposure}...")
        result = meta_analysis.get_analysis_data(disease, exposure, outcome=outcome, exclude_meta=exclude_meta, use_downstream=True)
        
        if "error" in result:
            print(f"Result contains error: {result['error']}")
        else:
            print(f"Success! Found {len(result.get('studies', []))} studies.")
            
    except Exception as e:
        print(f"Direct call failed: {e}")

if __name__ == "__main__":
    test_app_logic()
