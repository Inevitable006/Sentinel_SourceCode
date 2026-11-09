"""
GPU engine benchmark (Windows): starts Sentinel's llama-server sidecar for each downloaded model,
streams one answer and prints load time, time to first chunk, chunk rate and VRAM use.
Stream chunks are not guaranteed to equal tokenizer tokens; this is not a tokens/s benchmark.

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
QUESTION = "Explain in about 120 words why the sky is blue."


def benchmark_prompt(filename):
    if filename.startswith('llama-3.2-'):
        return (f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n{QUESTION}"
                "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
                ['<|eot_id|>', '<|end_of_text|>'])
    return (f"<|im_start|>user\n{QUESTION}<|im_end|>\n<|im_start|>assistant\n", ['<|im_end|>'])


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
    failed = False
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
            failed = True
            continue
        load_s = time.time() - t0
        try:
            t1, first, n = time.time(), None, 0
            prompt, stops = benchmark_prompt(fname)
            for _ in llm(prompt=prompt, max_tokens=200, stop=stops):
                n += 1
                first = first or time.time()
            gen_s = time.time() - (first or t1)
            if first is None:
                print(f"BENCH {label}: FAILED: no streamed output")
                failed = True
                continue
            print(f"BENCH {label}: load {load_s:.1f}s | first chunk {first - t1:.2f}s | "
                  f"{n} chunks at {max(0, n - 1) / gen_s if gen_s > 0 else 0:.1f} chunks/s after first chunk "
                  f"(not tokenizer tokens/s) | VRAM {sc.own_vram_mb() / 1024:.2f} GB")
        finally:
            sc.stop()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
