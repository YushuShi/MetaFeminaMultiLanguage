import os
import sys
import json
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meta_analysis

# PMIDs in old cache but NOT in new cache
missing_pmids = [
    "19828509", "28114909", "11008902", "22760085", "25915188", 
    "30796113", "24155133", "33183968", "34482608", "26633163", 
    "22497978", "36918842", "18400722", "17063275", "30049821", "36738657"
]

print("Fetching details from PubMed for missing PMIDs...")
articles = meta_analysis.fetch_details(missing_pmids)
print(f"Fetched {len(articles)} articles.")

# Get synonyms list
exposure_keyword = "Mediterranean diet"
disease_keyword = "Breast cancer"
outcome_keyword = "Incidence"
use_downstream = True

syn_dict = meta_analysis.get_equivalent_terms(exposure_keyword)
all_terms_str = ", ".join(filter(None, [syn_dict.get("core", ""), syn_dict.get("downstream", "")]))
synonyms = [s.strip().lower() for s in all_terms_str.split(',')] if all_terms_str else []
synonyms.append(exposure_keyword.lower())
exp_syns = list(set([s for s in synonyms if len(s) > 2]))

skip_reasons = {}

for article in articles:
    medline = article['MedlineCitation']
    pmid = str(medline.get('PMID', ''))
    article_data = medline['Article']
    title = str(article_data.get('ArticleTitle', 'No Title'))
    abstract_list = article_data.get('Abstract', {}).get('AbstractText', [])
    abstract = " ".join(abstract_list) if isinstance(abstract_list, list) else str(abstract_list)
    title_lower = title.lower()
    all_text = (abstract + " " + title).lower()
    
    # Run filter checks step-by-step
    relevance = meta_analysis.is_disease_relevant(all_text, disease_keyword)
    if not relevance:
        skip_reasons[pmid] = "disease relevance (not relevant to breast cancer)"
        continue
        
    if patient_phrase_in_title := meta_analysis.patient_phrase_in_title(title_lower, disease_keyword):
        skip_reasons[pmid] = "outcome filter (already-diagnosed patients/survivors in title)"
        continue
        
    survival_keywords = ["mortality", "survival", "prognosis", "prognostic", "death"]
    if any(kw in title_lower for kw in survival_keywords):
        safe_incidence_terms = ["risk", "incidence", "development", "etiology", "prevention"]
        if not any(term in title_lower for term in safe_incidence_terms):
            skip_reasons[pmid] = "outcome filter (survival/mortality keywords in title without incidence keywords)"
            continue
            
    # Meta-analysis/Review check
    pub_types = [pt.strip().lower() for pt in article_data.get('PublicationTypeList', [])]
    if (meta_analysis.re.search(r'meta[\s-]?analysis', title_lower) or "systematic review" in title_lower) and pmid != "28260236":
        skip_reasons[pmid] = "publication type (systematic review or meta-analysis in title)"
        continue
        
    strong_primary_types = ['clinical trial', 'comparative study', 'multicenter study', 'observational study', 'randomized controlled trial']
    is_strong_primary = any(pt in strong_primary_types for pt in pub_types)
    if any(pt in ['meta-analysis', 'systematic review', 'review'] for pt in pub_types) and pmid != "28260236":
        if not is_strong_primary:
            skip_reasons[pmid] = "publication type (classified as review/meta-analysis/systematic review without primary tags)"
            continue
            
    if meta_analysis.has_other_disease_conflict(title_lower, disease_keyword):
        skip_reasons[pmid] = "disease conflict (mentions other cancers/diseases in title)"
        continue
        
    animal_keywords = ["mice", "mouse", "rat", "murine", "in vitro", "cell line", "in-vitro", "xenograft", "rat model"]
    if any(kw in title_lower for kw in animal_keywords):
        skip_reasons[pmid] = "animal/in-vitro keyword in title"
        continue
        
    if meta_analysis.re.search(r'\breview\b', title_lower) and not meta_analysis.re.search(r'\b(systematic|scoping|cochrane)\b', title_lower):
        is_cohort = any(ck in all_text for ck in ["cohort", "prospective", "randomized", "randomised"])
        if not is_cohort:
            skip_reasons[pmid] = "narrative review check (mentions review in title and not a cohort/prospective study)"
            continue
            
    # Exposure keyword gate
    gate_syns = [t for t in exp_syns if len(t) >= 4]
    if gate_syns:
        if not any(t in all_text for t in gate_syns):
            skip_reasons[pmid] = f"exposure keyword gate (does not mention any of: {gate_syns})"
            continue
            
    # If not skipped, check if LLM returned null or skipped
    skip_reasons[pmid] = "passed pre-filter (maybe skipped by LLM extraction or not returned by PubMed search)"

for pmid, reason in skip_reasons.items():
    print(f"PMID {pmid}: skipped due to: {reason}")
