import shutil
import os

def copy_folate_to_folic_acid():
    print("Starting copy process...")
    
    # 1. Copy JSON result
    src_json = "Cached_results/folate/breast_cancer_incidence_true_all.json"
    dst_json = "Cached_results/folic_acid/breast_cancer_incidence_true_all.json"
    
    if os.path.exists(src_json):
        # Create a backup of the original folic_acid file first
        if os.path.exists(dst_json):
            backup_path = dst_json + ".orig_backup"
            shutil.copy2(dst_json, backup_path)
            print(f"Created backup of original Folic Acid JSON at {backup_path}")
            
        shutil.copy2(src_json, dst_json)
        print(f"Copied JSON from {src_json} to {dst_json}")
        
        # Modify the contents of the copied JSON file
        with open(dst_json, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Replace paths
        content = content.replace("static/folate/", "static/folic_acid/")
        content = content.replace("static\\folate\\", "static\\folic_acid\\")
        
        # Replace word occurrences in the results interpretation/headline
        content = content.replace("between folate and breast cancer", "between folic acid and breast cancer")
        content = content.replace("association between folate and", "association between folic acid and")
        
        with open(dst_json, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Updated paths and references inside dst JSON.")
    else:
        print(f"Source JSON {src_json} not found.")

    # 2. Copy plots
    plots = [
        "forest_breast_cancer_incidence_primary.png",
        "funnel_breast_cancer_incidence_primary.png",
        "baujat_breast_cancer_incidence_primary.png"
    ]
    
    for plot in plots:
        src_plot = os.path.join("static/folate", plot)
        dst_plot = os.path.join("static/folic_acid", plot)
        if os.path.exists(src_plot):
            shutil.copy2(src_plot, dst_plot)
            print(f"Copied plot {plot} to {dst_plot}")
        else:
            print(f"Plot {src_plot} not found.")
            
    print("Copy process completed successfully!")

if __name__ == "__main__":
    copy_folate_to_folic_acid()
