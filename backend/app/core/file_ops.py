"""Owner-approved file actions inside one approved folder, with preview, conflict check and undo.

- Only inside the approved folder (SENTINEL_FILES, default Documents\\Sentinel Workspace).
  Symlinks/junctions are resolved first, so they cannot lead outside it.
- Preview: what will change is shown on the approval card (sizes, first lines, overwrite or not).
- Conflict check: the file's fingerprint at preview time must still match when the action runs.
- Undo: for UNDO_SECONDS the previous state is kept and one click restores it. After that the
  action is final and the undo copy is erased. "Delete" moves the file into the undo store; it is
  only gone for good when the window closes. Nothing is ever deleted without that window.
"""
import contextvars
import hashlib
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from app.core.paths import SENTINEL_DATA_DIR

UNDO_SECONDS = 5 * 60
MAX_WRITE_BYTES = 1024 * 1024
UNDO_STORE = SENTINEL_DATA_DIR / "file_undo"

# Set by SecureRunner to the approval token while an approved action runs.
current_approval: contextvars.ContextVar = contextvars.ContextVar("sentinel_current_approval", default=None)
_previews: Dict[str, dict] = {}       # approval token -> fingerprint captured at preview time
_lock = threading.Lock()


class FileOpError(Exception):
    pass


def files_root() -> Path:
    configured = os.getenv("SENTINEL_FILES")
    root = Path(configured) if configured else Path.home() / "Documents" / "Sentinel Workspace"
    root.mkdir(parents=True, exist_ok=True)
    return Path(os.path.realpath(root))


def resolve(rel: str, must_exist: bool = False) -> Path:
    """Maps a path to a real path inside the approved folder, or refuses."""
    if not isinstance(rel, str) or not rel.strip() or "\x00" in rel:
        raise FileOpError("Give a file path inside the Sentinel Workspace folder.")
    root = files_root()
    candidate = Path(rel)
    candidate = candidate if candidate.is_absolute() else root / candidate
    real = Path(os.path.realpath(candidate))
    try:
        real.relative_to(root)
    except ValueError:
        raise FileOpError(f"Only files inside {root} can be changed.") from None
    if real == root:
        raise FileOpError("Choose a file or folder inside the workspace, not the workspace itself.")
    if must_exist and not real.exists():
        raise FileOpError(f"{rel} does not exist.")
    return real


def _rel(path: Path) -> str:
    return str(path.relative_to(files_root()))


def fingerprint(path: Path) -> str:
    if not path.exists():
        return "absent"
    if path.is_dir():
        return "dir:" + ",".join(sorted(p.name for p in path.iterdir()))
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _targets(op: str, args: dict):
    if op == "write":
        return [resolve(args.get("path", ""))]
    if op == "move":
        return [resolve(args.get("src", ""), must_exist=True), resolve(args.get("dest", ""))]
    if op == "delete":
        return [resolve(args.get("path", ""), must_exist=True)]
    if op == "mkdir":
        return [resolve(args.get("path", ""))]
    raise FileOpError("Unknown file action.")


def _first_lines(text: str, n: int = 6) -> str:
    lines = text.splitlines()
    return "\n".join(lines[:n]) + (f"\n… ({len(lines) - n} more lines)" if len(lines) > n else "")


def preview(op: str, args: dict, token: Optional[str] = None) -> dict:
    """What will happen, in plain words. Remembers the fingerprint for the conflict check."""
    targets = _targets(op, args)
    prints = [fingerprint(t) for t in targets]
    if op == "write":
        t = targets[0]
        content = str(args.get("content", ""))
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise FileOpError("That is more than 1 MB of text; split it up.")
        if t.is_dir():
            raise FileOpError(f"{args['path']} is a folder.")
        what = (f"Overwrite {_rel(t)} ({t.stat().st_size:,} bytes now → {len(content.encode('utf-8')):,} bytes)"
                if t.exists() else f"Create {_rel(t)} ({len(content.encode('utf-8')):,} bytes)")
        details = {"summary": what, "new_content_start": _first_lines(content)}
    elif op == "move":
        src, dest = targets
        if dest.exists():
            raise FileOpError(f"{_rel(dest)} already exists; choose another name.")
        details = {"summary": f"Move {_rel(src)} → {_rel(dest)}"}
    elif op == "delete":
        t = targets[0]
        kind = "folder (with everything in it)" if t.is_dir() else f"file ({t.stat().st_size:,} bytes)"
        details = {"summary": f"Delete the {kind} {_rel(t)}. You can undo this for {UNDO_SECONDS // 60} minutes; after that it is gone for good."}
    else:
        details = {"summary": f"Create folder {_rel(targets[0])}"}
    details["undo"] = f"Undo available for {UNDO_SECONDS // 60} minutes after it runs."
    if token:
        with _lock:
            _previews[token] = {"prints": prints, "at": time.time()}
    return details


def _check_conflict(op: str, args: dict, targets) -> None:
    token = current_approval.get()
    with _lock:
        seen = _previews.pop(token, None) if token else None
    if seen is None:
        raise FileOpError("This file action was not previewed and approved. Ask again.")
    if [fingerprint(t) for t in targets] != seen["prints"]:
        raise FileOpError("The file changed after you approved this action. Nothing was changed; ask again to see the new preview.")


