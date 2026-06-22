import os
import sys
import json
from dotenv import load_dotenv
import openai

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meta_analysis

def main():
    load_dotenv('mykey.env')
    client = openai.OpenAI(
        api_key=os.environ['OPENAI_API_KEY'],
        base_url=os.environ.get('OPENAI_BASE_URL')
    )
    
    title = "Chocolate consumption and risk of ovarian cancer."
    abstract = "In a prospective study of 40,000 women, we evaluated the association between chocolate intake and ovarian cancer risk. High chocolate consumption was not associated with ovarian cancer risk (HR 1.05, 95% CI 0.85-1.30)."
    exposure = "chocolate"
    disease = "Ovarian cancer"
    
    print("--- Testing screen_article_relevance_llm ---")
    try:
        res = meta_analysis.screen_article_relevance_llm(
            client=client,
            gemini_client=None,
            abstract=abstract,
            title=title,
            exposure=exposure
        )
        print("Screening result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n--- Testing extract_info_llm ---")
    try:
        res = meta_analysis.extract_info_llm(
            client=client,
            abstract=abstract,
            title=title,
            disease=disease,
            exposure=exposure,
            outcome="Incidence"
        )
        print("Extraction result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
