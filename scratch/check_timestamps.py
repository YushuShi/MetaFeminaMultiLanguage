import os
import json
from datetime import datetime

def main():
    results_dir = 'Cached_results'
    if not os.path.exists(results_dir):
        print("No Cached_results directory.")
        return

    all_files = []
    for root, dirs, files in os.walk(results_dir):
        for f in files:
            if f.endswith('.json'):
                path = os.path.join(root, f)
                mtime = os.path.getmtime(path)
                dt = datetime.fromtimestamp(mtime)
                all_files.append((path, dt))
                
    if not all_files:
        print("No JSON files found in Cached_results.")
        return
        
    all_files.sort(key=lambda x: x[1])
    print(f"Total JSON cache files: {len(all_files)}")
    print(f"Oldest 5 files:")
    for path, dt in all_files[:5]:
        print(f"  {path}: {dt}")
    print(f"Newest 5 files:")
    for path, dt in all_files[-5:]:
        print(f"  {path}: {dt}")

if __name__ == '__main__':
    main()
