"""Writes backend/skill-hashes.json: the SHA-256 of every built-in skill module.

Run after you intentionally change a skill:
    backend\\.venv\\Scripts\\python tools\\pin_skills.py
Review the diff of skill-hashes.json before committing it; a changed hash you did not expect
means a skill file was modified.
"""
import hashlib
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def main():
    modules = {}
    for init in sorted((BACKEND / "skills").glob("*/__init__.py")):
        modules[f"skills.{init.parent.name}"] = hashlib.sha256(init.read_bytes()).hexdigest()
    out = BACKEND / "skill-hashes.json"
    out.write_text(json.dumps({"algorithm": "sha256", "modules": modules}, indent=2) + "\n", encoding="utf-8")
    for name, digest in modules.items():
        print(f"{digest[:16]}  {name}")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
