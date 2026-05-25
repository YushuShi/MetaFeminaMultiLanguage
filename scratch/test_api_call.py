import os
from dotenv import load_dotenv
from openai import OpenAI
from google import genai

def test_openai():
    print("Testing OpenAI API...")
    try:
        load_dotenv("mykey.env")
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)
            
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Say hello!"}],
            max_tokens=10
        )
        print("OpenAI Success:", response.choices[0].message.content.strip())
        return True
    except Exception as e:
        print("OpenAI Failed:", e)
        return False

def test_gemini():
    print("Testing Gemini API...")
    try:
        load_dotenv("mykey.env")
        api_key = os.getenv("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Say hello!"
        )
        print("Gemini Success:", response.text.strip())
        return True
    except Exception as e:
        print("Gemini Failed:", e)
        return False

def main():
    test_openai()
    test_gemini()

if __name__ == '__main__':
    main()
