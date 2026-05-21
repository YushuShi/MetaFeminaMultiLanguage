import json

try:
    with open('c:/Users/mde4023/Downloads/MetaMamm/Cached_results/lycopene/breast_cancer_incidence_true.json', 'r', encoding='utf-8') as f:
        data_selected = json.load(f).get('studies', [])
except Exception as e:
    data_selected = []
    print("Error loading true.json:", e)

try:
    with open('c:/Users/mde4023/Downloads/MetaMamm/Cached_results/lycopene/breast_cancer_incidence_true_all.json', 'r', encoding='utf-8') as f:
        doc = json.load(f)
        data_all = doc.get('studies', []) if isinstance(doc, dict) else doc
except Exception as e:
    data_all = []
    print("Error loading true_all.json:", e)

print(f"Total selected studies in our JSON: {len(data_selected)}")

terms = ['Cui', 'Larsson', 'Pantavos', 'Zhang', 'Terry', 'Cho', 'Sesso', 'Horn-Ross', 'Bakker', 'Eliassen', 'Peng', 'Wang', 'Toniolo', 'Dorgan', 'Dorjgochoo', 'Hultén', 'Sato', 'Sisti', 'Pouchieu', 'Epplein', 'Masala', 'Suzuki', 'Boggs', 'Farvid', 'Dunneram']

pmids_selected = set(str(d.get('PMID', '')) for d in data_selected if type(d) is dict)

found_in_all = {term: [] for term in terms}
found_in_selected = {term: [] for term in terms}

for std in data_all:
    if type(std) is dict:
        s_str = str(std).lower()
        pmid = str(std.get('PMID', ''))
        title = std.get('Title', '') or std.get('Reference', '')
        authors = std.get('Authors', '')
        selected = pmid in pmids_selected or std.get('selected', False)
        
        for t in terms:
            if t.lower() in s_str:
                found_in_all[t].append({'pmid': pmid, 'selected': selected, 'title': title, 'authors': authors})
                if selected:
                    found_in_selected[t].append({'pmid': pmid, 'title': title, 'authors': authors})

# Also check selected list directly just in case
for std in data_selected:
    if type(std) is dict:
        s_str = str(std).lower()
        pmid = str(std.get('PMID', ''))
        title = std.get('Title', '') or std.get('Reference', '')
        authors = std.get('Authors', '')
        for t in terms:
            if t.lower() in s_str:
                # add if not already added
                if not any(m['pmid'] == pmid for m in found_in_selected[t]):
                    found_in_selected[t].append({'pmid': pmid, 'title': title, 'authors': authors})

print("\\nRESULTS:")
for t in terms:
    matches = found_in_selected[t]
    if matches:
        for m in matches:
            print(f"SELECTED MATCH: {t} | Authors: {m['authors']} | PMID: {m['pmid']} | Title: {m['title'][:60]}")
