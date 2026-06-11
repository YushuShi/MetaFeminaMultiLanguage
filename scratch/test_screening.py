import os
import sys

# Add root folder to path so we can import meta_analysis
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meta_analysis

def run_test():
    print("Testing LLM Screening Layer for Iodine...")
    
    # 1. Test case: Radioactive Iodine Study (Should be screened out -> is_directly_associated = False)
    rai_title = "Radioactive Iodine Therapy Did Not Significantly Increase the Incidence and Recurrence of Subsequent Breast Cancer."
    rai_abstract = (
        "To evaluate whether radioactive iodine (RAI) therapy increases the incidence and recurrence of "
        "subsequent breast cancer (BC) in patients with differentiated thyroid cancer. We performed a retrospective "
        "cohort study of 6150 patients. The primary exposure was high-dose RAI therapy (>120 mCi)."
    )
    
    # 2. Test case: Nutritional Iodine Study (Should be kept -> is_directly_associated = True)
    nut_title = "Blood Iodine as a Potential Marker of the Risk of Cancer in BRCA1 Carriers."
    nut_abstract = (
        "Blood iodine levels may be a marker of cancer risk. We measured serum iodine levels in BRCA1 mutation "
        "carriers and matched controls to see if dietary iodine intake or plasma iodine status is associated with "
        "breast and ovarian cancer risk."
    )
    
    print("\n--- Test 1: Radioactive Iodine (Should fail screening) ---")
    res1 = meta_analysis.screen_article_relevance_llm(
        client=meta_analysis.client,
        gemini_client=meta_analysis.gemini_client,
        abstract=rai_abstract,
        title=rai_title,
        exposure="iodine"
    )
    print(f"Result: {res1}")
    
    print("\n--- Test 2: Nutritional/Dietary Iodine (Should pass screening) ---")
    res2 = meta_analysis.screen_article_relevance_llm(
        client=meta_analysis.client,
        gemini_client=meta_analysis.gemini_client,
        abstract=nut_abstract,
        title=nut_title,
        exposure="iodine"
    )
    print(f"Result: {res2}")

if __name__ == "__main__":
    run_test()
