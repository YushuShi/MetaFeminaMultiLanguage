import os
from Bio import Entrez
import json

Entrez.email = "mde4023@cornell.edu"

def main():
    not_found_pmids = ["19828509", "28260236", "30968114", "37925868", "18400722", "30846706", "33256868", "36918842"]
    
    print("Fetching details for NOT FOUND PMIDs...")
    try:
        handle = Entrez.efetch(db="pubmed", id=not_found_pmids, retmode="xml")
        records = Entrez.read(handle)
        handle.close()
        articles = records.get('PubmedArticle', [])
    except Exception as e:
        print(f"Error fetching PubMed details: {e}")
        return

    for article in articles:
        medline = article['MedlineCitation']
        pmid = str(medline.get('PMID', ''))
        article_data = medline['Article']
        
        title = article_data.get('ArticleTitle', 'No Title')
        if isinstance(title, list): title = " ".join([str(t) for t in title])
        title = str(title)
        
        abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
        abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
        
        pub_types = article_data.get('PublicationTypeList', [])
        pub_types_list = [str(pt) for pt in pub_types]
        
        print("\n" + "="*80)
        print(f"PMID: {pmid}")
        print(f"TITLE: {title}")
        print(f"PUB TYPES: {pub_types_list}")
        
        # Check against search criteria:
        # 1. Mediterranean keywords
        med_keywords = ["mediterranean diet", "meddiet", "mediterranean-style diet", "traditional mediterranean diet", "mediterranean dietary pattern", "mds score", "p-mds", "alternate mediterranean diet"]
        all_text = (title + " " + abstract).lower()
        has_med = any(kw in all_text for kw in med_keywords)
        print(f"Has Mediterranean diet keywords in Title/Abstract: {has_med}")
        if not has_med:
            # Print what keywords are actually present
            print("  -> Does not contain any of the specific Mediterranean query keywords.")
            
        # 2. NOT keywords
        # - "breast cancer survivors"[Title] OR "breast cancer patients"[Title] OR "cancer survivors"[Title] OR "cancer patients"[Title]
        title_lower = title.lower()
        has_survivors = any(p in title_lower for p in ["breast cancer survivors", "breast cancer patients", "cancer survivors", "cancer patients"])
        print(f"Has survivor/patient exclusion keywords in Title: {has_survivors}")
        
        # - SNP/polymorphism in Title
        has_genetic = any(g in title_lower for g in ["snp", "polymorphism", "polymorphisms", "variant", "variants", "transferase", "genotype", "genotypes", "telomere length", "family history", "gene-diet", "gene-nutrient", "gene-supplement", "genotype-exposure", "genetic-nutrient"])
        print(f"Has genetic exclusion keywords in Title: {has_genetic}")
        
        # - Publication types
        is_review = "Meta-Analysis" in pub_types_list or "Systematic Review" in pub_types_list
        print(f"Is Meta-Analysis/Systematic Review: {is_review}")

if __name__ == "__main__":
    main()
