"""
Phase 10A Request Context Registry

Manages cancellation of in-flight network requests bound to unique request IDs.
"""
import asyncio
from typing import Dict
import threading

class RequestContextRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._active_tasks: Dict[str, asyncio.Task] = {}

    def register_task(self, request_id: str, task: asyncio.Task):
        """Binds an asyncio Task to a unique request ID."""
        with self._lock:
            self._active_tasks[request_id] = task

    def unregister_task(self, request_id: str):
        """Removes a task from the registry."""
        with self._lock:
            self._active_tasks.pop(request_id, None)

    def cancel_request(self, request_id: str) -> bool:
        """Cancels the task associated with the request ID if it exists."""
        with self._lock:
            task = self._active_tasks.get(request_id)
            if task and not task.done():
                # The task runs on a worker thread's own event loop: cancel it from that loop.
                task.get_loop().call_soon_threadsafe(task.cancel)
                return True
        return False


def cancel_request_work(request_id: str) -> None:
    """Stops everything running for one request: child processes and network tasks."""
    if not request_id:
        return
    from app.core.safe_process import safe_process
    safe_process.cancel_job(request_id)
    request_context.cancel_request(request_id)

request_context = RequestContextRegistry()
