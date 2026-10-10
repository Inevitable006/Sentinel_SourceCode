"""F22: list_directory follows the configured workspace, not an old hard-coded folder."""
import json
import os

from app.core.paths import workspace_root
from app.core.secure_runner import run_system_op
from app.core.tool_registry import is_failure


def test_default_root_is_this_project():
    assert (workspace_root() / "backend" / "app" / "core" / "paths.py").is_file()


def test_configured_workspace_can_be_listed(tmp_path, monkeypatch):
    (tmp_path / "note.txt").write_text("x")
    monkeypatch.setenv("SENTINEL_WORKSPACE", str(tmp_path))
    result = run_system_op("list_directory", str(tmp_path))
    assert not is_failure(result)
    assert [e["Name"] for e in json.loads(result)] == ["note.txt"]
    assert not is_failure(run_system_op("list_directory", ""))


def test_escapes_are_blocked(tmp_path, monkeypatch):
    ws = tmp_path / "Work"
    sibling = tmp_path / "WorkEvil"
    ws.mkdir(); sibling.mkdir()
    monkeypatch.setenv("SENTINEL_WORKSPACE", str(ws))
    for target in (str(sibling), str(ws / ".." / "WorkEvil"), str(tmp_path)):
        result = run_system_op("list_directory", target)
        assert is_failure(result) and "traversal blocked" in result, target


def test_junction_escape_is_blocked(tmp_path, monkeypatch):
    ws = tmp_path / "Work"; outside = tmp_path / "Outside"
    ws.mkdir(); outside.mkdir()
    link = ws / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        import subprocess
        if subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True).returncode != 0:
            import pytest; pytest.skip("cannot create a link here")
    monkeypatch.setenv("SENTINEL_WORKSPACE", str(ws))
    assert is_failure(run_system_op("list_directory", str(link)))
