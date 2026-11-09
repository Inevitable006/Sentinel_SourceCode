"""
Skill: code_assistant
Explore and test code inside the Sentinel Workspace folder. Changes go through file_manager
(preview, conflict check, 5-minute undo); tests run in the contained Python runner
(no network, no other programs, only the project folder). Risk Tier: 2 for reading, 3 for running.
"""
import os
import re
from collections import Counter

from app.core import file_ops
from app.core.tool_registry import failed

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode", ".pytest_cache"}
CODE_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".html", ".css", ".java", ".c", ".cpp",
            ".h", ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".sql", ".yml", ".yaml", ".toml", ".ini", ".cfg"}
MAX_FILE_BYTES = 512 * 1024
MAX_FILES = 300
MAX_READ_CHARS = 8_000  # Leave room for guidance below the runner's 10 KB output cap.

# ── Patterns for structural analysis ───────────────────────────────────────────
# Python: def, class, async def
_PY_DEF = re.compile(r"^(\s*)(async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
_PY_CLASS = re.compile(r"^(\s*)class\s+(\w+)", re.MULTILINE)
# JavaScript / TypeScript: function, const/let/var arrow, class, export function
_JS_DEF = re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE)
_JS_ARROW = re.compile(r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>", re.MULTILINE)
_JS_CLASS = re.compile(r"^(\s*)(?:export\s+)?class\s+(\w+)", re.MULTILINE)
# Import patterns
_PY_IMPORT = re.compile(r"^\s*(?:from\s+(\S+)\s+)?import\s+(.+)", re.MULTILINE)
_JS_IMPORT = re.compile(r"""^\s*(?:import\s+.*?from\s+['"]([^'"]+)['"]|(?:const|let|var)\s+.*?=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\))""", re.MULTILINE)


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


def _read_text(filepath: str, limit: int = MAX_FILE_BYTES) -> str:
    """Read a workspace file as text, bounded by limit bytes."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


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
    remaining = MAX_READ_CHARS
    with open(p, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            if n > end:
                out.append("… (more lines below)")
                break
            if n >= start:
                numbered = f"{n:5d}  {line.rstrip()}"
                if len(numbered) + 1 > remaining:
                    out.append(numbered[:max(0, remaining - 1)])
                    out.append(f"… (output limit reached at line {n}; request a smaller range or search for specific text)")
                    break
                out.append(numbered)
                remaining -= len(numbered) + 1
    return "\n".join(out) if out else "(no lines in that range)"


# ── Code outline ───────────────────────────────────────────────────────────────

def _outline_python(text: str) -> list:
    """Extract (line, kind, name, indent) for Python defs and classes."""
    items = []
    for n, line in enumerate(text.splitlines(), 1):
        m = _PY_CLASS.match(line)
        if m:
            items.append((n, "class", m.group(2), len(m.group(1))))
            continue
        m = _PY_DEF.match(line)
        if m:
            kind = "async def" if m.group(2) else "def"
            items.append((n, kind, m.group(3), len(m.group(1))))
    return items


def _outline_js(text: str) -> list:
    """Extract (line, kind, name, indent) for JS/TS definitions."""
    items = []
    for n, line in enumerate(text.splitlines(), 1):
        m = _JS_CLASS.match(line)
        if m:
            items.append((n, "class", m.group(2), len(m.group(1))))
            continue
        m = _JS_DEF.match(line)
        if m:
            items.append((n, "function", m.group(2), len(m.group(1))))
            continue
        m = _JS_ARROW.match(line)
        if m:
            items.append((n, "const", m.group(2), len(m.group(1))))
    return items


def code_outline(path: str) -> str:
    """Extract function/class definitions from a code file with line numbers."""
    try:
        p = file_ops.resolve(path, must_exist=True)
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")
    if not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
        return failed("Error: not a readable code file (or larger than 512 KB).")
    ext = p.suffix.lower()
    text = _read_text(str(p))
    if ext == ".py":
        items = _outline_python(text)
    elif ext in (".js", ".mjs", ".ts", ".tsx", ".jsx"):
        items = _outline_js(text)
    else:
        return failed(f"Error: outline is not supported for {ext} files. Supported: .py, .js, .ts, .tsx, .jsx, .mjs.")

    if not items:
        return "No functions or classes found."
    out = []
    for line_no, kind, name, indent in items:
        prefix = "  " * (indent // 4) if indent else ""
        out.append(f"{line_no:5d}  {prefix}{kind} {name}")
        if len(out) >= 200:
            out.append("… (more definitions omitted)")
            break
    return "\n".join(out)


# ── Code statistics ────────────────────────────────────────────────────────────

def code_stats(path: str = "") -> str:
    """Count files, lines, functions and classes in a project folder."""
    try:
        base, root = _folder(path), file_ops.files_root()
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")

    ext_counts = Counter()
    total_lines = 0
    total_funcs = 0
    total_classes = 0
    total_files = 0

    for full in _walk(base):
        total_files += 1
        ext = os.path.splitext(full)[1].lower()
        ext_counts[ext] += 1
        text = _read_text(full)
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        total_lines += lines

        if ext == ".py":
            total_funcs += len(_PY_DEF.findall(text))
            total_classes += len(_PY_CLASS.findall(text))
        elif ext in (".js", ".mjs", ".ts", ".tsx", ".jsx"):
            total_funcs += len(_JS_DEF.findall(text)) + len(_JS_ARROW.findall(text))
            total_classes += len(_JS_CLASS.findall(text))

        if total_files >= MAX_FILES:
            break

    if total_files == 0:
        return "No code files found."

    folder_name = os.path.relpath(base, root) if base != root else "(workspace root)"
    lines = [f"Project: {folder_name}", f"Files: {total_files}", f"Lines: {total_lines:,}",
             f"Functions/methods: {total_funcs}", f"Classes: {total_classes}", "",
             "By extension:"]
    for ext, count in ext_counts.most_common(15):
        lines.append(f"  {ext}: {count}")
    return "\n".join(lines)


# ── Import / dependency analysis ───────────────────────────────────────────────

def find_imports(path: str = "") -> str:
    """List import/require statements in a project, grouped by file."""
    try:
        base, root = _folder(path), file_ops.files_root()
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")

    out = []
    file_count = 0
    for full in _walk(base):
        ext = os.path.splitext(full)[1].lower()
        if ext not in (".py", ".js", ".mjs", ".ts", ".tsx", ".jsx"):
            continue
        text = _read_text(full)
        imports = []
        if ext == ".py":
            for m in _PY_IMPORT.finditer(text):
                from_mod = m.group(1)
                imported = m.group(2).strip()
                if from_mod:
                    imports.append(f"from {from_mod} import {imported[:120]}")
                else:
                    imports.append(f"import {imported[:120]}")
        else:
            for m in _JS_IMPORT.finditer(text):
                mod = m.group(1) or m.group(2)
                imports.append(mod)

        if imports:
            rel = os.path.relpath(full, root)
            out.append(f"{rel}:")
            for imp in imports[:30]:
                out.append(f"  {imp}")
            if len(imports) > 30:
                out.append(f"  … ({len(imports) - 30} more)")
            file_count += 1
            if file_count >= 50:
                out.append("… (first 50 files)")
                break

    return "\n".join(out) if out else "No imports found."


# ── Symbol reference search ────────────────────────────────────────────────────

def find_references(symbol: str, path: str = "") -> str:
    """Find all usage sites of a named symbol across project files."""
    if not symbol or not re.fullmatch(r"[A-Za-z_]\w{0,99}", symbol):
        return failed("Error: give a valid symbol name (letters, digits, underscore; 1–100 chars).")
    try:
        base, root = _folder(path), file_ops.files_root()
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")

    # Word-boundary match so 'add' doesn't match 'address'
    pattern = re.compile(r"\b" + re.escape(symbol) + r"\b")
    hits = []
    for full in _walk(base):
        ext = os.path.splitext(full)[1].lower()
        if ext not in (".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h",
                        ".cs", ".go", ".rs", ".rb", ".php"):
            continue
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if pattern.search(line):
                        hits.append(f"{os.path.relpath(full, root)}:{n}: {line.strip()[:200]}")
                        if len(hits) >= 80:
                            return "\n".join(hits) + "\n… (first 80 references)"
        except OSError:
            continue

    if not hits:
        return f"No references to '{symbol}' found."
    return "\n".join(hits)


# ── Test runner ────────────────────────────────────────────────────────────────

TEST_RUNNER = """
import sys, unittest
loader = unittest.TestLoader()
suite = loader.discover(start_dir={start!r}, pattern={pattern!r}, top_level_dir={top!r})
result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
print(f"\\nRESULT: ran={{result.testsRun}} failures={{len(result.failures)}} errors={{len(result.errors)}} skipped={{len(result.skipped)}}")
executed = result.testsRun - len(result.skipped)
if executed == 0:
    print("Error: no tests executed. Check the project folder, test pattern, and skip conditions.")
sys.exit(0 if result.wasSuccessful() and executed > 0 else 1)
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
