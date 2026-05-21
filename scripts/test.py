from Bio import Entrez
Entrez.email = 'test@example.com'
q = '(Breast AND Cancer)[Title/Abstract] AND (folic acid OR folate OR methyl donor nutrients OR one carbon cycle nutrients)[Title/Abstract] AND (incidence OR risk OR development OR "associated with" OR "odds ratio") NOT ("breast cancer survivors"[Title] OR "breast cancer patients"[Title]) NOT (mice[Title] OR mouse[Title] OR rat[Title] OR murine[Title] OR "in vitro"[Title]) NOT "SNP"[Title] AND (Journal Article[ptyp] OR "Clinical Trial"[ptyp])'
h = Entrez.esearch(db='pubmed', term=q, retmax=5000)
r = Entrez.read(h)
h.close()
ids = r.get('IdList', [])
print(f'Total: {len(ids)}, 34071317 in list: {str("34071317" in ids)}')
