import asyncio
import psutil
from enum import Enum
import time

class SystemState(Enum):
    IDLE = "idle"
    INTERACTIVE = "interactive"
    HIGH_LOAD = "high_load"
    EMERGENCY = "emergency"
    USER_PAUSED = "user_paused"

class ResourceGovernor:
    _instance = None
    
    def __init__(self):
        self.state = SystemState.IDLE
        self.manual_override = False
        self.poll_interval = 5.0 # seconds
        self._task = None
        self.high_load_count = 0
        self.emergency_count = 0
        
        # Thresholds
        self.cpu_high_threshold = 85.0
        self.ram_high_threshold = 90.0
        
        self.cpu_emerg_threshold = 95.0
        self.ram_emerg_threshold = 95.0
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def start(self):
        """Starts the background monitoring loop."""
        if self._task is None:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._monitor_loop())
            print("[ResourceGovernor] Started background monitoring.")
            
    async def _monitor_loop(self):
        while True:
            if not self.manual_override:
                self._check_resources()
            await asyncio.sleep(self.poll_interval)
            
    def _check_resources(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        ram = mem.percent
        vram = 0
        
        # Try to get VRAM if NVIDIA SMI is available
        import subprocess
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'], 
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                used, total = map(float, result.stdout.strip().split(',')[0:2])
                if total > 0:
                    vram = (used / total) * 100
        except Exception:
            pass
        
        # Check emergency thresholds
        if cpu >= self.cpu_emerg_threshold or ram >= self.ram_emerg_threshold or vram >= 95.0:
            self.emergency_count += 1
            if self.emergency_count >= 2: # 10 seconds sustained
                self._transition_to(SystemState.EMERGENCY)
        else:
            self.emergency_count = 0
            
            # Check high load thresholds
            if cpu >= self.cpu_high_threshold or ram >= self.ram_high_threshold or vram >= 85.0:
                self.high_load_count += 1
                if self.high_load_count >= 2: # 10 seconds sustained
                    if self.state != SystemState.EMERGENCY:
                        self._transition_to(SystemState.HIGH_LOAD)
            else:
                self.high_load_count = 0
                
                # If we were in high load/emergency and it subsided
                if self.state in [SystemState.HIGH_LOAD, SystemState.EMERGENCY]:
                    # Require 3 consecutive clean checks (15 seconds) to downgrade back to interactive
                    self.high_load_count -= 1
                    if self.high_load_count <= -3:
                        self._transition_to(SystemState.INTERACTIVE)
                        self.high_load_count = 0

    def _transition_to(self, new_state: SystemState):
        if self.state != new_state:
            print(f"[ResourceGovernor] State transition: {self.state.value} -> {new_state.value}")
            self.state = new_state
            
            # Action: Unload model on pressure
            if new_state in [SystemState.HIGH_LOAD, SystemState.EMERGENCY]:
                from app.core.ai_service import ai_service
                print(f"[ResourceGovernor] High system pressure detected. Unloading AI model to free RAM.")
                ai_service.unload_model()
                
    def set_user_paused(self, paused: bool):
        self.manual_override = paused
        if paused:
            self._transition_to(SystemState.USER_PAUSED)
            from app.core.ai_service import ai_service
            ai_service.unload_model()
        else:
            # Revert to interactive and let the next poll correct it if needed
            self._transition_to(SystemState.INTERACTIVE)
            self.emergency_count = 0
            self.high_load_count = 0

    def get_status(self):
        return {
            "state": self.state.value,
            "cpu_percent": psutil.cpu_percent(),
            "ram_percent": psutil.virtual_memory().percent,
            "manual_override": self.manual_override
        }

resource_governor = ResourceGovernor.get_instance()
