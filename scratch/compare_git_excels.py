import subprocess
import pandas as pd
import io
import os

def get_git_excel(filepath):
    # Read binary file from git HEAD using subprocess to avoid PowerShell binary redirection corruption
    cmd = ["git", "show", f"HEAD:{filepath}"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(f"Error fetching {filepath} from git: {result.stderr.decode('utf-8', errors='ignore')}")
        return None
    return pd.read_excel(io.BytesIO(result.stdout))

def compare_dataframes(df_git, df_local, name):
    print(f"\n==========================================")
    print(f"Comparing {name}")
    print(f"==========================================")
    if df_git is None or df_local is None:
        print("Cannot compare (missing dataframe).")
        return

    # Check shape
    print(f"Git shape: {df_git.shape} | Local shape: {df_local.shape}")
    
    # Compare exposures
    git_exposures = set(df_git['Exposure'].tolist())
    local_exposures = set(df_local['Exposure'].tolist())
    
    added = local_exposures - git_exposures
    removed = git_exposures - local_exposures
    common = git_exposures & local_exposures
    
    if added:
        print(f"Added exposures ({len(added)}): {sorted(list(added))}")
    if removed:
        print(f"Removed exposures ({len(removed)}): {sorted(list(removed))}")
        
    # Compare details for common exposures
    diffs = []
    for exp in sorted(list(common)):
        row_git = df_git[df_git['Exposure'] == exp].iloc[0]
        row_local = df_local[df_local['Exposure'] == exp].iloc[0]
        
        row_diffs = {}
        for col in df_git.columns:
            val_git = row_git[col]
            val_local = row_local[col]
            
            # Compare with floating point tolerance
            if pd.isna(val_git) and pd.isna(val_local):
                continue
            elif pd.isna(val_git) or pd.isna(val_local):
                row_diffs[col] = (val_git, val_local)
            elif isinstance(val_git, (int, float)) and isinstance(val_local, (int, float)):
                if abs(val_git - val_local) > 1e-5:
                    row_diffs[col] = (val_git, val_local)
            elif val_git != val_local:
                row_diffs[col] = (val_git, val_local)
                
        if row_diffs:
            diffs.append((exp, row_diffs))
            
    if diffs:
        print(f"\nModified exposures ({len(diffs)}):")
        for exp, r_diff in diffs:
            print(f"  {exp}:")
            for col, (g, l) in r_diff.items():
                print(f"    {col}: Git={g} -> Local={l}")
    else:
        print("\nNo common exposures were modified.")

def main():
    files = [
        'Plot/exposures_meta_analysis_ovarian_combined.xlsx',
        'Plot/exposures_meta_analysis_uterine_combined.xlsx'
    ]
    for f in files:
        if os.path.exists(f):
            df_local = pd.read_excel(f)
            df_git = get_git_excel(f)
            compare_dataframes(df_git, df_local, f)
        else:
            print(f"Local file {f} does not exist.")

if __name__ == '__main__':
    main()
