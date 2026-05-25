import os

def check_env_file(path):
    if os.path.exists(path):
        print(f"Found env file at: {path}")
        with open(path, 'r') as f:
            for line in f:
                if 'KEY' in line or 'EMAIL' in line:
                    key = line.split('=')[0].strip()
                    print(f"  Contains key: {key}")
    else:
        # print(f"Not found: {path}")
        pass

def main():
    # Check parent dirs
    current = os.path.abspath('.')
    while True:
        check_env_file(os.path.join(current, 'mykey.env'))
        check_env_file(os.path.join(current, '.env'))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        
    # Also check user home directory
    home = os.path.expanduser('~')
    check_env_file(os.path.join(home, 'mykey.env'))
    check_env_file(os.path.join(home, '.env'))

if __name__ == '__main__':
    main()
