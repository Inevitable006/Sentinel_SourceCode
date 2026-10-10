"""Bounded, local-only dictation. No audio files, network downloads or tool execution."""
import importlib.util
import hashlib
import io
import json
import threading
import wave
from pathlib import Path

MAX_SECONDS = 30
SAMPLE_RATE = 16000
MAX_AUDIO_BYTES = SAMPLE_RATE * 2 * MAX_SECONDS + 4096
MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "faster-whisper-base"
MODEL_MANIFEST = Path(__file__).resolve().parents[2] / "speech-model.json"


def verify_model():
    try:
        expected = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))["files"]
        for name in ("model.bin", "config.json", "tokenizer.json"):
            digest = hashlib.sha256()
            with (MODEL_DIR / name).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected[name]:
                raise ValueError("hash mismatch")
    except (OSError, ValueError, KeyError, TypeError):
        raise SpeechError("The local speech model failed its integrity check. Reinstall the pinned model.", 503) from None


class SpeechError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def decode_audio(data: bytes):
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise SpeechError("Record between a moment and 30 seconds of audio.", 413)
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            frames = audio.getnframes()
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
                raise SpeechError("Audio must be mono 16-bit PCM WAV at 16 kHz.")
            if frames < SAMPLE_RATE // 5 or frames > SAMPLE_RATE * MAX_SECONDS:
                raise SpeechError("Record between 0.2 and 30 seconds of audio.")
            pcm = audio.readframes(frames)
            if len(pcm) != frames * 2:
                raise SpeechError("The audio recording is incomplete.")
    except (wave.Error, EOFError) as exc:
        raise SpeechError("The audio recording is not a valid WAV file.") from exc
    import numpy as np
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


class SpeechInput:
    def __init__(self):
        self._busy = threading.Lock()
        self.epoch = 0
        self._runtime_checked = False
        self._runtime_error = None

    def invalidate(self, _reason="locked"):
        # A native inference call may finish before it observes this. Its output is discarded.
        self.epoch += 1

    def status(self):
        files = ("model.bin", "config.json", "tokenizer.json")
        if not all((MODEL_DIR / name).is_file() for name in files):
            reason = "The local speech model has not been installed. See docs/VOICE.md."
        elif importlib.util.find_spec("faster_whisper") is None:
            reason = "The local speech packages have not been installed. See docs/VOICE.md."
        else:
            if not self._runtime_checked:
                try:
                    from faster_whisper import WhisperModel  # loads native libraries
                except (ImportError, OSError, RuntimeError) as exc:
                    if "Application Control" in str(exc):
                        self._runtime_error = "Windows Application Control blocked a speech library. Dictation is unavailable; see docs/VOICE.md."
                    else:
                        self._runtime_error = "The speech runtime could not load. Check the local voice setup in docs/VOICE.md."
                else:
                    # Ready means the model really loads, not just that its files exist.
                    self._runtime_error = self._probe_model(WhisperModel)
                self._runtime_checked = True
            reason = self._runtime_error
        return {"available": reason is None, "reason": reason, "max_seconds": MAX_SECONDS,
                "device": "cpu", "model": "Whisper base (multilingual)", "busy": self._busy.locked()}

    @staticmethod
    def _probe_model(whisper_model):
        try:
            verify_model()
        except SpeechError as exc:
            return str(exc)
        try:
            model = whisper_model(str(MODEL_DIR), device="cpu", compute_type="int8",
                                  cpu_threads=1, num_workers=1, local_files_only=True)
            del model
        except Exception:
            # Native messages can contain local paths; keep the reason generic.
            return "The local speech model is incomplete or incompatible and cannot load. See docs/VOICE.md."
        return None

    def transcribe(self, data, allowed):
        if not self._busy.acquire(blocking=False):
            raise SpeechError("Another recording is being transcribed. Try again shortly.", 409)
        try:
            if not allowed():
                raise SpeechError("Dictation was interrupted. Unlock Sentinel and try again.", 423)
            samples = decode_audio(data)
            status = self.status()
            if not status["available"]:
                raise SpeechError(status["reason"], 503)
            verify_model()
            # Explicit local directory + bundled tokenizer + local_files_only prohibit model downloads.
            from faster_whisper import WhisperModel
            model = WhisperModel(str(MODEL_DIR), device="cpu", compute_type="int8",
                                 cpu_threads=4, num_workers=1, local_files_only=True)
            if not allowed():
                raise SpeechError("Dictation was interrupted. Unlock Sentinel and try again.", 423)
            segments, info = model.transcribe(samples, beam_size=1, vad_filter=True,
                                              condition_on_previous_text=False)
            pieces = []
            for segment in segments:
                if not allowed():
                    raise SpeechError("Dictation was interrupted. Unlock Sentinel and try again.", 423)
                pieces.append(segment.text)
            if not allowed():
                raise SpeechError("Dictation was interrupted. Unlock Sentinel and try again.", 423)
            return {"text": "".join(pieces).strip(), "language": info.language}
        except SpeechError:
            raise
        except Exception:
            # Native exception messages may include private content or local paths.
            raise SpeechError("Local speech recognition failed. Check the voice setup and try again.", 503) from None
        finally:
            self._busy.release()


speech_input = SpeechInput()
