import time
import psutil
from app.core.model_registry import model_registry
from app.core.ai_service import ai_service
from app.core.resource_governor import resource_governor, SystemState

def run_benchmark():
    print("=" * 50)
    print("SENTINEL INFERENCE BENCHMARK")
    print("=" * 50)
    
    # Ensure profile exists
    profile = model_registry.get_active_profile()
    if not profile:
        print("No active model profile found. Exiting.")
        return
        
    print(f"Profile: {profile['name']}")
    
    # Measure Load Time
    print("\n--- 1. Model Loading ---")
    start_load = time.time()
    success = ai_service.load_model()
    load_time = time.time() - start_load
    
    if not success:
        print("Model failed to load.")
        return
        
    print(f"Load Time: {load_time:.2f} seconds")
    
    engine = "GPU" if getattr(ai_service.llm, "n_gpu_layers", 0) > 0 else "CPU (AVX2)"
    print(f"Active Engine: {engine}")
    
    # Measure Inference
    print("\n--- 2. Inference Benchmark ---")
    prompt = "<|im_start|>user\nWrite a three paragraph essay about the history of artificial intelligence.<|im_end|>\n<|im_start|>assistant\n"
    
    print("Generating response...")
    start_inference = time.time()
    first_token_time = None
    token_count = 0
    
    stream = ai_service.llm.create_completion(
        prompt=prompt,
        max_tokens=150,
        stream=True,
        temperature=0.7
    )
    
    for chunk in stream:
        if first_token_time is None:
            first_token_time = time.time()
        token_count += 1
        # Print a dot to show progress
        print(".", end="", flush=True)
        
    end_inference = time.time()
    print("\n")
    
    ttft = first_token_time - start_inference
    total_time = end_inference - first_token_time
    tps = (token_count - 1) / total_time if total_time > 0 else 0
    
    print(f"Time To First Token (TTFT): {ttft:.2f} seconds")
    print(f"Tokens Generated: {token_count}")
    print(f"Tokens Per Second (TPS): {tps:.2f} t/s")
    
    # Resource checking
    print("\n--- 3. Resource Pressure Test ---")
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    print(f"System Load: CPU {cpu}%, RAM {mem}%")
    
    print("Simulating SystemState.HIGH_LOAD transition...")
    resource_governor.state = SystemState.INTERACTIVE # reset
    resource_governor._transition_to(SystemState.HIGH_LOAD)
    
    if ai_service.llm is None:
        print("SUCCESS: ResourceGovernor successfully unloaded the model.")
    else:
        print("FAIL: ResourceGovernor failed to unload the model.")
        
    print("=" * 50)
    print("Benchmark Complete")

if __name__ == "__main__":
    run_benchmark()
