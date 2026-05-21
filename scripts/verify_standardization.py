import json
import os

def verify_all():
    print("Verifying broader bracketed exposure standardization...")
    
    # 1. Check exposures.json
    with open('static/exposures.json', 'r') as f:
        exposures = json.load(f)
        
    bracketed = [e for e in exposures if '(' in e]
    if bracketed:
        print(f"FAIL: Still found exposures with brackets: {bracketed}")
        return False
        
    expected_gone = ["Riboflavin", "Niacin", "Pantothenic acid", "Biotin"]
    for e in expected_gone:
        if e in exposures:
            print(f"FAIL: '{e}' should have been removed (use Vitamin B#)")
            return False
            
    # 2. Check synonyms_cache.json
    with open('data/synonyms_cache.json', 'r') as f:
        cache = json.load(f)
        
    bracketed_keys = [k for k in cache.keys() if '(' in k]
    if bracketed_keys:
        print(f"FAIL: Still found cache keys with brackets: {bracketed_keys}")
        return False
        
    # Check specific consolidations
    checks = [
        ("vitamin b2", "riboflavin"),
        ("5-htp", "5-hydroxytryptophan"),
        ("beetroot", "beet juice"),
        ("cannabidiol", "cbd"),
        ("n-acetylcysteine", "nac")
    ]
    for key, syn in checks:
        if key not in cache:
            print(f"FAIL: '{key}' not in cache")
            return False
        core = str(cache[key].get("core", "")).lower()
        if syn not in core:
            print(f"FAIL: '{syn}' not in core synonyms of '{key}' ({core})")
            return False
            
    # Check HMB special case
    hmb_key = "beta-hydroxy-beta-methylbutyrate"
    if hmb_key not in cache:
        print(f"FAIL: '{hmb_key}' not in cache")
        return False
    core_hmb = str(cache[hmb_key].get("core", "")).lower()
    if "hmb" in core_hmb:
        print(f"FAIL: 'hmb' should NOT be a synonym for '{hmb_key}'")
        return False
        
    print("SUCCESS: Broader bracketed exposure standardization verified.")
    return True

if __name__ == "__main__":
    if verify_all():
        exit(0)
    else:
        exit(1)
