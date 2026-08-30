import pyttsx3
import threading
import queue
import re

class VoiceService:
    def __init__(self):
        self.q = queue.Queue()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        
    def _worker(self):
        # pyttsx3 must be initialized in the thread that uses it
        try:
            engine = pyttsx3.init()
            # Optional: configure voice properties (rate, volume)
            engine.setProperty('rate', 170)
            
            while True:
                text = self.q.get()
                if text is None:
                    break
                
                # Clean up text (remove markdown, code blocks, xml tags) before speaking
                clean_text = self._clean_text_for_speech(text)
                
                if clean_text.strip():
                    engine.say(clean_text)
                    engine.runAndWait()
                    
                self.q.task_done()
        except Exception as e:
            print(f"Voice engine failed to initialize or crashed: {e}")

    def speak(self, text: str):
        """Adds text to the speech queue."""
        self.q.put(text)
        
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
