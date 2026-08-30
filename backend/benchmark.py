import time
import os
import psutil
from llama_cpp import Llama

def benchmark_model():
    model_path = r"C:\Users\shamb\AppData\Roaming\sentinel\models\qwen2.5-1.5b-instruct-q4_k_m.gguf"
    
    if not os.path.exists(model_path):
        print(f"Model not found at {model_path}. Please check path.")
        return

    print(f"Benchmarking model: {model_path}")
    print(f"File size: {os.path.getsize(model_path) / (1024*1024):.2f} MB")
    
    print("\n--- Load Phase ---")
    start_time = time.time()
    llm = Llama(
        model_path=model_path,
        n_ctx=2048,
        n_threads=4,
        n_gpu_layers=0,
        verbose=False
    )
    load_time = time.time() - start_time
    print(f"Load time: {load_time:.2f} seconds")
    
    # RAM Usage
    process = psutil.Process(os.getpid())
    ram_usage = process.memory_info().rss / (1024*1024)
    print(f"RAM Usage: {ram_usage:.2f} MB")
    
    print("\n--- Inference Phase ---")
    prompt = "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\nWrite a short poem about coding.<|im_end|>\n<|im_start|>assistant\n"
    
    print("Generating...")
    start_gen_time = time.time()
    
    stream = llm(
        prompt=prompt,
        max_tokens=100,
        stop=["<|im_end|>"],
        stream=True
    )
    
    first_token_time = None
    tokens = 0
    
    for chunk in stream:
        if first_token_time is None:
            first_token_time = time.time() - start_gen_time
        token = chunk["choices"][0]["text"]
        if token:
            tokens += 1
            print(token, end="", flush=True)
            
    total_gen_time = time.time() - start_gen_time
    
    print("\n\n--- Results ---")
    print(f"First token latency: {first_token_time:.2f} seconds")
    print(f"Total generation time: {total_gen_time:.2f} seconds")
    print(f"Tokens generated: {tokens}")
    print(f"Tokens per second: {tokens / total_gen_time:.2f} t/s")

if __name__ == "__main__":
    benchmark_model()
