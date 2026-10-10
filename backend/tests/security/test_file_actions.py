"""File actions: approved folder only, preview, conflict check, 5-minute undo, then final."""
import os
import subprocess
import time

import pytest

from app.core import file_ops
from app.core.secure_runner import secure_runner


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setenv("SENTINEL_FILES", str(root))
    monkeypatch.setattr(file_ops, "UNDO_STORE", tmp_path / "undo")
    from app.core.skill_router import skill_router
    if "file_manager" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()
    return root


def approve(tool, args):
    """Preview (approval card), then run with the token, as chat does."""
    first = secure_runner.execute(tool, args, "files", force_confirmation=True)
    if first["status"] != "needs_confirmation":
        return first, None
    details = first["action_preview"]["details"]
    return secure_runner.execute(tool, args, "files", token=first["token"]), details


def action_id(result):
    return result["data"].split("(action ")[1].rstrip(").")


def test_create_preview_and_undo(workspace):
    result, details = approve("skill_write_file", {"path": "notes/todo.txt", "content": "buy milk\ncall mum"})
    assert details["summary"].startswith("Create notes") and "buy milk" in details["new_content_start"]
    assert result["status"] == "success" and (workspace / "notes" / "todo.txt").read_text() == "buy milk\ncall mum"
    assert "Undone" in file_ops.undo(action_id(result))
    assert not (workspace / "notes" / "todo.txt").exists()


def test_overwrite_undo_restores_old_content(workspace):
    (workspace / "a.txt").write_text("original")
    result, details = approve("skill_write_file", {"path": "a.txt", "content": "new"})
    assert details["summary"].startswith("Overwrite a.txt")
    file_ops.undo(action_id(result))
    assert (workspace / "a.txt").read_text() == "original"


def test_delete_is_held_until_the_window_closes(workspace):
    (workspace / "old.txt").write_text("keep me?")
    result, details = approve("skill_delete_file", {"path": "old.txt"})
    assert "gone for good" in details["summary"] and not (workspace / "old.txt").exists()
    file_ops.undo(action_id(result))
    assert (workspace / "old.txt").read_text() == "keep me?"
    result, _ = approve("skill_delete_file", {"path": "old.txt"})
    assert file_ops.finalize_expired(now=time.time() + file_ops.UNDO_SECONDS + 1) >= 1
    assert not any(file_ops.UNDO_STORE.iterdir())            # erased for good now
    with pytest.raises(file_ops.FileOpError, match="final"):
        file_ops.undo(action_id(result))


def test_move_and_undo(workspace):
    (workspace / "x.txt").write_text("x")
    result, _ = approve("skill_move_file", {"src": "x.txt", "dest": "archive/x.txt"})
    assert (workspace / "archive" / "x.txt").exists()
    file_ops.undo(action_id(result))
    assert (workspace / "x.txt").exists() and not (workspace / "archive" / "x.txt").exists()


def test_change_after_approval_is_refused(workspace):
    (workspace / "doc.txt").write_text("v1")
    first = secure_runner.execute("skill_write_file", {"path": "doc.txt", "content": "mine"}, "files", force_confirmation=True)
    (workspace / "doc.txt").write_text("someone else edited this")          # conflict
    result = secure_runner.execute("skill_write_file", {"path": "doc.txt", "content": "mine"}, "files", token=first["token"])
    assert result["status"] == "error" and "changed after you approved" in result["message"]
    assert (workspace / "doc.txt").read_text() == "someone else edited this"


@pytest.mark.parametrize("path", ["..\\outside.txt", "C:\\Windows\\win.ini", "sub\\..\\..\\escape.txt"])
def test_paths_outside_the_folder_are_refused_before_approval(workspace, path):
    result, _ = approve("skill_write_file", {"path": path, "content": "x"})
    assert result["status"] == "error" and "Only files inside" in result["message"]


def test_junction_escape_is_refused(workspace, tmp_path):
    outside = tmp_path / "outside"; outside.mkdir()
    workspace.mkdir(exist_ok=True)
    link = workspace / "link"
    if subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True).returncode != 0:
        pytest.skip("cannot create a junction here")
    result, _ = approve("skill_write_file", {"path": "link\\evil.txt", "content": "x"})
    assert result["status"] == "error" and not (outside / "evil.txt").exists()


def test_action_without_preview_is_refused(workspace):
    from app.core.file_ops import FileOpError
    with pytest.raises(FileOpError, match="not previewed"):
        file_ops.apply("write", {"path": "a.txt", "content": "x"})


def test_recent_list_shows_undo_time(workspace):
    approve("skill_make_folder", {"path": "projects"})
    latest = file_ops.recent()[0]
    assert latest["summary"].startswith("Created folder projects") and 0 < latest["undo_seconds_left"] <= 300
