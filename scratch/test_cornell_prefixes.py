import os
import sys
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, "mykey.env"))

sys.stdout.reconfigure(encoding='utf-8')

api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")

client = OpenAI(api_key=api_key, base_url=base_url)

for model in ["openai.gpt-4o", "gpt-4o", "openai.gpt-4.1", "gpt-4.1"]:
    try:
        print(f"Testing model: '{model}'...")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'OK'"}],
            max_tokens=5
        )
        print(f"  SUCCESS! Response: {response.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"  FAILED! Error: {e}")
