import json
import re

def clean_cache():
    exposures_path = 'static/exposures.json'
    cache_path = 'data/synonyms_cache.json'
    
    with open(exposures_path, 'r') as f:
        exposures = json.load(f)
        
    with open(cache_path, 'r') as f:
        cache = json.load(f)
        
    # Create mapping from secondary names to primary exposure names
    # e.g., "riboflavin" -> "vitamin b2"
    # and "cbd" -> "cannabidiol" (if it was "Cannabidiol (CBD)")
    
    primary_to_full = {e.lower(): e for e in exposures}
    
    # We want to identify synonyms that were in brackets
    # I'll hardcode some known ones or use the ones I found
    synonym_map = {
        "5-hydroxytryptophan": "5-htp",
        "branched-chain amino acids": "bcaas",
        "beet juice": "beetroot",
        "cbd": "cannabidiol",
        "bovine and shark": "cartilage",
        "roman": "chamomile",
        "kola nut": "cola nut",
        "forskolin": "coleus forskohlii",
        "dhea": "dehydroepiandrosterone",
        "nac": "n-acetylcysteine",
        "blond": "psyllium",
        "same": "s-adenosyl-l-methionine",
        "riboflavin": "vitamin b2",
        "niacin": "vitamin b3",
        "pantothenic acid": "vitamin b5",
        "biotin": "vitamin b7"
    }
    
    new_cache = {}
    
    def get_preferred(k):
        k = k.lower().strip()
        # Remove brackets if present
        if "(" in k:
            match = re.search(r'^(.*)\s*\((.*)\)$', k)
            if match:
                p1, p2 = match.group(1).strip().lower(), match.group(2).strip().lower()
                # If either part is a known primary, use it
                if p1 in primary_to_full: return p1
                if p2 in primary_to_full: return p2
                # If either part is a known synonym, use its primary
                if p1 in synonym_map: return synonym_map[p1]
                if p2 in synonym_map: return synonym_map[p2]
                # Default to first part
                return p1
            return re.sub(r'\s*\(.*\)', '', k).strip()
        
        # No brackets
        if k in primary_to_full: return primary_to_full[k]
        if k in synonym_map:
            resolved = synonym_map[k]
            if resolved in primary_to_full:
                return primary_to_full[resolved]
            return resolved
        return k

    for key, val in cache.items():
        preferred = get_preferred(key)
        
        if preferred not in new_cache:
            new_cache[preferred] = {"core": "", "downstream": ""}
            
        entry = new_cache[preferred]
        
        # Merge content from old entry
        if isinstance(val, dict):
            core_content = val.get("core", "")
            down_content = val.get("downstream", "")
        else:
            core_content = str(val)
            down_content = ""
            
        current_syns = set([s.strip().lower() for s in entry["core"].split(",") if s.strip()])
        
        # 1. Add parts of the key if bracketed
        if "(" in key:
            match = re.search(r'^(.*)\s*\((.*)\)$', key)
            if match:
                p1, p2 = match.group(1).strip().lower(), match.group(2).strip().lower()
                if p1 != preferred: current_syns.add(p1)
                if p2 != preferred: current_syns.add(p2)
            else:
                clean_k = re.sub(r'\s*\(.*\)', '', key).strip().lower()
                if clean_k != preferred: current_syns.add(clean_k)
        else:
            # No brackets, but if key != preferred, the key itself is a synonym
            if key.lower().strip() != preferred:
                current_syns.add(key.lower().strip())

        # 2. Add content from the old entry's core
        if core_content:
            current_syns.update([s.strip().lower() for s in core_content.split(",") if s.strip()])
        
        # 3. Always ensure the preferred name itself IS in core (app expectation)
        current_syns.add(preferred)

        # 4. Handle HMB exception: remove 'hmb' from all synonyms if preferred is beta-hydroxy...
        if "beta-hydroxy-beta-methylbutyrate" in preferred:
            current_syns = {s for s in current_syns if s != "hmb"}
            
        entry["core"] = ", ".join(sorted(list(current_syns)))
        
        if down_content and not entry["downstream"]:
            entry["downstream"] = down_content

    # Final pass: Ensure all synonyms from our mapping are actually in the core
    for syn, prim in synonym_map.items():
        if prim in new_cache:
            entry = new_cache[prim]
            # Handle HMB exception again
            if prim == "beta-hydroxy-beta-methylbutyrate" and syn == "hmb":
                continue
            
            current = set([s.strip().lower() for s in entry["core"].split(",") if s.strip()])
            current.add(syn.lower())
            current.add(prim.lower())
            entry["core"] = ", ".join(sorted(list(current)))

    with open(cache_path, 'w') as f:
        json.dump(new_cache, f, indent=4)
    print(f"Cleanly consolidated synonyms_cache.json. Keys: {len(cache)} -> {len(new_cache)}")

if __name__ == "__main__":
    clean_cache()
