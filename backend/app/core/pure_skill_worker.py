"""Contained, pinned pure calculators used by SkillRouter.

Uses the existing approved-script containment; not an OS sandbox for hostile code.
The only backend import available to the child is a failure-result facade.
"""
import hashlib
import json
import tempfile
import threading
import uuid
from pathlib import Path

from app.core.python_sandbox import run_python
from app.core.skill_verifier import skill_verifier
from app.core.tool_registry import failed
from app.core.safe_process import current_job, safe_process
from app.core.vault import vault
from app.db.database import is_open

TOOLS = {
    'business_analysis': frozenset({'unit_economics', 'campaign_metrics'}),
    'technical_analysis': frozenset({'convert_units', 'estimate_transfer'}),
}
SKILLS = Path(__file__).resolve().parents[2] / 'skills'
MAX_INPUT = 8192
MAX_SOURCE = 65536
_lock = threading.Lock()
_generation = 0
_active = {}


def _cancel_on_lock(reason='locked'):
    global _generation
    with _lock:
        _generation += 1
        jobs = set(_active.values())
    for job in jobs:
        safe_process.cancel_job(job)


vault.add_lock_listener(_cancel_on_lock)


def run_pure(skill: str, tool: str, args: dict):
    """Parent policy/approval checks must precede this internal execution adapter."""
    if not is_open():
        return failed('Calculation refused while Sentinel is locked.')
    identity = object()
    job = current_job.get() or 'calculation-' + uuid.uuid4().hex
    with _lock:
        generation = _generation
        _active[identity] = job
    token = current_job.set(job)
    try:
        if not is_open():
            return failed('Calculation refused while Sentinel is locked.')
        result = _run_pure(skill, tool, args)
        with _lock:
            cancelled = generation != _generation
        if cancelled or not is_open():
            return failed('Calculation cancelled because Sentinel locked.')
        return result
    finally:
        current_job.reset(token)
        with _lock:
            _active.pop(identity, None)


def _run_pure(skill: str, tool: str, args: dict):
    if not isinstance(skill, str) or not isinstance(tool, str) or skill not in TOOLS or tool not in TOOLS[skill]:
        return failed('Calculation worker does not support this tool.')
    try:
        if not isinstance(args, dict) or any(
            not isinstance(k, str) or k.startswith('_') or
            type(v) not in (str, int, float, bool, type(None)) for k, v in args.items()
        ):
            raise ValueError()
        encoded = json.dumps(args, allow_nan=False)
        if len(encoded.encode('utf-8')) > MAX_INPUT:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return failed('Calculation arguments must be bounded JSON scalar values.')
    try:
        with (SKILLS / skill / '__init__.py').open('rb') as stream:
            source = stream.read(MAX_SOURCE + 1)
        if len(source) > MAX_SOURCE:
            return failed('Calculation skill exceeds the worker source limit.')
        expected = (skill_verifier.pinned_hashes() or {}).get('skills.' + skill)
        if not expected or hashlib.sha256(source).hexdigest() != expected:
            return failed('Calculation skill integrity check failed.')
        # Only this tiny interface is exposed; never import the real backend in the child.
        script = '''import builtins, json, types
class Failure(str):
    pass
facade = types.SimpleNamespace(failed=Failure)
original_import = builtins.__import__
def limited_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'app.core.tool_registry' and fromlist == ('failed',):
        return facade
    if level or name not in ('json', 'math', 'decimal'):
        raise ImportError('Unsupported calculation import')
    return original_import(name, globals, locals, fromlist, level)
scope = {'__builtins__': dict(vars(builtins), __import__=limited_import)}
'''
        script += f"exec(compile({source!r}, '<pinned-calculator>', 'exec'), scope)\n"
        script += f"result = scope[{tool!r}](**json.loads({encoded!r}))\n"
        script += "print(json.dumps({'failed': isinstance(result, Failure), 'result': str(result)}, allow_nan=False))\n"
        with tempfile.TemporaryDirectory(prefix='sentinel_calculation_') as folder:
            ok, output, _ = run_python(script, workspace=Path(folder))
        if not ok:
            return failed('Calculation worker stopped or failed; no result was accepted.')
        envelope = json.loads(output)
        if (not isinstance(envelope, dict) or set(envelope) != {'failed', 'result'} or
                type(envelope['failed']) is not bool or not isinstance(envelope['result'], str)):
            raise ValueError()
        return failed(envelope['result']) if envelope['failed'] else envelope['result']
    except Exception:
        return failed('Calculation worker could not complete safely.')
