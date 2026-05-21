import re

def clean_warmer():
    path = 'scripts/warm_synonyms_cache.py'
    with open(path, 'r') as f:
        content = f.read()
        
    # Extract EXPOSURES list
    match = re.search(r'EXPOSURES = \[(.*?)\]', content, re.DOTALL)
    if not match:
        print("Could not find EXPOSURES list in script.")
        return
        
    exposures_str = match.group(1)
    # Parse items
    items = re.findall(r'"(.*?)"', exposures_str)
    
    # Process items (standardize and remove redundant)
    new_items = []
    seen = set()
    to_remove = ["thiamin", "riboflavin", "niacin", "pantothenic acid", "biotin"]
    
    for item in items:
        clean_item = item.lower()
        if clean_item in to_remove:
            continue
            
        if "(" in clean_item:
            if "beta-hydroxy-beta-methylbutyrate (hmb)" in clean_item:
                clean_item = "beta-hydroxy-beta-methylbutyrate"
            else:
                clean_item = re.sub(r'\s*\(.*\)', '', clean_item).strip()
        
        if clean_item not in seen:
            new_items.append(clean_item)
            seen.add(clean_item)
            
    # Rebuild list string
    # We'll try to keep the multi-line format
    new_exposures_str = "\n"
    for item in new_items:
        new_exposures_str += f'    "{item}",\n'
    
    new_content = content.replace(exposures_str, new_exposures_str)
    
    with open(path, 'w') as f:
        f.write(new_content)
        
    print(f"Cleaned warm_synonyms_cache.py. Reduced from {len(items)} to {len(new_items)} items.")

if __name__ == "__main__":
    clean_warmer()