def _snapshot(path: Path) -> str:
    UNDO_STORE.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    dest = UNDO_STORE / name
    if path.is_dir():
        shutil.copytree(path, dest)
    else:
        shutil.copy2(path, dest)
    return name


def _record(op, path, dest=None, snapshot=None, existed=False, summary=""):
    from app.db.database import SessionLocal
    from app.db.models import FileAction
    now = time.time()
    action_id = uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        db.add(FileAction(id=action_id, op=op, path=path, dest=dest, snapshot=snapshot, existed=int(existed),
                          summary=summary, created=now, undo_until=now + UNDO_SECONDS, status="done"))
        db.commit()
    return action_id


def apply(op: str, args: dict) -> str:
    targets = _targets(op, args)
    _check_conflict(op, args, targets)
    if op == "write":
        t = targets[0]
        existed = t.exists()
        snap = _snapshot(t) if existed else None
        t.parent.mkdir(parents=True, exist_ok=True)
        tmp = t.with_name(t.name + ".sentinel-tmp")
        tmp.write_text(str(args.get("content", "")), encoding="utf-8")
        os.replace(tmp, t)
        summary = f"{'Updated' if existed else 'Created'} {_rel(t)}"
        aid = _record("write", _rel(t), snapshot=snap, existed=existed, summary=summary)
    elif op == "move":
        src, dest = targets
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dest) if src.is_file() else shutil.move(str(src), str(dest))
        summary = f"Moved {args['src']} → {_rel(dest)}"
        aid = _record("move", args["src"], dest=_rel(dest), summary=summary)
    elif op == "delete":
        t = targets[0]
        UNDO_STORE.mkdir(parents=True, exist_ok=True)
        snap = uuid.uuid4().hex
        shutil.move(str(t), str(UNDO_STORE / snap))      # held, not destroyed, until the window closes
        summary = f"Deleted {args['path']}"
        aid = _record("delete", args["path"], snapshot=snap, summary=summary)
    else:
        t = targets[0]
        if t.exists():
            raise FileOpError(f"{args['path']} already exists.")
        t.mkdir(parents=True)
        summary = f"Created folder {_rel(t)}"
        aid = _record("mkdir", _rel(t), summary=summary)
    return f"{summary}. Undo is possible for {UNDO_SECONDS // 60} minutes (action {aid})."


def undo(action_id: str) -> str:
    from app.db.database import SessionLocal
    from app.db.models import FileAction
    with _lock, SessionLocal() as db:
        a = db.get(FileAction, action_id)
        if a is None:
            raise FileOpError("No such file action.")
        if a.status != "done":
            raise FileOpError("This action was already undone or is final.")
        if time.time() > a.undo_until:
            raise FileOpError("The undo window has closed; this action is final.")
        root = files_root()
        path = resolve(a.path)
        snap = UNDO_STORE / a.snapshot if a.snapshot else None
        if a.op == "write":
            if a.existed and snap and snap.exists():
                shutil.copy2(snap, path)
            elif not a.existed and path.exists():
                path.unlink()
        elif a.op == "move":
            dest = resolve(a.dest)
            if path.exists():
                raise FileOpError(f"{a.path} exists again; move it away first.")
            shutil.move(str(dest), str(path))
        elif a.op == "delete":
            if path.exists():
                raise FileOpError(f"Something new is at {a.path}; move it away first.")
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(snap), str(path))
            snap = None
        elif a.op == "mkdir":
            if path.exists() and any(path.iterdir()):
                raise FileOpError("The folder is no longer empty; not removing it.")
            if path.exists():
                path.rmdir()
        if snap and snap.exists():
            shutil.rmtree(snap) if snap.is_dir() else snap.unlink()
        a.status = "undone"
        db.commit()
        return f"Undone: {a.summary}."


def finalize_expired(now: Optional[float] = None) -> int:
    """Closes undo windows: erases undo copies (and held deleted files). Returns how many."""
    from app.db.database import SessionLocal
    from app.db.models import FileAction
    now = now or time.time()
    count = 0
    with _lock, SessionLocal() as db:
        for a in db.query(FileAction).filter(FileAction.status == "done", FileAction.undo_until < now):
            if a.snapshot:
                snap = UNDO_STORE / a.snapshot
                if snap.exists():
                    shutil.rmtree(snap) if snap.is_dir() else snap.unlink()
            a.status = "final"
            count += 1
        db.commit()
    with _lock:
        for token in [t for t, v in _previews.items() if now - v["at"] > 600]:
            _previews.pop(token, None)
    return count


def recent(limit: int = 30) -> list:
    from app.db.database import SessionLocal
    from app.db.models import FileAction
    now = time.time()
    with SessionLocal() as db:
        rows = db.query(FileAction).order_by(FileAction.created.desc()).limit(limit).all()
        return [{"id": a.id, "summary": a.summary, "status": a.status, "created": a.created,
                 "undo_seconds_left": max(0, int(a.undo_until - now)) if a.status == "done" else 0} for a in rows]
