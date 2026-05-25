import sys
import os
import json
from Bio import Entrez

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meta_analysis

Entrez.email = "your_email@example.com"
pmid = "36918842"

print(f"Fetching details for PMID {pmid}...")
articles = meta_analysis.fetch_details([pmid])
article = articles[0]

medline = article['MedlineCitation']
article_data = medline['Article']
title = str(article_data.get('ArticleTitle', ''))
abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)

print("Title:", title)
print("Abstract:", abstract)

# Let's run extraction using Gemini
print("\nRunning Gemini Extraction...")
res = meta_analysis.extract_info_gemini(
    meta_analysis.gemini_client,
    meta_analysis.gemini_model_name,
    abstract,
    title,
    disease="Breast cancer",
    exposure="Mediterranean diet",
    outcome="Incidence"
)
print("Gemini result:", json.dumps(res, indent=2))
