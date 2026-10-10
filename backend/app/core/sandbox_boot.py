"""Runs inside the sandboxed Python child process. Not imported by the backend.

Reads the owner-approved script from stdin, installs an audit hook, then runs the script.
The hook allows reading the standard library and the workspace, writing only inside the
workspace, and refuses network, new processes, native-code loading and registry access.
Audit hooks are a strong guard rail, not an OS security boundary: the Windows Job Object
applied by the parent (memory cap, single process, kill on close) and the owner's explicit
approval of the exact code remain the other layers.
"""
import os
import sys

WORKSPACE = os.path.normcase(os.path.realpath(sys.argv[1]))
STDLIB = [os.path.normcase(os.path.realpath(p)) for p in {sys.base_prefix, sys.prefix, os.path.dirname(os.__file__)}]

BLOCKED_EVENTS = (
    "socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.startfile",
    "os.kill", "os.fork", "ctypes.", "_winapi.", "winreg.", "msvcrt.",
    "sys.settrace", "sys.setprofile", "code.__new__", "urllib.Request", "webbrowser.open", "os.add_dll_directory",
    "_ctypes.", "sys.addaudithook",
)
BLOCKED_MODULES = {"ctypes", "_ctypes", "socket", "_socket", "ssl", "_ssl", "subprocess", "_posixsubprocess",
                   "multiprocessing", "_multiprocessing", "winreg", "_winapi", "msvcrt", "_overlapped",
                   "asyncio", "select", "selectors", "http", "urllib", "ftplib", "smtplib", "webbrowser"}
WRITE_EVENTS = {"os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate", "os.link",
                "os.symlink", "shutil.rmtree", "shutil.copyfile", "shutil.move", "os.utime"}


def _inside(path, roots):
    try:
        p = os.path.normcase(os.path.realpath(os.fsdecode(path)))
    except (TypeError, ValueError):
        return False
    return any(p == r or p.startswith(r + os.sep) for r in roots)


class SandboxViolation(PermissionError):
    pass


def _hook(event, args):
    if event == "import":
        name = (args[0] or "").split(".")[0]
        if name in BLOCKED_MODULES:
            raise SandboxViolation(f"Sandbox: importing '{name}' is not allowed.")
        return
    if event.startswith(BLOCKED_EVENTS):
        raise SandboxViolation(f"Sandbox: '{event}' is not allowed.")
    if event == "open":
        path, mode = args[0], args[1] if len(args) > 1 else "r"
        if isinstance(path, int):
            return
        writing = any(c in str(mode or "r") for c in "wax+")
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
            writing = True
        if writing:
            if not _inside(path, [WORKSPACE]):
                raise SandboxViolation("Sandbox: files can only be written inside the Sentinel Python workspace.")
        elif not _inside(path, [WORKSPACE] + STDLIB):
            raise SandboxViolation("Sandbox: files outside the Sentinel Python workspace cannot be read.")
        return
    if event in WRITE_EVENTS:
        for value in args:
            if isinstance(value, (str, bytes, os.PathLike)) and not _inside(value, [WORKSPACE]):
                raise SandboxViolation(f"Sandbox: '{event}' outside the workspace is not allowed.")


def main():
    code = sys.stdin.buffer.read().decode("utf-8")
    os.chdir(WORKSPACE)
    sys.path[:] = [p for p in sys.path if _inside(p, STDLIB)]
    sys.addaudithook(_hook)
    exec(compile(code, "<sentinel-script>", "exec"), {"__name__": "__main__", "__builtins__": __builtins__})


if __name__ == "__main__":
    main()
