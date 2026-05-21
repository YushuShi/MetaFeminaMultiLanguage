
import os
import json
from meta_analysis import get_results_interpretation

def test_interpretation():
    print("Testing get_results_interpretation...")
    result = get_results_interpretation(
        disease="Breast Cancer",
        exposure="Vitamin D",
        outcome="Incidence",
        n_studies=45,
        pooled_es=0.85,
        ci_low=0.72,
        ci_upp=0.99,
        i2=67.3,
        stat_interpretation="Statistically Significant (Decreased Risk/Odds)"
    )
    
    print(f"\n--- Interpretation ---")
    print(result)
    print(f"\n--- Checks ---")
    
    # Check for causal language
    causal_words = ["causes", "prevents", "leads to", "results in"]
    found_causal = [w for w in causal_words if w.lower() in result.lower()]
    if found_causal:
        print(f"WARNING: Found causal language: {found_causal}")
    else:
        print("PASS: No causal language detected")
    
    # Check length
    print(f"Length: {len(result)} chars")
    print(f"Non-empty: {'PASS' if len(result) > 20 else 'FAIL'}")

if __name__ == "__main__":
    test_interpretation()
