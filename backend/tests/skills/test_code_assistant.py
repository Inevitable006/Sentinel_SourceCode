"""Coding skill pack: explore code in Sentinel Workspace; run tests in the contained runner."""
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
    app_dir = tmp_path / "calc"
    (app_dir / "node_modules").mkdir(parents=True)
    (app_dir / "node_modules" / "junk.js").write_text("ignore me")
    (app_dir / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b\n")
    (app_dir / "test_calc.py").write_text(
        "import unittest\nfrom calc import add, div\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
        "    def test_div(self):\n        self.assertEqual(div(6, 3), 2)\n")
    return tmp_path


def approve(tool, args):
    first = secure_runner.execute(tool, args, "code", force_confirmation=True)
    assert first["status"] == "needs_confirmation", first
    return secure_runner.execute(tool, args, "code", token=first["token"])


def test_list_skips_dependency_folders():
    out = approve("skill_list_code_files", {"path": "calc"})["data"]
    assert "calc.py" in out and "test_calc.py" in out and "node_modules" not in out


def test_search_and_read():
    hits = approve("skill_search_code", {"query": "def div", "path": ""})["data"]
    assert hits.strip() == "calc" + os.sep + "calc.py:5: def div(a, b):"
    lines = approve("skill_read_code", {"path": "calc/calc.py", "start_line": 1, "end_line": 2})["data"]
    assert lines.splitlines() == ["    1  def add(a, b):", "    2      return a + b", "… (more lines below)"]


def test_reading_outside_the_workspace_is_refused(project):
    result = approve("skill_read_code", {"path": "..\\..\\secret.txt", "start_line": 1, "end_line": 5})
    assert result["status"] == "error" and "Only files inside" in result["message"]


@pytest.mark.parametrize("content", ["x" * 100_000, ("x" * 200 + "\n") * 200],
                         ids=["long-line", "many-lines"])
def test_code_read_output_is_bounded(project, content):
    (project / "calc" / "large.js").write_text(content)
    result = approve("skill_read_code", {"path": "calc/large.js"})
    assert result["status"] == "success"
    assert len(result["data"]) < 8_200
    assert result["data"].startswith("    1  ")
    assert "output limit reached at line" in result["data"]


@pytest.mark.skipif(os.name != "nt", reason="contained runner is Windows-only")
def test_tests_run_for_real_and_failures_are_reported(project):
    ok = approve("skill_run_python_tests", {"path": "calc"})
    assert ok["status"] == "success" and "RESULT: ran=2 failures=0 errors=0" in ok["data"]
    (project / "calc" / "calc.py").write_text("def add(a, b):\n    return a - b\n\n\ndef div(a, b):\n    return a / b\n")
    bad = approve("skill_run_python_tests", {"path": "calc"})
    assert bad["status"] == "error" and "failures=1" in bad["message"]


@pytest.mark.skipif(os.name != "nt", reason="contained runner is Windows-only")
def test_test_code_cannot_escape_the_project_folder(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "stolen.txt"
    (project / "calc" / "test_evil.py").write_text(
        "import unittest\nclass E(unittest.TestCase):\n"
        f"    def test_x(self):\n        open(r'{outside}', 'w').write('x')\n")
    result = approve("skill_run_python_tests", {"path": "calc"})
    assert result["status"] == "error" and not outside.exists()


@pytest.mark.skipif(os.name != "nt", reason="contained runner is Windows-only")
def test_no_matching_tests_is_not_success(project):
    result = approve("skill_run_python_tests", {"path": "calc", "pattern": "missing_*.py"})
    assert result["status"] == "error"
    assert "RESULT: ran=0" in result["message"]
    assert "no tests executed" in result["message"]


@pytest.mark.skipif(os.name != "nt", reason="contained runner is Windows-only")
def test_all_skipped_tests_is_not_success(project):
    (project / "calc" / "test_skipped.py").write_text(
        "import unittest\n@unittest.skip('not configured')\n"
        "class T(unittest.TestCase):\n"
        "    def test_skipped(self):\n        pass\n")
    result = approve("skill_run_python_tests", {"path": "calc", "pattern": "test_skipped.py"})
    assert result["status"] == "error"
    assert "RESULT: ran=1 failures=0 errors=0 skipped=1" in result["message"]
    assert "no tests executed" in result["message"]
    mixed = approve("skill_run_python_tests", {"path": "calc"})
    assert mixed["status"] == "success"
    assert "RESULT: ran=3 failures=0 errors=0 skipped=1" in mixed["data"]


def test_running_tests_needs_tier_3():
    from app.core.tool_registry import tool_registry
    assert int(tool_registry.get_tool("skill_run_python_tests").tool_schema.risk_tier) == 3
    assert int(tool_registry.get_tool("skill_read_code").tool_schema.risk_tier) == 2
