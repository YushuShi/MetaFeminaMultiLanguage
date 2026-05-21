import os
import sys

print("Starting minimal test...")
try:
    import app
    print("Import 'app' successful.")
except Exception as e:
    print(f"Import 'app' failed: {e}")
    import traceback
    traceback.print_exc()

print("Minimal test done.")
