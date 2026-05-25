import os
import json

def main():
    results_dir = 'Cached_results'
    folders = os.listdir(results_dir)
    
    uterine_total_studies = 0
    ovarian_total_studies = 0
    
    for folder in folders:
        folder_path = os.path.join(results_dir, folder)
        if not os.path.isdir(folder_path):
            continue
            
        for file in os.listdir(folder_path):
            filepath = os.path.join(folder_path, file)
            if file == 'uterine_cancer_incidence_true_all.json':
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    uterine_total_studies += len(data.get('studies', []))
                except:
                    pass
            elif file == 'ovarian_cancer_incidence_true_all.json':
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    ovarian_total_studies += len(data.get('studies', []))
                except:
                    pass

    print(f"Total uterine cancer studies across all exposures: {uterine_total_studies}")
    print(f"Total ovarian cancer studies across all exposures: {ovarian_total_studies}")

if __name__ == '__main__':
    main()
