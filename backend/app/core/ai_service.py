import os
from pathlib import Path
from llama_cpp import Llama
from app.core.paths import MODELS_DIR

class AIService:
    _instance = None
    
    def __init__(self):
        self.llm = None
        self.active_profile = None
        self.model_path = None
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def load_model(self):
        """Loads the model into memory. Call this during app startup."""
        if self.llm is not None:
            return True
            
        from app.core.model_registry import model_registry
        profile = model_registry.get_active_profile()
        if not profile:
            print("Error: No active model profile configured.")
            return False
            
        self.active_profile = profile
        self.model_path = model_registry.get_model_path(profile["filename"])
            
        if not self.model_path.exists():
            print(f"Warning: Model not found at {self.model_path}. Please download the model first.")
            return False
            
        try:
            print(f"Loading model into RAM: {self.model_path} with profile {profile['name']}")
            
            import llama_cpp
            
            # Check for GPU support
            gpu_layers = profile.get("n_gpu_layers", 20)
            supports_gpu = True  # Bypassing wrapper check since CUDA DLLs are manually linked


            try:
                self.llm = Llama(
                    model_path=str(self.model_path),
                    n_ctx=profile.get("n_ctx", 2048),
                    n_threads=profile.get("n_threads", 4),
                    n_gpu_layers=gpu_layers,
                    verbose=False
                )
            except Exception as e:
                if gpu_layers > 0:
                    print(f"GPU Model load failed ({e}). Attempting CPU fallback...")
                    self.llm = Llama(
                        model_path=str(self.model_path),
                        n_ctx=profile.get("n_ctx", 2048),
                        n_threads=profile.get("n_threads", 4),
                        n_gpu_layers=0,
                        verbose=False
                    )
                else:
                    raise e
                    
            print(f"Model loaded successfully (GPU Layers: {gpu_layers if supports_gpu else 0}).")
            return True
        except Exception as e:
            print(f"Failed to load model completely: {e}")
            return False
            
    def unload_model(self):
        """Unloads the model from memory to free RAM."""
        if self.llm is not None:
            del self.llm
            self.llm = None
            import gc
            gc.collect()
            print("AI Model unloaded from RAM.")
            
    def generate_stream(self, prompt: str, history: list = None, system_prompt: str = None):
        """Generates a streaming response from the model, considering conversation history."""
        from app.core.resource_governor import resource_governor, SystemState
        if resource_governor.state in [SystemState.EMERGENCY, SystemState.HIGH_LOAD]:
            yield f"\n[System Error: Cannot process request. Sentinel is in {resource_governor.state.value} mode to protect system stability.]"
            return
            
        if resource_governor.state == SystemState.USER_PAUSED:
            yield "\n[System Error: Sentinel background tasks and AI inference are currently paused by the user.]"
            return
            
        if not self.llm:
            yield "SYSTEM: Error - Model is not loaded. Please wait for the system to initialize."
            return

        if system_prompt is None:
            # We will try to fetch the active system prompt from memory/db in a future step.
            system_prompt = (
                "You are Sentinel, a highly advanced, concise, and helpful personal AI assistant. "
                "You have access to the following tools:\n"
                "1. get_system_telemetry(): Returns the current CPU and RAM usage.\n"
                "2. run_system_op(operation: str, target: str): Executes a validated system operation (e.g. get_processes, ping_host).\n"
                "3. search_web(query: str): Searches the live internet and returns factual summaries.\n"
                "To use a tool, you MUST output a JSON block wrapped in <tool_call> tags. Example:\n"
                '<tool_call>{"name": "search_web", "args": {"query": "current weather"}}</tool_call>\n'
                "Once you receive the tool output (which will be provided as a system message), you must summarize the result for the user."
            )

        # Format prompt according to Qwen/ChatML format
        formatted_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        
        # Append history if available
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                formatted_prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
                
        # Append current user prompt
        formatted_prompt += f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        try:
            stream = self.llm(
                prompt=formatted_prompt,
                max_tokens=512,
                stop=["<|im_end|>"],
                stream=True
            )
            
            for chunk in stream:
                token = chunk["choices"][0]["text"]
                if token:
                    yield token
        except Exception as e:
            yield f"\n[Inference Error: {e}]"

ai_service = AIService.get_instance()
