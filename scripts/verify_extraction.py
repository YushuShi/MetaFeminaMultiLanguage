
import os
import json
import pandas as pd
from meta_analysis import get_analysis_data

def test_extraction():
    print("Starting extraction test for Vitamin D...")
    # Using a small search to keep it fast
    result = get_analysis_data("Breast Cancer", "Vitamin D", outcome="Incidence", exclude_meta=True)
    
    if "error" in result:
        print(f"Error during extraction: {result['error']}")
        return

    studies = result.get("studies", [])
    print(f"Found {len(studies)} studies.")
    
    found_context = 0
    for study in studies[:10]: # Check first 10
        pmid = study.get("PMID")
        context = study.get("comparison_type")
        print(f"PMID: {pmid} | Context: {context}")
        if context and context != "-" and context != "N/A":
            found_context += 1
            
    print(f"\nStudies with valid context: {found_context}/10")
    
    # Check if key exists in all dictionaries
    all_have_key = all("comparison_type" in study for study in studies)
    print(f"All studies have 'comparison_type' key: {all_have_key}")

if __name__ == "__main__":
    test_extraction()
