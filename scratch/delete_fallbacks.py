import os
import json
import glob

def main():
    files = glob.glob('Cached_results/**/*.json', recursive=True)
    deleted = 0
    for f in files:
        should_delete = False
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                if 'Regex extraction fallback' in content:
                    should_delete = True
            if should_delete:
                print(f"Deleting {f}")
                os.remove(f)
                deleted += 1
        except Exception as e:
            print(f"Error checking/deleting {f}: {e}")
    print(f"Deleted {deleted} files containing Regex extraction fallback.")

if __name__ == '__main__':
    main()
