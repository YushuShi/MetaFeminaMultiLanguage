import sys
import os
from Bio import Entrez

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meta_analysis

Entrez.email = "your_email@example.com"

not_in_search = ["19828509", "34482608", "22497978", "36918842", "18400722", "36738657"]

for pmid in not_in_search:
    print(f"\n--- Analyzing PMID {pmid} ---")
    # Fetch title/abstract/pubtypes
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
        
        print(f"Title: {title}")
        print(f"Pub Types: {pub_types}")
        
        # Test individual filters
        # 1. Disease terms
        disease_alias = meta_analysis.get_disease_alias("Breast cancer")
        disease_query = disease_alias["query"]
        print(f"Matches breast cancer query: {'Yes' if ('breast' in title.lower() or 'breast' in abstract.lower()) else 'No'}")
        
        # 2. Exposure terms
        exposure = "Mediterranean diet"
        syn_dict = meta_analysis.get_equivalent_terms(exposure)
        all_terms_str = ", ".join(filter(None, [syn_dict.get("core", ""), syn_dict.get("downstream", "")]))
        terms = [exposure] + [s.strip() for s in all_terms_str.split(',') if s.strip()]
        unique_terms = list(set([t.lower() for t in terms]))
        has_exp = any(t in (title + " " + abstract).lower() for t in unique_terms)
        print(f"Matches exposure synonyms in title/abstract: {'Yes' if has_exp else 'No'}")
        if not has_exp:
            print("  Synonyms checked:", unique_terms)
            print("  Actual text mentions of 'mediterranean':", [w for w in (title + " " + abstract).split() if 'mediter' in w.lower()])

        # 3. Outcome terms
        outcome_terms = ["incidence", "risk", "development", "associated with", "odds ratio"]
        has_outcome = any(o in (title + " " + abstract).lower() for o in outcome_terms)
        print(f"Matches outcome terms in title/abstract: {'Yes' if has_outcome else 'No'}")
        
        # 4. Exclusions
        is_meta = any(pt in ['meta-analysis', 'systematic review'] for pt in pub_types) or "meta-analysis" in title.lower() or "systematic review" in title.lower()
        print(f"Is Meta-analysis/Systematic Review: {'Yes' if is_meta else 'No'}")
        
        has_animal = any(kw in title.lower() for kw in ["mice", "mouse", "rat", "murine", "in vitro"])
        print(f"Has animal terms in Title: {'Yes' if has_animal else 'No'}")

        has_snp = any(kw in title.lower() for kw in ["snp", "polymorphism", "polymorphisms", "variant", "variants"])
        print(f"Has genetic exclusion terms in Title: {'Yes' if has_snp else 'No'}")

        has_survivor = any(phrase in title.lower() for phrase in disease_alias["patient_phrases"])
        print(f"Has survivor/patient exclusion terms in Title: {'Yes' if has_survivor else 'No'}")

    except Exception as e:
        print(f"Failed: {e}")
