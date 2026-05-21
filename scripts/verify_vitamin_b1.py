import json
import os

def verify():
    print("Verifying Vitamin B1/Thiamin consolidation...")
    
    # 1. Check exposures.json
    with open('static/exposures.json', 'r') as f:
        exposures = json.load(f)
        
    if "Thiamin" in exposures:
        print("FAIL: 'Thiamin' still in exposures.json")
        return False
    if "Vitamin B1 (Thiamin)" in exposures:
        print("FAIL: 'Vitamin B1 (Thiamin)' still in exposures.json")
        return False
    if "Vitamin B1" not in exposures:
        print("FAIL: 'Vitamin B1' not in exposures.json")
        return False
        
    # 2. Check synonyms_cache.json
    with open('data/synonyms_cache.json', 'r') as f:
        cache = json.load(f)
        
    if "thiamin" in cache:
        print("FAIL: 'thiamin' key still in synonyms_cache.json")
        return False
    if "vitamin b1 (thiamin)" in cache:
        print("FAIL: 'vitamin b1 (thiamin)' key still in synonyms_cache.json")
        return False
    if "vitamin b1" not in cache:
        print("FAIL: 'vitamin b1' key not in synonyms_cache.json")
        return False
        
    core = cache["vitamin b1"].get("core", "")
    if "Thiamin" not in core:
        print(f"FAIL: 'Thiamin' not in vitamin b1 core synonyms ({core})")
        return False
        
    print("SUCCESS: Vitamin B1/Thiamin consolidation verified.")
    return True

if __name__ == "__main__":
    if verify():
        exit(0)
    else:
        exit(1)
