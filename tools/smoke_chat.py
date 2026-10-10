"""
End-to-end backend smoke test (Windows, real model, no Electron).

Starts run_server.py with a throwaway session token and an ISOLATED data
directory (so your real chat history / memory DB is never touched), loads the
active model, sends one chat message over the WebSocket and reports what came
back plus rough speed. Model files are hard-linked, not copied. With the 1.5B
and 7B models linked, the default "auto" profile exercises the GPU engine
(7B on the GPU when it fits). At the end the backend is killed hard, and the
test checks that Windows also ended its llama-server (Job Object).

Usage:  backend\\.venv\\Scripts\\python.exe tools\\smoke_chat.py
"""
import json, os, secrets, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
MODELS = [m.strip() for m in os.environ.get(
    "SMOKE_MODELS", "qwen2.5-1.5b-instruct-q4_k_m.gguf,qwen2.5-7b-instruct-q4_k_m.gguf").split(",") if m.strip()]
PORT = int(os.environ.get("SMOKE_PORT", "8765"))
TOKEN = secrets.token_hex(32)


def http(method, path, body=None, auth=True, timeout=10):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method)
    if auth:
        req.add_header("X-Sentinel-Session", TOKEN)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
        return r.status, json.loads(r.read() or b"{}")


def main():
    real_models = Path(os.environ["APPDATA"]) / "sentinel" / "models"
    tmp = Path(tempfile.mkdtemp(prefix="sentinel_smoke_"))
    links = []
    for name in MODELS:
        if (real_models / name).exists():
            link = tmp / "sentinel" / "models" / name
            link.parent.mkdir(parents=True, exist_ok=True)
            os.link(real_models / name, link)             # hard link: no copy, no change to the original
            links.append(link)
    print("models linked:", [l.name for l in links] or "NONE")
    env = dict(os.environ, APPDATA=str(tmp), SENTINEL_SESSION_TOKEN=TOKEN, SENTINEL_BACKEND_PORT=str(PORT))
    log_path = tmp / "server.log"
    proc = subprocess.Popen([sys.executable, "run_server.py"], cwd=BACKEND, env=env,
                            stdout=open(log_path, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    ok = False
    try:
        for _ in range(60):
            try:
                st, h = http("GET", "/health", auth=False, timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("backend did not come up")
        print("health:", h)

        try:
            http("GET", "/api/governor/status", auth=False)
            raise RuntimeError("governor status reachable without a session token")
        except urllib.error.HTTPError as e:
            if e.code not in (401, 422):
                raise RuntimeError(f"unexpected unauthenticated governor response: HTTP {e.code}") from None
            print(f"governor status without token -> HTTP {e.code} (expected 401/422)")

        st, u = http("GET", "/api/unlock/status")
        print("unlock state before setup:", u.get("state"))
        st, r = http("POST", "/api/unlock/setup", {"pin": secrets.token_hex(8)}, timeout=60)
        if st != 200 or not r.get("recovery_key"):
            raise RuntimeError("isolated owner setup did not issue a recovery key")
        print("owner setup: ok (recovery key issued)")

        t0 = time.time()
        st, r = http("POST", "/api/models/load", timeout=300)
        print(f"model load: {r} in {time.time() - t0:.1f}s")
        print("health after load:", http("GET", "/health", auth=False)[1])

        import websocket  # websocket-client
        ws = websocket.create_connection(f"ws://127.0.0.1:{PORT}/ws/chat", subprotocols=["sentinel.v1", TOKEN], timeout=180)
        prompt = "In one short sentence, say hello and tell me your name."
        ws.send(json.dumps({"text": prompt, "request_id": "smoke-1"}))
        reply, first_tok, t_start, n = "", None, time.time(), 0
        completed = False
        while True:
            msg = json.loads(ws.recv())
            if msg.get("type") == "reply_chunk":
                n += 1
                first_tok = first_tok or time.time()
                reply += msg.get("token", "")
            elif msg.get("type") == "error":
                print("ERROR from backend:", msg); break
            elif msg.get("type") == "state" and msg.get("state") in ("COMPLETED", "CANCELLED"):
                completed = msg.get("state") == "COMPLETED"
                break
        ws.close()
        gen = time.time() - (first_tok or t_start)
        print(f"prompt: {prompt}")
        print(f"reply : {reply.strip()[:400]}")
        print(f"chunks: {n}, time to first token: {((first_tok or time.time()) - t_start):.1f}s, "
              f"~{n / gen if gen > 0 else 0:.1f} chunks/s")
        ok = completed and bool(reply.strip())
    finally:
        proc.terminate()                                   # hard kill: no clean shutdown on purpose
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:                                               # the Job Object must have ended llama-server
            import psutil
            bin_dir = str(BACKEND / "llama-bin").lower()
            left, deadline = [], time.time() + 10
            while time.time() < deadline:
                left = [p.pid for p in psutil.process_iter(["name", "exe"])
                        if (p.info["name"] or "").lower() == "llama-server.exe"
                        and (p.info["exe"] or "").lower().startswith(bin_dir)]
                if not left:
                    break
                time.sleep(0.5)
            print("llama-server still running after the backend was killed:", left or "none")
            ok = ok and not left
        except ImportError:
            pass
        tail = log_path.read_text(encoding="utf-8", errors="replace").replace(TOKEN, "<token>")
        print("---- server log (last 25 lines, token redacted) ----")
        print("\n".join(tail.splitlines()[-25:]))
        for link in links:
            link.unlink()                                  # remove only our hard links
        shutil.rmtree(tmp, ignore_errors=True)            # our own temp dir
    print("SMOKE RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
