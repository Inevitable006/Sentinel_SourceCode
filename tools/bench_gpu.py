"""
GPU engine benchmark (Windows): starts Sentinel's llama-server sidecar for each downloaded model,
streams one answer and prints load time, time to first token, speed and the VRAM it used.

Your model files are only read. Logs go to a temporary folder, never into your Sentinel data.
The same safety checks as in the app run (binary hashes, 127.0.0.1, API key, port owner).

Usage:  backend\\.venv\\Scripts\\python.exe tools\\bench_gpu.py      (or tools\\check.bat -Only gpu)
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_MODELS = Path(os.environ["APPDATA"]) / "sentinel" / "models"
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="sentinel_bench_")      # logs go here, not to your data
sys.path.insert(0, str(ROOT / "backend"))

from app.core import llama_sidecar as ls  # noqa: E402

MODELS = [("Qwen 2.5 1.5B", "qwen2.5-1.5b-instruct-q4_k_m.gguf", 2048),
          ("Llama 3.2 3B", "llama-3.2-3b-instruct-q4_k_m.gguf", 4096),
          ("Qwen 2.5 7B", "qwen2.5-7b-instruct-q4_k_m.gguf", 4096)]
PROMPT = "<|im_start|>user\nExplain in about 120 words why the sky is blue.<|im_end|>\n<|im_start|>assistant\n"


def main() -> int:
    sc = ls.LlamaSidecar()
    reason = sc.unavailable_reason()
    if reason:
        print("BENCH GPU engine unavailable:", reason)
        return 1
    t0 = time.time()
    exe = ls.ensure_binaries()
    print(f"BENCH binaries verified against llama-bin.sha256.json in {time.time() - t0:.1f}s")
    dirs, _ = ls.cuda_dll_dirs()
    ver = subprocess.run([str(exe), "--version"], env=ls.build_env("unused-key-000", dirs), cwd=str(ls.BIN_DIR),
                         capture_output=True, text=True, timeout=120, creationflags=ls._creation_flags())
    lines = [ln.strip() for ln in (ver.stdout + ver.stderr).splitlines() if ln.strip()]
    print("BENCH llama-server:", " | ".join(lines[-3:]))
    for label, fname, n_ctx in MODELS:
        path = REAL_MODELS / fname
        if not path.exists():
            print(f"BENCH {label}: not downloaded")
            continue
        ok, why = sc.fits(path, n_ctx)
        print(f"BENCH {label}: fit check {'OK' if ok else 'NO'} ({why})")
        if not ok:
            continue
        t0 = time.time()
        try:
            llm = sc.start(path, n_ctx=n_ctx)
        except ls.SidecarError as e:
            print(f"BENCH {label}: start FAILED: {e}")
            continue
        load_s = time.time() - t0
        try:
            t1, first, n = time.time(), None, 0
            for _ in llm(prompt=PROMPT, max_tokens=200, stop=["<|im_end|>"]):
                n += 1
                first = first or time.time()
            gen_s = time.time() - (first or t1)
            print(f"BENCH {label}: load {load_s:.1f}s | first token {(first or t1) - t1:.2f}s | "
                  f"{n} tokens at {n / gen_s if gen_s > 0 else 0:.1f} tok/s | VRAM {sc.own_vram_mb() / 1024:.2f} GB")
        finally:
            sc.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
