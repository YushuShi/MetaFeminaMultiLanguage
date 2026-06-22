import os
import json
from dotenv import load_dotenv
import openai

def main():
    load_dotenv('mykey.env')
    print("API KEY:", os.environ.get('OPENAI_API_KEY')[:10] + "...")
    print("BASE URL:", os.environ.get('OPENAI_BASE_URL'))
    print("MODEL:", os.environ.get('OPENAI_MODEL_NAME'))

    client = openai.OpenAI(
        api_key=os.environ['OPENAI_API_KEY'],
        base_url=os.environ.get('OPENAI_BASE_URL')
    )
    
    prompt = """
    Return a JSON object with the following keys:
    - is_directly_associated: (boolean) true
    - reason: (string) "test reason"
    """
    
    try:
        response = client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL_NAME', 'anthropic.claude-4.5-sonnet'),
            messages=[
                {"role": "system", "content": "You are a helpful screening assistant. Outcome response must be purely JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            timeout=20.0
        )
        content = response.choices[0].message.content
        print("RAW CONTENT:", repr(content))
        parsed = json.loads(content)
        print("PARSED SUCCESS:", parsed)
    except Exception as e:
        print("API ERROR:", e)

if __name__ == "__main__":
    main()
