import json
import os
import re

CACHE_DIR = 'Cached_results'
VERIFICATIONS_FILE = 'data/verifications.json'

def migrate():
    # 1. Map PMIDs to contexts by scanning all cache files
    pmid_to_contexts = {}
    
    print("Scanning cache files...")
    for exposure_dir in os.listdir(CACHE_DIR):
        exposure_path = os.path.join(CACHE_DIR, exposure_dir)
        if not os.path.isdir(exposure_path):
            continue
            
        for filename in os.listdir(exposure_path):
            if not filename.endswith('.json'):
                continue
                
            file_path = os.path.join(exposure_path, filename)
            
            # Infer context from filename and directory
            # Filename format: disease_outcome_excludeMeta_downstream.json
            # Context key format: disease_exposure_outcome
            
            # Let's try to extract from the file content first if available
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # We need to find disease and outcome. Exposure is the directory name.
                # In many cases, these aren't explicitly in the JSON top-level,
                # but we can guess from the filename.
                
                match = re.match(r'^(.*)_(incidence|survival)_', filename)
                if match:
                    disease = match.group(1).replace('_', ' ')
                    outcome = match.group(2).capitalize()
                    exposure = exposure_dir.replace('_', ' ')
                    
                    context_key = f"{disease}_{exposure}_{outcome}".lower().replace(" ", "_")
                    
                    if "studies" in data:
                        for study in data["studies"]:
                            pmid = str(study.get('PMID'))
                            if pmid not in pmid_to_contexts:
                                pmid_to_contexts[pmid] = set()
                            pmid_to_contexts[pmid].add(context_key)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    # 2. Load verifications and migrate
    if not os.path.exists(VERIFICATIONS_FILE):
        print(f"{VERIFICATIONS_FILE} not found. Nothing to migrate.")
        return

    with open(VERIFICATIONS_FILE, 'r') as f:
        verifications = json.load(f)

    migrated_count = 0
    for pmid, v_info in verifications.items():
        if isinstance(v_info, int):
            # Very old legacy count only
            continue
            
        if "contexts" not in v_info:
            # This is a legacy entry!
            submissions = v_info.get("submissions", [])
            consensus = v_info.get("consensus_data")
            
            if not submissions and not consensus:
                continue
                
            # Create contexts dict
            v_info["contexts"] = {}
            
            # Where does this PMID belong?
            contexts = pmid_to_contexts.get(pmid, [])
            
            if not contexts:
                print(f"Warning: PMID {pmid} found in verifications but not in any cache file. Skipping migration for this entry.")
                # We'll leave it in the top-level so it's not lost, but it will still have the spillover problem
                # until it's found in a cache.
                continue
            
            for ctx in contexts:
                v_info["contexts"][ctx] = {
                    "submissions": submissions,
                    "consensus_data": consensus
                }
            
            # Clear legacy top-level data ONLY AFTER migrating to ALL identified contexts
            # Actually, to prevent spillover, we MUST clear them.
            v_info["submissions"] = []
            v_info["consensus_data"] = None
            migrated_count += 1
            print(f"Migrated PMID {pmid} to contexts: {', '.join(contexts)}")

    # 3. Save back
    with open(VERIFICATIONS_FILE, 'w') as f:
        json.dump(verifications, f, indent=4)
        
    print(f"Successfully migrated {migrated_count} legacy verification entries.")

if __name__ == "__main__":
    migrate()
