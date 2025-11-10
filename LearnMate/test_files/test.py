import sys
import os
sys.path.append(os.path.dirname(__file__))

from backend.models.code_analysis import CodeAnalysisModel
import logging

logging.basicConfig(level=logging.DEBUG)

def test_debug():
    print("Testing code analysis...")
    
    analyzer = CodeAnalysisModel()
    
    test_code = """
def factorial(n):
    if n == 0:
        return 1
    else:
        return n * factorial(n-1)
    
result = factorial(5)
print(result)
"""
    
    print(f"Model pipeline available: {analyzer.pipeline is not None}")
    
    if analyzer.pipeline:
        result = analyzer.explain_code(test_code, "explain")
        print(f"RESULT: '{result}'")
        print(f"Result length: {len(result)}")
        print(f"Result is empty: {not result.strip()}")
    else:
        print("Model not loaded properly")

if __name__ == "__main__":
    test_debug()

