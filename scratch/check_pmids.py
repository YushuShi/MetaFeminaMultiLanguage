import os
import sys
from dotenv import load_dotenv
import json
from Bio import Entrez
import openai

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meta_analysis

Entrez.email = "mde4023@cornell.edu"

def main():
    load_dotenv('mykey.env')
    
    disease = "Breast cancer"
    exposure = "Mediterranean diet"
    outcome = "Incidence"
    
    # These 5 PMIDs were returned by PubMed search but are not in the cached studies list
    found_pmids = ["26872903", "30049821", "37169990", "17063275", "22571994"]
    
    client = openai.OpenAI(
        api_key=os.environ['OPENAI_API_KEY'],
        base_url=os.environ.get('OPENAI_BASE_URL')
    )
    
    print("Fetching details for PMIDs from PubMed...")
    try:
        handle = Entrez.efetch(db="pubmed", id=found_pmids, retmode="xml")
        records = Entrez.read(handle)
        handle.close()
        articles = records.get('PubmedArticle', [])
    except Exception as e:
        print(f"Error fetching PubMed details: {e}")
        return

    print(f"Fetched {len(articles)} articles.")
    
    for article in articles:
        medline = article['MedlineCitation']
        pmid = str(medline.get('PMID', ''))
        article_data = medline['Article']
        
        title = article_data.get('ArticleTitle', 'No Title')
        if isinstance(title, list): title = " ".join([str(t) for t in title])
        title = str(title)
        
        abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
        abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
        
        print("\n" + "="*80)
        print(f"PMID: {pmid}")
        print(f"TITLE: {title}")
        
        print("\n--- Running screen_article_relevance_llm ---")
        try:
            screen_res = meta_analysis.screen_article_relevance_llm(
                client=client,
                gemini_client=None,
                abstract=abstract,
                title=title,
                exposure=exposure
            )
            print("Screening result:")
            print(json.dumps(screen_res, indent=2))
        except Exception as e:
            print(f"Screening error: {e}")
            
        print("\n--- Running extract_info_llm ---")
        try:
            extract_res = meta_analysis.extract_info_llm(
                client=client,
                abstract=abstract,
                title=title,
                disease=disease,
                exposure=exposure,
                outcome=outcome
            )
            print("Extraction result:")
            print(json.dumps(extract_res, indent=2))
        except Exception as e:
            print(f"Extraction error: {e}")

if __name__ == "__main__":
    main()
