import json
import os

def verify():
    print("Verifying Multivitamin/mineral Supplements split...")
    
    # 1. Check exposures.json
    with open('static/exposures.json', 'r') as f:
        exposures = json.load(f)
        
    combined = "Multivitamin/mineral Supplements"
    if combined in exposures:
        print(f"FAIL: '{combined}' still in exposures.json")
        return False
    if "Multivitamin" not in exposures:
        print("FAIL: 'Multivitamin' not in exposures.json")
        return False
    if "Mineral supplements" not in exposures:
        print("FAIL: 'Mineral supplements' not in exposures.json")
        return False
        
    # 2. Check synonyms_cache.json
    with open('data/synonyms_cache.json', 'r') as f:
        cache = json.load(f)
        
    if combined.lower() in cache:
        print(f"FAIL: '{combined.lower()}' still in synonyms_cache.json")
        return False
    if "multivitamin" not in cache:
        print("FAIL: 'multivitamin' not in synonyms_cache.json")
        return False
    if "mineral supplements" not in cache:
        print("FAIL: 'mineral supplements' not in synonyms_cache.json")
        return False
        
    print("SUCCESS: Multivitamin/mineral Supplements split verified.")
    return True

if __name__ == "__main__":
    if verify():
        exit(0)
    else:
        exit(1)
