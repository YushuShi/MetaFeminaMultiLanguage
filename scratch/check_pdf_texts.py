import zlib
import re

def get_pdf_text(filepath):
    with open(filepath, 'rb') as f:
        content = f.read()
    
    # PDF objects containing streams
    streams = re.findall(b'stream\r?\n(.*?)\r?\nendstream', content, re.DOTALL)
    text_segments = []
    
    for s in streams:
        try:
            decompressed = zlib.decompress(s)
            # Find strings in parentheses like (BCAAs) or (Choline) or similar
            matches = re.findall(rb'\((.*?)\)', decompressed)
            for m in matches:
                try:
                    text_segments.append(m.decode('utf-8', errors='ignore'))
                except Exception:
                    pass
        except Exception:
            # Maybe not compressed or compressed with different parameters
            matches = re.findall(rb'\((.*?)\)', s)
            for m in matches:
                try:
                    text_segments.append(m.decode('utf-8', errors='ignore'))
                except Exception:
                    pass
    return text_segments

protective_texts = get_pdf_text('Plot/forest_protective_breast.pdf')
harmful_texts = get_pdf_text('Plot/forest_harmful_breast.pdf')

print("Protective texts containing BCAA/bcaa/Choline/choline/Betaine/betaine:")
for text in protective_texts:
    if any(keyword in text.lower() for keyword in ['bcaa', 'choline', 'betaine']):
        print("FOUND:", text)

print("\nHarmful texts containing Leucine/leucine/glutamine/Glutamine:")
for text in harmful_texts:
    if any(keyword in text.lower() for keyword in ['leucine', 'glutamine']):
        print("FOUND:", text)
