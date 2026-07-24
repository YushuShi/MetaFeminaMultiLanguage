import os

search_paths = [
    r"C:\Program Files\R",
    r"C:\Program Files (x86)\R",
]

found = False
for path in search_paths:
    if os.path.exists(path):
        print(f"Found R directory: {path}")
        for root, dirs, files in os.walk(path):
            if "Rscript.exe" in files:
                rscript_path = os.path.join(root, "Rscript.exe")
                print(f"Found Rscript.exe at: {rscript_path}")
                found = True
                break

if not found:
    print("Rscript.exe not found in common directories. Searching root of C:\\Program Files...")
    # Do a quick check
    for root, dirs, files in os.walk(r"C:\Program Files"):
        # Limit depth to avoid infinite search
        depth = root.count(os.sep)
        if depth > 4:
            continue
        if "Rscript.exe" in files:
            rscript_path = os.path.join(root, "Rscript.exe")
            print(f"Found Rscript.exe at: {rscript_path}")
            found = True
            break
