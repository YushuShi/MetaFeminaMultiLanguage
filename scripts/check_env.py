import Bio
from Bio import Entrez
import os

print(f"Bio File: {Bio.__file__}")
print(f"Entrez: {Entrez}")
print(f"Entrez Email: {Entrez.email}")
print(f"Entrez API Key: {getattr(Entrez, 'api_key', 'Not Set')}")
print(f"Environment NCBI_API_KEY: {os.getenv('NCBI_API_KEY', 'Not Set')}")
print(f"Environment PUBMED_EMAIL: {os.getenv('PUBMED_EMAIL', 'Not Set')}")
