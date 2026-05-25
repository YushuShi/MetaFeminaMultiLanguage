import os
from dotenv import load_dotenv

def main():
    # Try loading mykey.env
    env_path = 'mykey.env'
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print("Loaded mykey.env")
    else:
        print("mykey.env not found in current directory.")
        
    print("OPENAI_API_KEY present:", 'OPENAI_API_KEY' in os.environ)
    print("GOOGLE_API_KEY present:", 'GOOGLE_API_KEY' in os.environ)
    print("PUBMED_EMAIL present:", 'PUBMED_EMAIL' in os.environ)

if __name__ == '__main__':
    main()
