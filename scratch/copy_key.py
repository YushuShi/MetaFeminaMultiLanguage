import shutil
import os

def main():
    src = r"C:\Users\mde4023\.gemini\antigravity\scratch\mykey.env"
    dst = "mykey.env"
    
    if os.path.exists(src):
        shutil.copy(src, dst)
        print(f"Copied {src} to {dst}")
        # Verify it exists now
        if os.path.exists(dst):
            print("Successfully verified mykey.env exists in current directory.")
            # Let's print the size to be sure
            print("Size:", os.path.getsize(dst), "bytes")
    else:
        print(f"Source file {src} does not exist!")

if __name__ == '__main__':
    main()
