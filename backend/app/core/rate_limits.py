"""Per-skill hourly limits (sliding one-hour window, in memory).

Counted when an action actually starts. When a skill reaches its limit, new requests are refused
before an approval is even asked for, with how long to wait. Limits are owner settings
(Security → Skills); 0 means unlimited. Restarting Sentinel resets the counters.
"""
import threading
import time
from collections import defaultdict, deque

WINDOW = 3600


class SkillRate:
    def __init__(self):
        self._runs = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, skill, now):
        runs = self._runs[skill]
        while runs and now - runs[0] >= WINDOW:
            runs.popleft()
        return runs

    def used(self, skill: str, now: float = None) -> int:
        with self._lock:
            return len(self._trim(skill, now or time.time()))

    def check(self, skill: str, limit: int, now: float = None):
        """Returns None if allowed, else the number of seconds until the next run is allowed."""
        if not limit:
            return None
        now = now or time.time()
        with self._lock:
            runs = self._trim(skill, now)
            if len(runs) < limit:
                return None
            return int(WINDOW - (now - runs[0])) + 1

    def record(self, skill: str, now: float = None):
        with self._lock:
            self._runs[skill].append(now or time.time())


skill_rate = SkillRate()
