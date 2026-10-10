"""Real offline speech smoke: synthesize a test phrase, then transcribe it. No microphone access."""
import io
import os
from pathlib import Path
import socket
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def offline(*args, **kwargs):
    raise RuntimeError("The voice smoke test must not access the network")


socket.socket.connect = offline
socket.socket.connect_ex = offline
socket.getaddrinfo = offline


def read_wav_16k(path):
    """Reads the synthesized WAV with the standard library (PyAV's API changed) and resamples to 16 kHz mono."""
    import numpy as np
    with wave.open(str(path), "rb") as reader:
        channels, width, rate = reader.getnchannels(), reader.getsampwidth(), reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    dtype = {1: np.uint8, 2: "<i2", 4: "<i4"}[width]
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    samples = (samples - 128) / 128 if width == 1 else samples / float(2 ** (8 * width - 1))
    samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        positions = np.arange(0, len(samples), rate / 16000)
        samples = np.interp(positions, np.arange(len(samples)), samples)
    return samples


def main():
    import pyttsx3
    from app.core.speech_input import speech_input
    with tempfile.TemporaryDirectory(prefix="sentinel_voice_smoke_") as folder:
        audio_path = Path(folder) / "synthetic.wav"
        engine = pyttsx3.init()
        engine.save_to_file("Hello Sentinel. This is a local speech recognition test.", str(audio_path))
        engine.runAndWait()
        engine.stop()
        samples = read_wav_16k(audio_path)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes((samples.clip(-1, 1) * 32767).astype("<i2").tobytes())
        result = speech_input.transcribe(buffer.getvalue(), lambda: True)
        print("Synthetic test transcript:", result["text"])
        assert "local" in result["text"].lower() and "speech" in result["text"].lower(), "Expected test phrase not recognized"
        print("VOICE SMOKE: PASS (real local model, network blocked, no microphone)")


if __name__ == "__main__":
    main()
