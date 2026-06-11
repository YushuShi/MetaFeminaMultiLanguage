import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import meta_analysis

def verify_resolution():
    print("Verifying canonical name resolution...")
    
    # Test cases: (input, expected_canonical)
    test_cases = [
        ("eggs", "eggs"),
        ("dairy", "dairy"),
        ("egg", "eggs"),
        ("milk", "dairy"),
        ("yogurt", "dairy"),
        ("whole egg", "eggs")
    ]
    
    success = True
    for input_term, expected in test_cases:
        resolved = meta_analysis.get_canonical_name(input_term)
        print(f"Input: '{input_term}' -> Resolved: '{resolved}' (Expected: '{expected}')")
        if resolved != expected:
            print("  [FAIL]")
            success = False
        else:
            print("  [PASS]")
            
    if success:
        print("ALL TESTS PASSED SUCCESSFULLY!")
    else:
        print("SOME TESTS FAILED.")

if __name__ == "__main__":
    verify_resolution()
