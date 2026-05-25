import os
import json

def main():
    results_dir = 'Cached_results'
    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} not found.")
        return

    folders = os.listdir(results_dir)
    
    uterine_total = 0
    uterine_with_studies = 0
    ovarian_total = 0
    ovarian_with_studies = 0
    
    for folder in folders:
        folder_path = os.path.join(results_dir, folder)
        if not os.path.isdir(folder_path):
            continue
            
        files = os.listdir(folder_path)
        for file in files:
            filepath = os.path.join(folder_path, file)
            if 'uterine_cancer_incidence_true_all.json' == file:
                uterine_total += 1
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if len(data.get('studies', [])) > 0:
                        uterine_with_studies += 1
                except Exception as e:
                    pass
            elif 'ovarian_cancer_incidence_true_all.json' == file:
                ovarian_total += 1
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if len(data.get('studies', [])) > 0:
                        ovarian_with_studies += 1
                except Exception as e:
                    pass

    print(f"Uterine: total cached files = {uterine_total}, with studies = {uterine_with_studies}")
    print(f"Ovarian: total cached files = {ovarian_total}, with studies = {ovarian_with_studies}")

if __name__ == '__main__':
    main()
