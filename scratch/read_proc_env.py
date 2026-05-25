import os
import sys

try:
    import psutil
    print("psutil imported successfully")
    proc = psutil.Process(22760)
    env = proc.environ()
    print("Keys found in target process environment:")
    for k in sorted(env.keys()):
        if 'KEY' in k or 'API' in k or 'EMAIL' in k or 'TOKEN' in k:
            print(f"  {k} = [PRESENT]")
        else:
            # print(f"  {k}")
            pass
except Exception as e:
    print(f"Failed: {e}")
