"""
End-to-end backend smoke test (Windows, real model, no Electron).

Starts run_server.py with a throwaway session token and an ISOLATED data
directory (so your real chat history / memory DB is never touched), loads the
active model, sends one chat message over the WebSocket and reports what came
back plus rough speed. The model file is hard-linked, not copied.

Usage:  backend\\.venv\\Scripts\\python.exe tools\\smoke_chat.py
"""
import json, os, secrets, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
MODEL = os.environ.get("SMOKE_MODEL", "qwen2.5-1.5b-instruct-q4_k_m.gguf")
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
    link = tmp / "sentinel" / "models" / MODEL
    link.parent.mkdir(parents=True)
    os.link(real_models / MODEL, link)                     # hard link: no copy, no change to the original
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
            print("SECURITY: governor status reachable WITHOUT token  -> FAIL")
        except urllib.error.HTTPError as e:
            print(f"governor status without token -> HTTP {e.code} (expected 401/422)")

        t0 = time.time()
        st, r = http("POST", "/api/models/load", timeout=300)
        print(f"model load: {r} in {time.time() - t0:.1f}s")
        print("health after load:", http("GET", "/health", auth=False)[1])

        import websocket  # websocket-client
        ws = websocket.create_connection(f"ws://127.0.0.1:{PORT}/ws/chat?token={TOKEN}", timeout=180)
        prompt = "In one short sentence, say hello and tell me your name."
        ws.send(json.dumps({"text": prompt, "request_id": "smoke-1"}))
        reply, first_tok, t_start, n = "", None, time.time(), 0
        while True:
            msg = json.loads(ws.recv())
            if msg.get("type") == "reply_chunk":
                n += 1
                first_tok = first_tok or time.time()
                reply += msg.get("token", "")
            elif msg.get("type") == "error":
                print("ERROR from backend:", msg); break
            elif msg.get("type") == "state" and msg.get("state") in ("COMPLETED", "CANCELLED"):
                break
        ws.close()
        gen = time.time() - (first_tok or t_start)
        print(f"prompt: {prompt}")
        print(f"reply : {reply.strip()[:400]}")
        print(f"chunks: {n}, time to first token: {((first_tok or time.time()) - t_start):.1f}s, "
              f"~{n / gen if gen > 0 else 0:.1f} chunks/s")
        ok = bool(reply.strip())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        tail = log_path.read_text(encoding="utf-8", errors="replace").replace(TOKEN, "<token>")
        print("---- server log (last 25 lines, token redacted) ----")
        print("\n".join(tail.splitlines()[-25:]))
        link.unlink()                                      # remove only our hard link
        shutil.rmtree(tmp, ignore_errors=True)            # our own temp dir
    print("SMOKE RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
