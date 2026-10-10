import pyttsx3
import threading
import queue
import re
import json
import os

MIN_RATE, MAX_RATE, DEFAULT_RATE = 100, 260, 170


def _settings_file():
    from app.core.paths import SENTINEL_DATA_DIR
    return SENTINEL_DATA_DIR / "voice.json"


def _gender_of(voice) -> str:
    """Windows records each voice's gender in the registry (Attributes, value Gender)."""
    gender = getattr(voice, "gender", None)
    if gender:
        return str(gender).lower()
    voice_id = str(getattr(voice, "id", ""))
    if os.name == "nt" and voice_id.upper().startswith("HKEY_LOCAL_MACHINE\\"):
        try:
            import winreg
            sub = voice_id.split("\\", 1)[1] + "\\Attributes"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as key:
                return str(winreg.QueryValueEx(key, "Gender")[0]).lower()
        except OSError:
            pass
    name = str(getattr(voice, "name", "")).lower()
    for known, g in (("zira", "female"), ("hazel", "female"), ("susan", "female"), ("david", "male"), ("mark", "male"), ("george", "male")):
        if known in name:
            return g
    return "unknown"

class VoiceService:
    """Local text-to-speech on one worker thread.
    stop() discards everything queued and interrupts the current utterance; it is called on
    lock, emergency stop and when the owner turns Voice off. Text is spoken sentence by
    sentence, so even if the engine cannot interrupt mid-sentence, speech ends promptly."""

    def __init__(self):
        self.q = queue.Queue()
        self._generation = 0
        self._lock = threading.Lock()
        self._engine = None
        self._voices = None              # [{id, name, gender}] once the engine has started
        self._ready = threading.Event()
        self._settings = self._load_settings()
        self._applied = None
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        # pyttsx3 must be initialized in the thread that uses it
        try:
            engine = pyttsx3.init()
            # Optional: configure voice properties (rate, volume)
            try:
                self._voices = [{"id": str(v.id), "name": str(v.name).split(" - ")[0].replace(" Desktop", ""),
                                 "gender": _gender_of(v)} for v in engine.getProperty("voices")]
            except Exception:
                self._voices = []   # speaking still works with the default voice
            self._engine = engine
            self._apply(engine)
            self._ready.set()

            while True:
                item = self.q.get()
                if item is None:
                    break
                generation, sentence = item
                try:
                    if generation == self._generation and sentence.strip():
                        self._apply(engine)
                        engine.say(sentence)
                        engine.runAndWait()
                finally:
                    self.q.task_done()
        except Exception as e:
            self._ready.set()
            print(f"Voice engine failed to initialize or crashed: {type(e).__name__}")

    # ── voice choice (male / female) and speed ───────────────────
    @staticmethod
    def _load_settings() -> dict:
        try:
            data = json.loads(_settings_file().read_text(encoding="utf-8"))
            return {"voice_id": data.get("voice_id"), "rate": int(data.get("rate", DEFAULT_RATE))}
        except (OSError, ValueError, TypeError):
            return {"voice_id": None, "rate": DEFAULT_RATE}

    def _apply(self, engine):
        wanted = (self._settings.get("voice_id"), self._settings.get("rate"))
        if wanted == self._applied:
            return
        if wanted[0]:
            engine.setProperty("voice", wanted[0])
        engine.setProperty("rate", wanted[1])
        self._applied = wanted

    def list_voices(self) -> list:
        self._ready.wait(10)
        return list(self._voices or [])

    def settings(self) -> dict:
        voices = self.list_voices()
        current = self._settings.get("voice_id") or (voices[0]["id"] if voices else None)
        return {"voices": voices, "voice_id": current, "rate": self._settings["rate"],
                "min_rate": MIN_RATE, "max_rate": MAX_RATE}

    def set_voice(self, voice_id=None, rate=None) -> dict:
        """Only voices installed on this PC can be chosen. Saved for next time."""
        if voice_id is not None and voice_id not in {v["id"] for v in self.list_voices()}:
            raise ValueError("That voice is not installed on this PC.")
        if rate is not None and not (MIN_RATE <= int(rate) <= MAX_RATE):
            raise ValueError(f"Speed must be between {MIN_RATE} and {MAX_RATE}.")
        with self._lock:
            if voice_id is not None:
                self._settings["voice_id"] = voice_id
            if rate is not None:
                self._settings["rate"] = int(rate)
            try:
                _settings_file().write_text(json.dumps(self._settings), encoding="utf-8")
            except OSError:
                pass
        return self.settings()

    def speak(self, text: str):
        """Adds text to the speech queue."""
        clean_text = self._clean_text_for_speech(text)
        with self._lock:
            generation = self._generation
        for sentence in re.split(r'(?<=[.!?])\s+', clean_text):
            if sentence.strip():
                self.q.put((generation, sentence))

    def stop(self, _reason: str = "stop"):
        """Drops all queued speech and interrupts what is being said now."""
        with self._lock:
            self._generation += 1
        while True:
            try:
                self.q.get_nowait()
                self.q.task_done()
            except queue.Empty:
                break
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

    def pending(self) -> int:
        return self.q.qsize()

    def _clean_text_for_speech(self, text: str) -> str:
        """Removes markdown and code blocks so the TTS doesn't read out syntax."""
        # Remove code blocks
        text = re.sub(r'```.*?```', ' code block omitted ', text, flags=re.DOTALL)
        # Remove tool calls
        text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL)
        # Remove inline code
        text = re.sub(r'`.*?`', '', text)
        # Remove markdown bold/italic asterisks
        text = text.replace('*', '')
        # Remove markdown links
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        return text

voice_service = VoiceService()
