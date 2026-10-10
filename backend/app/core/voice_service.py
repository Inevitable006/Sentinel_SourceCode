import pyttsx3
import threading
import queue
import re

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
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        # pyttsx3 must be initialized in the thread that uses it
        try:
            engine = pyttsx3.init()
            # Optional: configure voice properties (rate, volume)
            engine.setProperty('rate', 170)
            self._engine = engine

            while True:
                item = self.q.get()
                if item is None:
                    break
                generation, sentence = item
                try:
                    if generation == self._generation and sentence.strip():
                        engine.say(sentence)
                        engine.runAndWait()
                finally:
                    self.q.task_done()
        except Exception as e:
            print(f"Voice engine failed to initialize or crashed: {type(e).__name__}")

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
