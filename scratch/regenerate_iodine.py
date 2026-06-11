import os
import sys
from datetime import datetime

# Reconfigure standard output streams to use UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add root folder to path so we can import meta_analysis and app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meta_analysis
import app

def regenerate():
    diseases = ["Breast cancer", "Ovarian cancer", "Uterine cancer"]
    exposure = "iodine"
    outcome = "Incidence"
    exclude_meta = True
    use_downstream = True
    model = "openai.gpt-4o"
    
    print("Starting regeneration of iodine caches...")
    
    for disease in diseases:
        print(f"\n==================================================")
        print(f"Regenerating for: {disease} vs {exposure}")
        print(f"==================================================")
        
        canonical_exposure = meta_analysis.get_canonical_name(exposure)
        
        # Call meta-analysis engine
        result = meta_analysis.get_analysis_data(
            disease=disease,
            exposure=canonical_exposure,
            outcome=outcome,
            exclude_meta=exclude_meta,
            use_downstream=use_downstream,
            model=model
        )
        
        # Check if empty/error
        is_empty = result.get("error") == "No relevant evidence was identified in the reviewed sources."
        if "error" not in result or is_empty:
            result['last_run'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            target_cache_path = app.get_cache_path(
                disease=disease,
                exposure=exposure,
                outcome=outcome,
                exclude_meta=exclude_meta,
                use_downstream=use_downstream,
                model=model
            )
            app.save_json(target_cache_path, result)
            print(f"Successfully saved refreshed result cache to: {target_cache_path}")
            if "studies" in result:
                print(f"Number of studies included: {len(result['studies'])}")
                for s in result['studies']:
                    try:
                        print(f"  - {s.get('Study')}: {s.get('Reference')[:60]}...")
                    except Exception:
                        print(f"  - Study PMID: {s.get('PMID')}")
            else:
                print("No studies extracted.")
        else:
            print(f"Analysis returned an error, not caching: {result.get('error')}")

if __name__ == "__main__":
    regenerate()
