import os
import sys
from dotenv import load_dotenv

# Ensure we import from the root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

def main():
    load_dotenv('mykey.env')
    print("Starting get_analysis_data...")
    res = app.meta_analysis.get_analysis_data(
        'Ovarian cancer', 
        'chocolate', 
        outcome='Incidence', 
        exclude_meta=True
    )
    print("Result:")
    print("Error:", res.get('error'))
    studies = res.get('studies', [])
    print("Studies count:", len(studies))
    if studies:
        print("First study:", studies[0])

if __name__ == "__main__":
    main()
