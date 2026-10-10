"""
Skill: code_assistant
Explore and test code inside the Sentinel Workspace folder. Changes go through file_manager
(preview, conflict check, 5-minute undo); tests run in the contained Python runner
(no network, no other programs, only the project folder). Risk Tier: 2 for reading, 3 for running.
"""
import os
import re

from app.core import file_ops
from app.core.tool_registry import failed

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode", ".pytest_cache"}
CODE_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".html", ".css", ".java", ".c", ".cpp",
            ".h", ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".sql", ".yml", ".yaml", ".toml", ".ini", ".cfg"}
MAX_FILE_BYTES = 512 * 1024
MAX_FILES = 300


def _folder(path: str):
    if not path or path in (".", "/", "\\"):
        return file_ops.files_root()
    p = file_ops.resolve(path, must_exist=True)
    if not p.is_dir():
        raise file_ops.FileOpError(f"{path} is not a folder.")
    return p


def _walk(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.splitext(name)[1].lower() in CODE_EXT and os.path.getsize(full) <= MAX_FILE_BYTES:
                yield full


def list_code_files(path: str = "") -> str:
    try:
        base, root = _folder(path), file_ops.files_root()
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")
    files = []
    for full in _walk(base):
        files.append(f"{os.path.relpath(full, root)}  ({os.path.getsize(full):,} bytes)")
        if len(files) >= MAX_FILES:
            files.append(f"… (stopped at {MAX_FILES} files)")
            break
    return "\n".join(files) if files else "No code files found."


def search_code(query: str, path: str = "") -> str:
    if not query or len(query) > 200:
        return failed("Error: give a search text of 1–200 characters.")
    try:
        base, root = _folder(path), file_ops.files_root()
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")
    needle, hits = query.lower(), []
    for full in _walk(base):
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if needle in line.lower():
                        hits.append(f"{os.path.relpath(full, root)}:{n}: {line.strip()[:200]}")
                        if len(hits) >= 50:
                            return "\n".join(hits) + "\n… (first 50 matches)"
        except OSError:
            continue
    return "\n".join(hits) if hits else f"No matches for {query!r}."


def read_code(path: str, start_line: int = 1, end_line: int = 200) -> str:
    try:
        p = file_ops.resolve(path, must_exist=True)
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")
    if not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
        return failed("Error: not a readable code file (or larger than 512 KB).")
    start, end = max(1, int(start_line)), int(end_line)
    end = min(end, start + 399)
    out = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            if n > end:
                out.append("… (more lines below)")
                break
            if n >= start:
                out.append(f"{n:5d}  {line.rstrip()}")
    return "\n".join(out) if out else "(no lines in that range)"


TEST_RUNNER = """
import sys, unittest
loader = unittest.TestLoader()
suite = loader.discover(start_dir={start!r}, pattern={pattern!r}, top_level_dir={top!r})
result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
print(f"\\nRESULT: ran={{result.testsRun}} failures={{len(result.failures)}} errors={{len(result.errors)}} skipped={{len(result.skipped)}}")
sys.exit(0 if result.wasSuccessful() else 1)
"""


def run_python_tests(path: str = "", pattern: str = "test*.py") -> str:
    """Runs unittest-style tests of a project folder inside the contained runner."""
    if not re.fullmatch(r"[\w*.\-]{1,60}", pattern or ""):
        return failed("Error: invalid test file pattern.")
    try:
        base = _folder(path)
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")
    from app.core.python_sandbox import run_python
    code = TEST_RUNNER.format(start=str(base), pattern=pattern, top=str(base))
    ok, out, err = run_python(code, workspace=base)
    text = (out + ("\n" + err if err else "")).strip()
    return text if ok else failed(text or "Error: the tests could not run.")
