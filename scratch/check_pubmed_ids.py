import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meta_analysis

missing_pmids = [
    "19828509", "28114909", "11008902", "22760085", "25915188", 
    "30796113", "24155133", "33183968", "34482608", "26633163", 
    "22497978", "36918842", "18400722", "17063275", "30049821", "36738657"
]

print("Running PubMed search...")
search_ids = meta_analysis.search_pubmed(
    disease="Breast cancer",
    exposure="Mediterranean diet",
    outcome="Incidence",
    exclude_meta=True,
    max_results=5000
)

print(f"Total PMIDs returned by search: {len(search_ids)}")

in_search = [pmid for pmid in missing_pmids if pmid in search_ids]
not_in_search = [pmid for pmid in missing_pmids if pmid not in search_ids]

print(f"PMIDs in search results ({len(in_search)}): {in_search}")
print(f"PMIDs NOT in search results ({len(not_in_search)}): {not_in_search}")
