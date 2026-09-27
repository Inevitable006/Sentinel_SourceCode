import asyncio
import psutil
from enum import Enum
import time

from app.core.gpu_monitor import gpu_monitor

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

    def stop(self):
        """Stops the background monitoring loop (called on app shutdown)."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        gpu_monitor.shutdown()
            
    async def _monitor_loop(self):
        while True:
            if not self.manual_override:
                try:
                    # Blocking reads (psutil, GPU) run in a worker thread so the event loop
                    # (chat streaming, WebSocket) never waits on them. State changes and
                    # model unloading stay on the event-loop thread.
                    metrics = await asyncio.to_thread(self._read_metrics)
                    if not self.manual_override:
                        self._evaluate(*metrics)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[ResourceGovernor] Monitoring error (will retry): {type(e).__name__}: {e}")
            await asyncio.sleep(self.poll_interval)

    def _read_metrics(self):
        """Returns (cpu %, ram %, vram %). vram is 0.0 when no GPU reading is available."""
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        gpu = gpu_monitor.snapshot()
        vram = gpu["vram_percent"] if gpu["available"] and gpu["vram_percent"] is not None else 0.0
        return cpu, ram, vram

    def _check_resources(self):
        """One synchronous check (tests and callers outside the monitor loop)."""
        self._evaluate(*self._read_metrics())

    def _evaluate(self, cpu, ram, vram):
        # Check emergency thresholds
        if cpu >= self.cpu_emerg_threshold or ram >= self.ram_emerg_threshold or vram >= 95.0:
            self.emergency_count += 1
            if self.emergency_count >= 2: # 10 seconds sustained
                self._transition_to(SystemState.EMERGENCY)
        else:
            self.emergency_count = 0
            
            # Check high load thresholds
            if cpu >= self.cpu_high_threshold or ram >= self.ram_high_threshold or vram >= 85.0:
                # A spike during recovery restarts the clean-check countdown.
                self.high_load_count = max(self.high_load_count, 0) + 1
                if self.high_load_count >= 2: # 10 seconds sustained
                    if self.state != SystemState.EMERGENCY:
                        self._transition_to(SystemState.HIGH_LOAD)
            else:
                # If we were in high load/emergency and it subsided
                if self.state in [SystemState.HIGH_LOAD, SystemState.EMERGENCY]:
                    # Require 3 consecutive clean checks (15 seconds) to downgrade back to interactive.
                    # (Previously the counter was reset to 0 on every clean check, so it never
                    # reached -3 and Sentinel stayed in HIGH_LOAD/EMERGENCY until restart.)
                    self.high_load_count = min(self.high_load_count, 0) - 1
                    if self.high_load_count <= -3:
                        self._transition_to(SystemState.INTERACTIVE)
                        self.high_load_count = 0
                else:
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
        vm = psutil.virtual_memory()
        return {
            "state": self.state.value,
            "cpu_percent": psutil.cpu_percent(),
            "ram_percent": vm.percent,
            "ram_used_gb": round((vm.total - vm.available) / 1073741824, 1),
            "ram_total_gb": round(vm.total / 1073741824, 1),
            "manual_override": self.manual_override,
            "gpu": gpu_monitor.peek(),
        }

resource_governor = ResourceGovernor.get_instance()
