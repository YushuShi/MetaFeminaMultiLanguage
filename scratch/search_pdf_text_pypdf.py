import pypdf
import os

pdf_files = [
    'Plot/forest_protective_breast.pdf',
    'Plot/forest_harmful_breast.pdf',
    'Plot/plot_es_vs_heterogeneity.pdf',
    'Plot/plot_eggers_vs_heterogeneity.pdf',
    'Plot/comparison_dumbbell.pdf'
]

keywords = ['bcaa', 'leucine', 'isoleucine', 'choline']

for pdf_file in pdf_files:
    if not os.path.exists(pdf_file):
        print(f"File {pdf_file} does not exist.")
        continue
    
    print(f"\nScanning {pdf_file}:")
    reader = pypdf.PdfReader(pdf_file)
    found_any = False
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
        for kw in keywords:
            if kw in text.lower():
                print(f"  -> Found '{kw}' on page {i+1}")
                found_any = True
    if not found_any:
        print("  -> None of the keywords found in text.")
