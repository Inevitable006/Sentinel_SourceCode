"""
Skill: file_manager
Create, edit, move and delete files inside the approved Sentinel Workspace folder only.
Every action is previewed on the approval card, checked for conflicts, and can be undone for
5 minutes (app.core.file_ops). Risk Tier: 3 (approval + fresh PIN).
"""
from app.core import file_ops
from app.core.tool_registry import failed


def _run(op, args):
    try:
        return file_ops.apply(op, args)
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")
    except OSError as e:
        return failed(f"Error: the file action failed ({type(e).__name__}). Nothing else was changed.")


def write_file(path: str, content: str) -> str:
    return _run("write", {"path": path, "content": content})


def move_file(src: str, dest: str) -> str:
    return _run("move", {"src": src, "dest": dest})


def delete_file(path: str) -> str:
    return _run("delete", {"path": path})


def make_folder(path: str) -> str:
    return _run("mkdir", {"path": path})


def undo_file_action(action_id: str) -> str:
    try:
        return file_ops.undo(action_id)
    except file_ops.FileOpError as e:
        return failed(f"Error: {e}")
