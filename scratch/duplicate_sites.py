import os
import shutil

def duplicate_project(src_dir, dest_dir):
    print(f"Duplicating {src_dir} to {dest_dir}...")
    
    # Custom ignore function to skip git, caches, and cached results
    def ignore_patterns(path, names):
        ignored = []
        for name in names:
            if name in ['.git', '__pycache__', 'Cached_results', '.Rhistory', '.RData', '.ipynb_checkpoints']:
                ignored.append(name)
            elif name.endswith('.pyc'):
                ignored.append(name)
        return ignored

    if os.path.exists(dest_dir):
        print(f"Destination {dest_dir} already exists. Removing it first...")
        shutil.rmtree(dest_dir)
        
    shutil.copytree(src_dir, dest_dir, ignore=ignore_patterns)
    
    # Create empty Cached_results directory in the destination
    os.makedirs(os.path.join(dest_dir, 'Cached_results'), exist_ok=True)
    print(f"Successfully duplicated to {dest_dir}")

if __name__ == '__main__':
    src = r'c:\Users\mde4023\Downloads\MetaMamm'
    duplicate_project(src, r'c:\Users\mde4023\Downloads\MetaOvary')
    duplicate_project(src, r'c:\Users\mde4023\Downloads\MetaUturus')
