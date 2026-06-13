"""
warm_synonyms_cache.py

Runs get_equivalent_terms for every known exposure so that all synonyms
are cached in synonyms_cache.json before the app processes them at runtime.

Usage:
    python warm_synonyms_cache.py
"""

import json
import os
import sys

# Ensure we can import meta_analysis from the parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import meta_analysis

# All exposures to pre-cache.
# These come from the current synonyms_cache.json + Cached_results subdirectories.
EXPOSURES = [
    "soy",
    "vitamin a",
    "zinc",
    "acai",
    "vitamin d",
    "carnitine",
    "melatonin",
    "5-htp",
    "copper",
    "turmeric",
    "tea",
    "coffee",
    "alcohol",
    "red meat",
    "processed meat",
    "multivitamin",
    "mineral supplements",
    "dairy",
    "eggs",
    "calcium",
    "vitamin c",
    "vitamin e",
    "vitamin b12",
    "vitamin b1",
    "folate",
    "omega-3",
    "fish oil",
    "selenium",
    "magnesium",
    "iron",
    "iodine",
    "fiber",
    "whole grains",
    "green tea",
    "black tea",
    "cruciferous vegetables",
    "broccoli",
    "garlic",
    "resveratrol",
    "lycopene",
    "beta-carotene",
    "lignans",
    "phytoestrogens",
    "isoflavones",
    "genistein",
    "daidzein",
    "coenzyme q10",
    "quercetin",
    "flaxseed",
    "olive oil",
    "mediterranean diet",
    "physical activity",
    "fermented foods",
    "skyr",
    "hemp seeds",
    "kefir",
    "legumes",
    "chia seeds",
    "oats",
    "flax",
]

def main():
    print("=" * 60)
    print("Synonym Cache Warmer")
    print("=" * 60)

    # Load current cache to show what's already in it
    cache_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'synonyms_cache.json')
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            current_cache = json.load(f)
        print(f"Existing cache entries: {list(current_cache.keys())}\n")
    else:
        current_cache = {}
        print("No existing cache found.\n")

    results = {}
    errors = []

    for exposure in EXPOSURES:
        key = exposure.lower()
        
        # Skip if already in cache (case-insensitive lookup)
        cached_val = None
        for k, v in current_cache.items():
            if k.lower().strip() == key:
                cached_val = v
                break

        if cached_val is not None:
            print(f"[CACHED] {exposure}")
            results[exposure] = cached_val
            continue

        # Fetch synonyms (will call LLM and save to cache)
        print(f"[FETCHING] {exposure} ...")
        try:
            synonyms = meta_analysis.get_equivalent_terms(exposure)
            results[exposure] = synonyms
            
            # Format display string for both dict and string
            display_str = str(synonyms)
            print(f"  -> {display_str[:80]}{'...' if len(display_str) > 80 else ''}")
        except Exception as e:
            print(f"  [ERROR] {e}")
            errors.append((exposure, str(e)))

    print("\n" + "=" * 60)
    print(f"Done. {len(results)} exposures processed, {len(errors)} errors.")
    if errors:
        print("Errors:")
        for exp, err in errors:
            print(f"  {exp}: {err}")

    # Print final cache contents
    print("\nFinal cache contents:")
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            final_cache = json.load(f)
        for k, v in final_cache.items():
            # Handle both string and dict status
            if isinstance(v, dict):
                is_empty = not (v.get("core", "").strip() or v.get("downstream", "").strip())
            else:
                is_empty = not str(v).strip()
            
            status = "EMPTY" if is_empty else "OK"
            print(f"  [{status}] {k}")
    print("=" * 60)

if __name__ == "__main__":
    main()
