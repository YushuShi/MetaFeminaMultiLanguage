import sys
import os
from Bio import Entrez

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meta_analysis

Entrez.email = "your_email@example.com"

passed_pre_filter = ["28114909", "11008902", "22760085", "25915188", "30796113", "24155133", "26633163", "17063275", "36918842"]

print("Analyzing abstracts of passed studies:")
for pmid in passed_pre_filter:
    try:
        handle = Entrez.efetch(db="pubmed", id=pmid, retmode="xml")
        records = Entrez.read(handle)
        handle.close()
        
        article = records['PubmedArticle'][0]
        medline = article['MedlineCitation']
        article_data = medline['Article']
        title = str(article_data.get('ArticleTitle', ''))
        abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
        abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
        pub_types = [pt.strip().lower() for pt in article_data.get('PublicationTypeList', [])]
        
        print(f"\n--- PMID {pmid} ---")
        print(f"Title: {title}")
        print(f"Pub Types: {pub_types}")
        print("Abstract Snippet:")
        # Look for numbers/intervals or keywords in abstract
        print(abstract[:600] + "...")
    except Exception as e:
        print(f"Failed for PMID {pmid}: {e}")
