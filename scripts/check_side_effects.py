import sys
import os
from Bio import Entrez as Entrez_before

# Import meta_analysis
import meta_analysis
from Bio import Entrez as Entrez_after

print(f"Entrez Before ID: {id(Entrez_before)}")
print(f"Entrez After ID: {id(Entrez_after)}")
print(f"meta_analysis Entrez ID: {id(meta_analysis.Entrez)}")

print(f"Entrez After Email: {Entrez_after.email}")
print(f"Entrez After Tool: {getattr(Entrez_after, 'tool', 'Not Set')}")
print(f"Entrez After Base URL: {getattr(Entrez_after, 'base_url', 'Not Set')}")

if Entrez_before is Entrez_after:
    print("Entrez is the same object.")
else:
    print("Entrez has been REPLACED!")

if hasattr(Entrez_after, 'esearch'):
    print(f"esearch type: {type(Entrez_after.esearch)}")
    print(f"esearch dir: {dir(Entrez_after.esearch)}")

# Let's try to see if it's a wrapper
import inspect
try:
    print(f"Source of esearch: {inspect.getfile(Entrez_after.esearch)}")
except:
    print("Could not get source of esearch.")
