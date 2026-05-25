import os

def check_env_file(path):
    if os.path.exists(path):
        print(f"Found env file at: {path}")
        with open(path, 'r') as f:
            for line in f:
                if 'KEY' in line or 'EMAIL' in line:
                    key = line.split('=')[0].strip()
                    print(f"  Contains key: {key}")
                    
def main():
    gemini_dir = r"C:\Users\mde4023\.gemini"
    if os.path.exists(gemini_dir):
        for root, dirs, files in os.walk(gemini_dir):
            for f in files:
                if '.env' in f or 'mykey' in f:
                    check_env_file(os.path.join(root, f))
    else:
        print("Gemini dir not found.")

if __name__ == '__main__':
    main()
