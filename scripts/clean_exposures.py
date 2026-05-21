import json
import re

def clean_exposures():
    path = 'static/exposures.json'
    with open(path, 'r') as f:
        exposures = json.load(f)
        
    to_remove = [
        "Branched-chain amino acids",
        "Riboflavin",
        "Niacin",
        "Pantothenic acid",
        "Biotin",
        "HMB (beta-hydroxy-beta-methylbutyrate)",
        "Chamomile (Roman)"
    ]
    
    new_exposures = []
    seen = set()
    
    for e in exposures:
        if e in to_remove:
            continue
            
        # Standardize "Name (Synonym)" -> "Name"
        # Special case: Beta-hydroxy-beta-methylbutyrate (HMB) -> drop the (HMB) part
        if "Beta-hydroxy-beta-methylbutyrate (HMB)" in e:
             new_name = "Beta-hydroxy-beta-methylbutyrate"
        elif "(" in e:
            new_name = re.sub(r'\s*\(.*\)', '', e).strip()
        else:
            new_name = e
            
        if new_name not in seen:
            new_exposures.append(new_name)
            seen.add(new_name)
            
    # Final check for sorted or just preserve order
    with open(path, 'w') as f:
        json.dump(new_exposures, f, indent=2)
        
    print(f"Cleaned exposures.json. Reduced from {len(exposures)} to {len(new_exposures)} items.")

if __name__ == "__main__":
    clean_exposures()
