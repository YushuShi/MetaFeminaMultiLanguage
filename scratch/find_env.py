import os

def main():
    for root, dirs, files in os.walk('.'):
        for f in files:
            if '.env' in f or 'mykey' in f:
                print(f"Found: {os.path.join(root, f)}")

if __name__ == '__main__':
    main()
