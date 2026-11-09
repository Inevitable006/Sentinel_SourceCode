"""Code analysis tools: outline, stats, imports, references."""
import os

import pytest

from app.core.secure_runner import secure_runner
from app.core.tool_registry import is_failure


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_FILES", str(tmp_path))
    from app.core.skill_router import skill_router
    if "code_assistant" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()

    # Python project
    py_dir = tmp_path / "myapp"
    py_dir.mkdir()
    (py_dir / "main.py").write_text(
        "import os\nimport json\nfrom pathlib import Path\n\n"
        "class App:\n    def __init__(self):\n        pass\n\n"
        "    def run(self):\n        pass\n\n"
        "    async def start(self):\n        pass\n\n"
        "def helper():\n    return 42\n\n"
        "async def async_helper():\n    return 99\n"
    )
    (py_dir / "utils.py").write_text(
        "from myapp.main import App, helper\n\n"
        "def format_name(name):\n    return name.strip()\n\n"
        "class Formatter:\n    pass\n"
    )

    # JS project
    js_dir = tmp_path / "frontend"
    js_dir.mkdir()
    (js_dir / "app.js").write_text(
        "import React from 'react';\n"
        "const { useState } = require('react');\n\n"
        "export class Dashboard {\n    constructor() {}\n}\n\n"
        "export function render() {\n    return null;\n}\n\n"
        "const fetchData = async (url) => {\n    return fetch(url);\n};\n\n"
        "export async function init() {\n    await fetchData('/api');\n}\n"
    )
    (js_dir / "utils.ts").write_text(
        "import { Dashboard } from './app';\n\n"
        "export function formatDate(d: Date): string {\n    return d.toISOString();\n}\n\n"
        "export class Helper {\n    static greet() { return 'hi'; }\n}\n\n"
        "const calculate = (a: number, b: number) => a + b;\n"
    )

    return tmp_path


def approve(tool, args):
    first = secure_runner.execute(tool, args, "code", force_confirmation=True)
    assert first["status"] == "needs_confirmation", first
    return secure_runner.execute(tool, args, "code", token=first["token"])


# ── code_outline tests ─────────────────────────────────────────────────────────

class TestCodeOutline:
    def test_python_outline(self):
        result = approve("skill_code_outline", {"path": "myapp/main.py"})
        assert result["status"] == "success"
        data = result["data"]
        assert "class App" in data
        assert "def __init__" in data
        assert "def run" in data
        assert "async def start" in data
        assert "def helper" in data
        assert "async def async_helper" in data

    def test_python_outline_shows_line_numbers(self):
        result = approve("skill_code_outline", {"path": "myapp/main.py"})
        lines = result["data"].strip().splitlines()
        # Each line should start with a line number
        for line in lines:
            stripped = line.strip()
            assert stripped[0].isdigit(), f"Expected line number, got: {line}"

    def test_python_outline_indentation(self):
        result = approve("skill_code_outline", {"path": "myapp/main.py"})
        data = result["data"]
        # Methods inside the class should be indented
        for line in data.splitlines():
            if "def __init__" in line or "def run" in line or "async def start" in line:
                # These are methods, they should have indent
                assert "  def" in line or "  async def" in line

    def test_js_outline(self):
        result = approve("skill_code_outline", {"path": "frontend/app.js"})
        assert result["status"] == "success"
        data = result["data"]
        assert "class Dashboard" in data
        assert "function render" in data
        assert "const fetchData" in data
        assert "function init" in data

    def test_ts_outline(self):
        result = approve("skill_code_outline", {"path": "frontend/utils.ts"})
        assert result["status"] == "success"
        data = result["data"]
        assert "function formatDate" in data
        assert "class Helper" in data
        assert "const calculate" in data

    def test_outline_unsupported_extension(self, project):
        (project / "data.json").write_text('{"key": "value"}')
        result = approve("skill_code_outline", {"path": "data.json"})
        assert result["status"] == "error"
        assert "not supported" in result["message"]

    def test_outline_nonexistent_file(self):
        result = approve("skill_code_outline", {"path": "nope.py"})
        assert result["status"] == "error"

    def test_outline_empty_file(self, project):
        (project / "empty.py").write_text("")
        result = approve("skill_code_outline", {"path": "empty.py"})
        assert result["status"] == "success"
        assert "No functions or classes" in result["data"]


# ── code_stats tests ───────────────────────────────────────────────────────────

