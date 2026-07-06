import os
import json

def main():
    results_dir = 'Cached_results'
    folders = os.listdir(results_dir)
    
    inconsistencies = []
    
    for folder in folders:
        folder_path = os.path.join(results_dir, folder)
        if not os.path.isdir(folder_path):
            continue
            
        for file in os.listdir(folder_path):
            if file.endswith('.json'):
                filepath = os.path.join(folder_path, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    studies = data.get('studies', [])
                    for s in studies:
                        es = s.get('Effect Size')
                        low = s.get('Lower CI')
                        upp = s.get('Upper CI')
                        pmid = s.get('PMID')
                        study_name = s.get('Study')
                        
                        try:
                            es = float(es)
                            low = float(low)
                            upp = float(upp)
                            
                            # Check if ES is outside [low, upp] (allowing some small floating point tolerance or ordering)
                            if es < low or es > upp:
                                inconsistencies.append({
                                    "folder": folder,
                                    "file": file,
                                    "pmid": pmid,
                                    "study": study_name,
                                    "Effect Size": es,
                                    "Lower CI": low,
                                    "Upper CI": upp,
                                    "Issue": "ES outside CI range"
                                })
                            elif low > upp:
                                inconsistencies.append({
                                    "folder": folder,
                                    "file": file,
                                    "pmid": pmid,
                                    "study": study_name,
                                    "Effect Size": es,
                                    "Lower CI": low,
                                    "Upper CI": upp,
                                    "Issue": "Lower CI > Upper CI"
                                })
                        except (ValueError, TypeError):
                            # None or non-numeric
                            pass
                except Exception as e:
                    pass

    print(f"Found {len(inconsistencies)} inconsistencies:")
    for inc in inconsistencies:
        print(f"\nExposure: {inc['folder']} | File: {inc['file']}")
        print(f"  Study: {inc['study']} (PMID: {inc['pmid']})")
        print(f"  ES: {inc['Effect Size']} | Lower CI: {inc['Lower CI']} | Upper CI: {inc['Upper CI']}")
        print(f"  Issue: {inc['Issue']}")

if __name__ == '__main__':
    main()
