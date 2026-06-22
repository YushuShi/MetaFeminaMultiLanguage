import os
from dotenv import load_dotenv
import openai

def main():
    load_dotenv('mykey.env')
    client = openai.OpenAI(
        api_key=os.environ['OPENAI_API_KEY'],
        base_url=os.environ.get('OPENAI_BASE_URL')
    )
    
    prompt = "Test alpha \u03b1 and beta \u03b2."
    print("Prompt length:", len(prompt))
    try:
        response = client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL_NAME', 'anthropic.claude-4.5-sonnet'),
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            timeout=20.0
        )
        print("Success! Response:", response.choices[0].message.content[:50])
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
