"""Cheap local readiness facts; never initialize inference or speech to check them."""
import os
import sys
from itertools import islice
from app.db.database import DatabaseLocked


def _service(module, name):
    loaded = sys.modules.get('app.core.' + module)
    return getattr(loaded, name, None) if loaded else None


def _paused():
    governor = _service('resource_governor', 'resource_governor')
    return governor is not None and governor.state.value not in ('idle', 'interactive')


def _chat():
    if os.environ.get('SENTINEL_DISABLE_LLAMA') == '1':
        return 'unavailable', 'Local chat is disabled in this runtime.'
    if _paused():
        return 'unavailable', 'Chat is paused. Check the PC status or your pause setting.'
    engine = _service('ai_service', 'ai_service')
    registry = _service('model_registry', 'model_registry')
    if engine is None or registry is None:
        return 'unknown', 'Chat runtime status has not been initialized.'
    if engine.llm is not None:
        return 'ready', 'A local chat model is loaded. This check does not test a conversation.'
    active = registry.get_active_id()
    profiles = registry.get_all_profiles()
    candidates = [profiles.get(key, {}) for key in ('heavy', 'balanced', 'lightweight')] if active == 'auto' else [profiles.get(active, {})]
    if not any(p.get('filename') and registry.get_model_path(p['filename']).is_file() for p in candidates):
        return 'setup_required', 'Install a supported chat model and choose it in Settings → Model Selection.'
    if engine.last_load_error:
        return 'unavailable', 'The last model load failed. Check Settings → Model Selection.'
    if engine._llama_available is True:
        return 'ready', 'Model files and the CPU runtime are available. Model loading and conversation are not tested here.'
    return 'unknown', 'Model files exist, but runtime availability has not been confirmed. Check Settings → Model Selection.'


def _dictation():
    from app.core import speech_input
    if _paused():
        return 'unavailable', 'Dictation is paused. Check the PC status or your pause setting.'
    files = ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')
    if not all((speech_input.MODEL_DIR / name).is_file() for name in files):
        return 'setup_required', 'Install the local dictation model using the voice setup guide.'
    service = speech_input.speech_input
    # status() can load the native model: use only the result of an earlier check.
    if not service._runtime_checked:
        return 'unknown', 'Dictation model files exist. Open the existing voice controls to check the runtime; microphone quality is untested.'
    if service._runtime_error:
        return 'unavailable', 'The dictation runtime could not be used. Check the voice setup guide.'
    return 'ready', 'The local dictation runtime passed its previous check. Microphone quality has not been tested here.'


def _speech():
    service = _service('voice_service', 'voice_service')
    if service is None or not service._ready.is_set():
        return 'unknown', 'Speech output has not initialized. Open Settings → Voice to check available voices.'
    if service._engine is None or not service.thread.is_alive():
        return 'unavailable', 'The local speech engine is unavailable. Check Settings → Voice.'
    return 'ready', 'The local speech engine is initialized. No audio was played or heard by this check.'


def _documents():
    from app.core.semantic_search import status
    info = status()
    if _paused():
        return 'unavailable', 'Meaning search is paused. Check the PC status or your pause setting.'
    if not info['installed']:
        return 'setup_required', 'Install the local meaning-search model using the document search guide.'
    if not info['documents'] or not info['indexed'] or info['pending']:
        return 'setup_required', 'Save and prepare documents in Workspace → Documents. Meaning search covers prepared documents only.'
    return 'ready', 'The English model file exists and saved documents are prepared. Model integrity is checked when used, not by this status check.'


def _google():
    from app.core.google_workspace import status
    info = status()
    if not info['configured'] or not info['connected']:
        return 'setup_required', 'Configure and authorize the read-only connection in Settings → Google.'
    if not info['gmail'] or not info['calendar']:
        return 'setup_required', 'Some Google read permissions are missing. Review the connection in Settings → Google. Live access has not been checked.'
    return 'ready', 'Local Google authorization is stored. Live access has not been checked; use Refresh in Settings → Google.'


def _backup():
    from app.core.backup import BACKUP_DIR, SUFFIX
    # No sorting, archive reads, directory creation or backup creation.
    if BACKUP_DIR.exists():
        with os.scandir(BACKUP_DIR) as entries:
            for index, entry in enumerate(islice(entries, 101)):
                if index == 100:
                    return 'unknown', 'The backup folder could not be checked within the status limit. Review Settings → Backup.'
                if entry.name.endswith(SUFFIX) and entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_size > 0:
                    return 'ready', 'A local backup file exists. Its integrity and restore on another PC have not been tested here.'
    return 'setup_required', 'Create an encrypted backup in Settings → Backup and keep your recovery key safely.'


def snapshot():
    checks = []
    for ident, label, probe in (
        ('chat', 'Local chat', _chat), ('dictation', 'Dictation', _dictation),
        ('speech', 'Speech output', _speech), ('document_search', 'Document meaning search', _documents),
        ('google', 'Gmail and Google Calendar', _google), ('backup', 'Encrypted backup', _backup),
    ):
        try:
            state, detail = probe()
        except DatabaseLocked:
            raise
        except Exception:
            state, detail = 'unknown', 'This local check could not establish readiness. Try Refresh or the existing feature settings.'
        checks.append({'id': ident, 'label': label, 'state': state, 'detail': detail})
    return {'version': 1, 'checks': checks}
