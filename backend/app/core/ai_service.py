"""
Local model engine: decides where the model runs and streams its answers.

Engines
  * "gpu": llama.cpp's llama-server (CUDA) as a child process, see app/core/llama_sidecar.py
  * "cpu": the llama-cpp-python binding inside this process (a CPU-only build on Python 3.14)

Load plan (load_model)
  * Profile "auto" (the default): the biggest downloaded model that fits in the free VRAM runs on
    the GPU (7B, then 3B, then 1.5B). If the GPU engine can't be used: the 1.5B model on the CPU.
  * A named profile: that model on the GPU if it fits, otherwise the same model on the CPU.
Every skipped or failed option is kept in `load_notes` (shown in Settings), so a fallback to the
CPU is never silent. unload_model() also cancels a load that is still running.
"""
import gc
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.core.llama_sidecar import SidecarError, llama_sidecar

AUTO_GPU_ORDER = ("heavy", "balanced", "lightweight")
AUTO_CPU_ORDER = ("lightweight",)
_DISABLED = "local models are switched off (SENTINEL_DISABLE_LLAMA=1)"
_CANCELLED = "loading was cancelled because Sentinel had to free resources"


class AIService:
    _instance = None

    def __init__(self):
        self.llm = None
        self.engine: Optional[str] = None                      # "gpu" or "cpu" while a model is loaded
        self.active_profile: Optional[Dict[str, Any]] = None   # profile of the loaded model
        self.loaded_profile_id: Optional[str] = None
        self.model_path = None
        self.load_notes: List[str] = []                        # why better options were skipped
        self.last_load_error: Optional[str] = None
        self._llama_cls = None
        disabled = os.environ.get("SENTINEL_DISABLE_LLAMA") == "1"
        self._llama_available = False if disabled else None    # CPU binding; None = not tried yet
        self._binding_error: Optional[str] = _DISABLED if disabled else None
        self._epoch = 0                                        # bumped by unload_model()
        self.lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── loading ──────────────────────────────────────────────────
    def load_model(self) -> bool:
        """Load the active profile's model (plan above). Returns True when a model is ready."""
        with self.lock:
            if self.llm is not None:
                return True
            epoch = self._epoch
            from app.core.model_registry import model_registry
            steps, notes = self._plan(model_registry.get_active_id(), model_registry)
            for pid, profile, path, engine in steps:
                if self._epoch != epoch:
                    notes.append(_CANCELLED)
                    break
                name = profile.get("name", pid)
                try:
                    llm = self._start(engine, profile, path)
                except Exception as e:
                    notes.append(f"{name} on the {engine.upper()}: {e}")
                    continue
                if self._epoch != epoch:          # unloaded (PC busy / paused) while this was loading
                    self._dispose(llm, engine)
                    notes.append(_CANCELLED)
                    break
                self.llm, self.engine = llm, engine
                self.active_profile, self.loaded_profile_id, self.model_path = profile, pid, path
                self.load_notes, self.last_load_error = notes, None
                print(f"[AI Service] Loaded {name} on the {engine.upper()}.")
                return True
            self.load_notes = notes
            self.last_load_error = "; ".join(notes) if notes else "no model profile is configured"
            print(f"[AI Service] No model could be loaded: {self.last_load_error}")
            return False

    def _plan(self, active_id: str, registry) -> Tuple[List[Tuple[str, Dict[str, Any], Any, str]], List[str]]:
        """Ordered (profile id, profile, model path, engine) options, plus notes on skipped ones."""
        profiles = registry.get_all_profiles()
        if active_id == "auto":
            orders = (("gpu", AUTO_GPU_ORDER), ("cpu", AUTO_CPU_ORDER))
        else:
            orders = (("gpu", (active_id,)), ("cpu", (active_id,)))
        steps, notes = [], []
        gpu_reason = llama_sidecar.unavailable_reason()
        if gpu_reason:
            notes.append(f"GPU engine: {gpu_reason}")
        for engine, ids in orders:
            if engine == "gpu" and gpu_reason:
                continue
            for pid in ids:
                profile = profiles.get(pid)
                if not profile or not profile.get("filename"):
                    continue
                path = registry.get_model_path(profile["filename"])
                if not path.exists():
                    note = f"{profile.get('name', pid)}: model file not downloaded"
                    if note not in notes:
                        notes.append(note)
                    continue
                steps.append((pid, profile, path, engine))
        return steps, notes

    def _start(self, engine: str, profile: Dict[str, Any], path):
        n_ctx = int(profile.get("n_ctx", 2048))
        if engine == "gpu":
            ok, why = llama_sidecar.fits(path, n_ctx)
            if not ok:
                raise SidecarError(why)
            return llama_sidecar.start(path, n_ctx=n_ctx, n_gpu_layers=99)
        if not self._binding_ready():
            raise RuntimeError(self._binding_error or "the CPU engine (llama_cpp) is unavailable")
        return self._llama_cls(
            model_path=str(path),
            n_ctx=n_ctx,
            n_threads=int(profile.get("n_threads", 4)),
            n_gpu_layers=0,          # this binding build has no GPU offload; the GPU engine is separate
            verbose=False,
        )

    def _binding_ready(self) -> bool:
        if self._llama_available is None:
            if os.environ.get("SENTINEL_DISABLE_LLAMA") == "1":
                self._llama_available, self._binding_error = False, _DISABLED
            else:
                try:
                    from llama_cpp import Llama
                    self._llama_cls, self._llama_available = Llama, True
                except (OSError, RuntimeError, ImportError) as e:
                    self._llama_available, self._binding_error = False, f"llama_cpp unavailable: {e}"
                    print(f"[AI Service] {self._binding_error}")
        return bool(self._llama_available)

    def _dispose(self, llm, engine: str) -> None:
        if engine == "gpu":
            llama_sidecar.stop()
        del llm
        gc.collect()

    def unload_model(self):
        """Free the model's RAM or VRAM. Safe any time, also while a load is still running."""
        self._epoch += 1
        llm, engine = self.llm, self.engine
        self.llm = None
        self.engine = None
        self.loaded_profile_id = None
        llama_sidecar.stop()             # also ends a GPU start that is still in progress
        if llm is not None:
            del llm
            gc.collect()
            print(f"[AI Service] Model unloaded ({(engine or '').upper()} memory freed).")

    def check_engine(self) -> None:
        """Called by the resource governor every few seconds: notices a GPU engine that died."""
        if self.engine == "gpu" and self.llm is not None and not llama_sidecar.running():
            self.unload_model()
            self.last_load_error = ("the GPU engine stopped unexpectedly (details in logs/llama-server.log); "
                                    "load the model again")
            print(f"[AI Service] {self.last_load_error}")

    def loaded_info(self) -> Optional[Dict[str, Any]]:
        if self.llm is None:
            return None
        return {"profile_id": self.loaded_profile_id, "name": (self.active_profile or {}).get("name"),
                "engine": self.engine, "notes": list(self.load_notes)}

    # ── inference ────────────────────────────────────────────────
    def generate_stream(self, prompt: str, history: list = None, system_prompt: str = None):
        # A single local model must never be advanced by two chat workers at once.
        with self.lock:
            yield from self._generate_stream(prompt, history, system_prompt)

    def _generate_stream(self, prompt: str, history: list = None, system_prompt: str = None):
        """Generates a streaming response from the model, considering conversation history."""
        from app.core.resource_governor import resource_governor, SystemState
        if resource_governor.state in [SystemState.EMERGENCY, SystemState.HIGH_LOAD]:
            yield f"\n[System Error: Cannot process request. Sentinel is in {resource_governor.state.value} mode to protect system stability.]"
            return

        if resource_governor.state == SystemState.USER_PAUSED:
            yield "\n[System Error: Sentinel background tasks and AI inference are currently paused by the user.]"
            return

        llm = self.llm
        if llm is None:
            yield "SYSTEM: Error - Model is not loaded. Please wait for the system to initialize."
            return

        from app.core import prompting
        if system_prompt is None:
            system_prompt = prompting.build_system_prompt()

        # The owner's message is already the last entry of `history` (it is saved before the
        # history is read); `prompt` is only an extra follow-up instruction, so never repeat it.
        if history and prompt is not None and history[-1].get("role") == "user" \
                and str(history[-1].get("content", "")) == str(prompt):
            prompt = None
        family = prompting.chat_family(getattr(self, "active_profile", None))
        formatted_prompt = prompting.format_chat(family, system_prompt, history or [], prompt)

        try:
            stream = llm(
                prompt=formatted_prompt,
                max_tokens=512,
                stop=prompting.STOP_TOKENS[family],
                stream=True
            )

            for chunk in stream:
                token = chunk["choices"][0]["text"]
                if token:
                    yield token
        except Exception as e:
            yield f"\n[Inference Error: {e}]"


ai_service = AIService.get_instance()
