import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import meta_analysis

print("OpenAI client:", meta_analysis.client)
print("Gemini client:", meta_analysis.gemini_client)

if meta_analysis.client:
    try:
        res = meta_analysis.client.chat.completions.create(
            model="openai.gpt-4o",
            messages=[{"role": "user", "content": "hello"}]
        )
        print("OpenAI completion:", res.choices[0].message.content)
    except Exception as e:
        print("OpenAI failed:", e)

if meta_analysis.gemini_client:
    try:
        res = meta_analysis.gemini_client.models.generate_content(
            model=meta_analysis.gemini_model_name,
            contents="hello"
        )
        print("Gemini completion:", res.text)
    except Exception as e:
        print("Gemini failed:", e)