class TestCodeStats:
    def test_stats_myapp(self):
        result = approve("skill_code_stats", {"path": "myapp"})
        assert result["status"] == "success"
        data = result["data"]
        assert "Project: myapp" in data
        assert "Files: 2" in data
        assert "Functions/methods:" in data
        assert "Classes:" in data
        assert ".py: 2" in data

    def test_stats_frontend(self):
        result = approve("skill_code_stats", {"path": "frontend"})
        assert result["status"] == "success"
        data = result["data"]
        assert "Files: 2" in data
        assert "Functions/methods:" in data
        assert "Classes:" in data

    def test_stats_workspace_root(self):
        result = approve("skill_code_stats", {"path": ""})
        assert result["status"] == "success"
        data = result["data"]
        assert "Files: 4" in data

    def test_stats_counts_lines(self):
        result = approve("skill_code_stats", {"path": "myapp"})
        data = result["data"]
        # Lines: should be a positive number
        for line in data.splitlines():
            if line.startswith("Lines:"):
                count = int(line.split(":")[1].strip().replace(",", ""))
                assert count > 0

    def test_stats_counts_functions(self):
        result = approve("skill_code_stats", {"path": "myapp"})
        data = result["data"]
        for line in data.splitlines():
            if line.startswith("Functions/methods:"):
                count = int(line.split(":")[1].strip())
                # main.py: __init__, run, start, helper, async_helper = 5
                # utils.py: format_name = 1
                assert count == 6

    def test_stats_counts_classes(self):
        result = approve("skill_code_stats", {"path": "myapp"})
        data = result["data"]
        for line in data.splitlines():
            if line.startswith("Classes:"):
                count = int(line.split(":")[1].strip())
                # main.py: App = 1, utils.py: Formatter = 1
                assert count == 2

    def test_stats_empty_folder(self, project):
        empty = project / "empty_proj"
        empty.mkdir()
        result = approve("skill_code_stats", {"path": "empty_proj"})
        assert result["status"] == "success"
        assert "No code files" in result["data"]

    def test_stats_nonexistent_folder(self):
        result = approve("skill_code_stats", {"path": "nope"})
        assert result["status"] == "error"


# ── find_imports tests ─────────────────────────────────────────────────────────

class TestFindImports:
    def test_python_imports(self):
        result = approve("skill_find_imports", {"path": "myapp"})
        assert result["status"] == "success"
        data = result["data"]
        assert "import os" in data
        assert "import json" in data
        assert "from pathlib import Path" in data
        assert "from myapp.main import App, helper" in data

    def test_js_imports(self):
        result = approve("skill_find_imports", {"path": "frontend"})
        assert result["status"] == "success"
        data = result["data"]
        assert "react" in data
        assert "./app" in data

    def test_imports_grouped_by_file(self):
        result = approve("skill_find_imports", {"path": "myapp"})
        data = result["data"]
        # Should have file headers ending with ':'
        file_headers = [l for l in data.splitlines() if l.endswith(":")]
        assert len(file_headers) == 2  # main.py and utils.py

    def test_imports_empty_folder(self, project):
        empty = project / "no_imports"
        empty.mkdir()
        (empty / "readme.md").write_text("# Hello")
        result = approve("skill_find_imports", {"path": "no_imports"})
        assert result["status"] == "success"
        assert "No imports" in result["data"]


# ── find_references tests ──────────────────────────────────────────────────────

class TestFindReferences:
    def test_find_symbol_across_files(self):
        result = approve("skill_find_references", {"symbol": "App", "path": "myapp"})
        assert result["status"] == "success"
        data = result["data"]
        # Should find 'App' in main.py (class definition) and utils.py (import)
        assert "main.py" in data
        assert "utils.py" in data

    def test_find_helper(self):
        result = approve("skill_find_references", {"symbol": "helper", "path": "myapp"})
        assert result["status"] == "success"
        data = result["data"]
        assert "main.py" in data
        assert "utils.py" in data

    def test_word_boundary_matching(self, project):
        (project / "myapp" / "boundary.py").write_text(
            "def address():\n    pass\n\ndef add():\n    x = add()\n")
        result = approve("skill_find_references", {"symbol": "add", "path": "myapp"})
        data = result["data"]
        # 'add' should match def add and x = add(), not 'address'
        lines = [l for l in data.splitlines() if "boundary.py" in l]
        for line in lines:
            # none of the matched lines should be the 'address' definition alone
            assert "add" in line

    def test_no_references(self):
        result = approve("skill_find_references", {"symbol": "nonexistent_symbol_xyz", "path": "myapp"})
        assert result["status"] == "success"
        assert "No references" in result["data"]

    def test_invalid_symbol(self):
        result = approve("skill_find_references", {"symbol": "", "path": "myapp"})
        assert result["status"] == "error"

    def test_symbol_with_special_chars(self):
        result = approve("skill_find_references", {"symbol": "a+b", "path": "myapp"})
        assert result["status"] == "error"

    def test_references_in_js(self):
        result = approve("skill_find_references", {"symbol": "Dashboard", "path": "frontend"})
        assert result["status"] == "success"
        data = result["data"]
        assert "app.js" in data
        assert "utils.ts" in data


# ── Tier check ─────────────────────────────────────────────────────────────────

def test_new_tools_are_tier_2():
    from app.core.tool_registry import tool_registry
    for name in ("skill_code_outline", "skill_code_stats", "skill_find_imports", "skill_find_references"):
        tool = tool_registry.get_tool(name)
        assert tool is not None, f"{name} not registered"
        assert int(tool.tool_schema.risk_tier) == 2, f"{name} should be Tier 2"
