import os
import sys

print("--- B5-R1: Real Local Inference Verification ---")
print(f"Python Executable: {sys.executable}")
print("Attempting to import llama_cpp...")

try:
    import llama_cpp
    print(f"llama_cpp imported successfully. Version: {llama_cpp.__version__}")
    
    # We would theoretically try to load a model here, but the import itself is blocked.
    # If the import succeeded, we would need to download a tiny gguf.
    # Since we know the import fails on this specific system due to WDAC, let's see.
    
except Exception as e:
    print("FATAL ERROR: Failed to import llama_cpp.")
    print(f"Exception Type: {type(e).__name__}")
    print(f"Exception Message: {e}")
    sys.exit(1)

