import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import meta_analysis

print("Gemini client:", meta_analysis.gemini_client)
print("OpenAI client:", meta_analysis.client)

exposure = "eggs"
prompt = f"""Acting as a nutritional epidemiology researcher, for the nutritional exposure: "{exposure}"

Identify which type this exposure belongs to:
- Compound (vitamins, minerals, fatty acids, bioactive molecules, polyphenols, peptides, phytochemicals)
- Food item (whole foods, food groups, dietary patterns, food preparations)

Then classify search terms into two categories:

1. CORE — terms that directly refer to the exposure itself:
   - If a compound: chemical names, specific isomers, biomarker measurement terms
     (serum/plasma/dietary X, X intake, X supplementation, X level)
   - If a food item: scientific (Latin) name, common name variants, direct food forms
     and preparations (e.g. tofu, tempeh, soy milk for soy)
   Exclude: food sources that contain the compound, derived metabolites that are
   distinct compounds, vague functional classes (e.g. "antioxidants")

2. DOWNSTREAM — related terms for broader search recall, NOT the exposure itself:
   - If a compound: primary food sources containing it (e.g. citrus fruits for vitamin C)
   - If a food item: key bioactive compounds it contains (e.g. isoflavones for soy)
   Exclude: vague functional terms (e.g. "polyphenols", "antioxidants", "plant-based foods")

Return ONLY a JSON object, no explanation:
{{"core": "term1, term2, term3", "downstream": "term1, term2"}}

Core: no more than 10 terms. Downstream: no more than 4 terms. If no downstream applies, use empty string."""

print("Sending request to Gemini...")
try:
    response = meta_analysis.gemini_client.models.generate_content(
        model=meta_analysis.gemini_model_name,
        contents=prompt
    )
    print("Raw Gemini Response text:")
    print(repr(response.text))
except Exception as e:
    print("Gemini failed:", e)

if meta_analysis.client:
    print("Sending request to OpenAI...")
    try:
        model_to_use = meta_analysis.get_openai_model_name()
        response = meta_analysis.client.chat.completions.create(
            model=model_to_use,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0
        )
        print("Raw OpenAI Response text:")
        print(repr(response.choices[0].message.content))
    except Exception as e:
        print("OpenAI failed:", e)
