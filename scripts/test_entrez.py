from Bio import Entrez
import os

Entrez.email = "margauxdelporte@gmail.com"

def test_entrez():
    print("Testing Entrez Search...")
    try:
        handle = Entrez.esearch(db="pubmed", term="breast cancer", retmax=5)
        record = Entrez.read(handle)
        handle.close()
        print(f"Success! Found {len(record['IdList'])} IDs.")
        print(f"IDs: {record['IdList']}")
    except Exception as e:
        print(f"Entrez Search Failed: {e}")

if __name__ == "__main__":
    test_entrez()
