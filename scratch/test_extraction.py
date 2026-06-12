import os
import sys
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meta_analysis

def test_gemini():
    if not meta_analysis.gemini_client:
        print("Gemini client not initialized. Skipping Gemini test.")
        return
    
    title = "Dietary Folate Intake and Breast Cancer Risk"
    abstract = "We investigated the association between dietary folate intake and breast cancer risk. A food frequency questionnaire was administered to 989 women. The hazard ratio was 0.85 (95% CI 0.75-0.95). There were 120 breast cancer cases."
    disease = "Breast Cancer"
    exposure = "Folate"
    outcome = "Incidence"

    print("Running Gemini extraction...")
    result = meta_analysis.extract_info_gemini(
        meta_analysis.gemini_client,
        meta_analysis.gemini_model_name,
        abstract,
        title,
        disease,
        exposure,
        outcome
    )
    print("Gemini Result:")
    print(json.dumps(result, indent=2))

def test_openai():
    if not meta_analysis.client:
        print("OpenAI/Cornell client not initialized. Skipping OpenAI test.")
        return
    
    title = "Circulating Vitamin D Levels and Ovarian Cancer Risk"
    abstract = "We measured serum 25-hydroxyvitamin D concentration in blood samples of 500 women. The odds ratio for ovarian cancer was 0.70 (95% CI 0.50-0.98) comparing highest to lowest quartile of vitamin D. 50 cases were identified."
    disease = "Ovarian Cancer"
    exposure = "Vitamin D"
    outcome = "Incidence"

    print("Running OpenAI extraction...")
    result = meta_analysis.extract_info_llm(
        meta_analysis.client,
        abstract,
        title,
        disease,
        exposure,
        outcome
    )
    print("OpenAI Result:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_gemini()
    print("-" * 50)
    test_openai()
