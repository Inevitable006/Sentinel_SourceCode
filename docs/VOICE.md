# Local dictation (Phase 2a)

In Chat, choose **Dictate**, allow the microphone, speak, then choose **Stop**. The transcript appears in the message box. Review it and press Send yourself. Cancel discards the recording and ignores any pending transcript. The microphone stops on cancellation, when the page is hidden, on a lock notification, or when leaving Chat. Recordings are limited to 30 seconds.

Audio is held in memory and sent only to Sentinel's authenticated local backend. It is not saved to disk or uploaded. Cancelling an HTTP request does not immediately stop an already-running native recognition call; that call may finish, but the cancelled UI ignores its result. Locking invalidates results even if Sentinel is unlocked again before recognition finishes. Recognition is serialized and runs off the receiving event loop. Resource pressure or manual pause blocks dictation.

Speech uses the multilingual Whisper base model with CPU int8 and four threads, leaving GPU memory for chat. This is dictation, not speaker authentication. Existing PIN and action approvals still apply. Wake word, speaker identity, Windows Hello, GPU speech recognition and Piper are not implemented by this milestone.

## Current status (2026-10-10)

The speech libraries now import (the earlier Application Control block no longer occurs), but the installed model folder `backend/models/faster-whisper-base` is incomplete: it has `model.bin`, `config.json` and `tokenizer.json`, while CTranslate2 also needs the model's vocabulary file and reports “Cannot load the vocabulary from the model directory”.

Readiness is now honest: the status check actually loads the model once, so Dictation shows **unavailable** until the model really loads. To finish: add the missing vocabulary file from the same model release, add its SHA-256 to `backend/speech-model.json`, then run the synthetic smoke test below. The smoke test no longer depends on PyAV's changed `open()` API. Physical microphone capture and recognition quality remain unverified until then.

Text-to-speech stops immediately (queued sentences discarded) when Sentinel locks, on Emergency stop, or when Voice is turned off.

## Reproduce the setup

Optional packages are pinned in `backend/requirements-voice.txt`; core typed chat does not import them at startup. Install them into the existing backend environment:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r backend\requirements-voice.txt
```

The installed model is `Systran/faster-whisper-base`, revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`. Its three required files (`model.bin`, `config.json`, `tokenizer.json`) live in `backend/models/faster-whisper-base/` and their SHA-256 hashes are recorded in `backend/speech-model.json`. The model directory is ignored by Git. Each transcription verifies these hashes before loading. Runtime model downloads are prohibited; restoration is a separate setup operation from that exact upstream revision. The existing installer excludes models and does not yet bundle this feature.

## Verification

```powershell
.\tools\check.bat -Only tests
.\backend\.venv\Scripts\python.exe tools\smoke_voice.py
```

The second command generates a synthetic test sentence with local Windows speech synthesis and transcribes it with all network sockets blocked. It never opens the microphone and removes its temporary synthetic audio on exit. It must pass before declaring voice operational.

Implementation references: [Faster Whisper local inference](https://github.com/SYSTRAN/faster-whisper), [Electron permission handlers](https://www.electronjs.org/docs/latest/api/session#sessetpermissionrequesthandlerhandler).
