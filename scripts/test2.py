import sys
import os
import json
from Bio import Entrez
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
import meta_analysis

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mykey.env'))
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))

Entrez.email = 'test@example.com'
r = Entrez.read(Entrez.efetch(db='pubmed', id='34071317', retmode='xml'))
article = r['PubmedArticle'][0]
medline = article['MedlineCitation']
article_data = medline['Article']

title = article_data.get('ArticleTitle', '')
abs_list = article_data.get('Abstract', {}).get('AbstractText', [])
abstract = ' '.join(abs_list) if isinstance(abs_list, list) else str(abs_list)

print("Running raw LLM extraction...")
raw = meta_analysis.extract_info_llm(client, abstract, title, "Breast Cancer", "folic acid", "Incidence")
print(json.dumps(raw, indent=2))
flat = meta_analysis.flatten_json(raw)
print("Flattened:", json.dumps(flat, indent=2))
