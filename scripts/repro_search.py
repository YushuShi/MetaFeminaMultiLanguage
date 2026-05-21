import os
from Bio import Entrez
import json
import re

# Mocking the environment
Entrez.email = "margauxdelporte@gmail.com"

def get_equivalent_terms(exposure):
    # From the current data/synonyms_cache.json
    if exposure.lower() == "mediterranean diet":
        return {"core": "meddiet, mediterranean-style diet", "downstream": ""}
    return {"core": "", "downstream": ""}

def search_pubmed_repro(disease, exposure, outcome="Incidence", exclude_meta=False, max_results=50):
    # Copying logic from meta_analysis.py
    outcome_terms = '(incidence OR risk OR development OR "associated with" OR "odds ratio")'
    syn_dict = get_equivalent_terms(exposure)
    all_terms_str = ", ".join(filter(None, [syn_dict.get("core", ""), syn_dict.get("downstream", "")]))
    if all_terms_str:
        terms = [exposure] + [s.strip() for s in all_terms_str.split(',') if s.strip()]
        unique_terms = []
        seen = set()
        for t in terms:
            if t.lower() not in seen:
                unique_terms.append(t)
                seen.add(t.lower())
        exposure_term = "(" + " OR ".join(unique_terms) + ")"
    else:
        exposure_term = exposure

    disease_term = disease
    if disease.lower().strip() == 'breast cancer':
        disease_term = '(Breast AND Cancer)'

    survivor_exclusion = ' NOT ("breast cancer survivors"[Title] OR "breast cancer patients"[Title])'
    animal_exclusion = ' NOT (mice[Title] OR mouse[Title] OR rat[Title] OR murine[Title] OR "in vitro"[Title])'
    negative_constraints = ' NOT "SNP"[Title]'

    query = f"({disease_term}[Title/Abstract] AND {exposure_term}[Title/Abstract] AND {outcome_terms}{survivor_exclusion}{animal_exclusion}{negative_constraints} AND (Journal Article[ptyp] OR \"Clinical Trial\"[ptyp]))"
    
    print(f"Full Query: {query}")
    
    date_windows = [("2019/01/01", "3000/12/31"), ("1900/01/01", "2018/12/31")]
    for mindate, maxdate in date_windows:
        try:
            print(f"Searching ({mindate[:4]}–{maxdate[:4]})...")
            handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, datetype="pdat", mindate=mindate, maxdate=maxdate)
            record = Entrez.read(handle)
            handle.close()
            print(f"  Success: {len(record['IdList'])} results.")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    search_pubmed_repro("breast cancer", "Mediterranean diet")
