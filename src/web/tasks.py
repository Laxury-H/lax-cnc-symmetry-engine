"""
Asynchronous Background Task Manager with SSE Progress Streaming.
Prevents HTTP Gateway Timeouts (504 on Render/Cloud Run) for large CAD files.
Executes geometric analysis and repair asynchronously, tracking stage progression
and streaming real-time status updates (0% -> 100%) to the frontend via Server-Sent Events.
"""

from __future__ import annotations
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, Generator
import json


@dataclass
class TaskState:
    task_id: str
    status: str = "queued"          # "queued" | "running" | "completed" | "failed"
    progress: int = 0               # 0 to 100
    stage: str = "Đang chờ xử lý..."
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "error": self.error,
            "elapsed_seconds": round(time.time() - self.created_at, 2)
        }


class TaskManager:
    """
    Manages long-running geometric processing jobs with thread-safe progress tracking.
    """

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: Dict[str, TaskState] = {}
        self._lock = threading.Lock()

    def submit_task(
        self,
        task_func: Callable[[Callable[[int, str], None]], Any]
    ) -> str:
        """
        Submits a function to the task queue.
        The function must accept a `progress_callback(percent: int, stage_name: str)`.
        """
        task_id = str(uuid.uuid4())[:8]
        state = TaskState(task_id=task_id)

        with self._lock:
            self.tasks[task_id] = state

        def worker():
            with self._lock:
                state.status = "running"
                state.progress = 5
                state.stage = "Bắt đầu xử lý..."
                state.updated_at = time.time()

            def progress_callback(pct: int, message: str):
                with self._lock:
                    state.progress = max(0, min(100, pct))
                    state.stage = message
                    state.updated_at = time.time()

            try:
                res = task_func(progress_callback)
                with self._lock:
                    state.status = "completed"
                    state.progress = 100
                    state.stage = "Hoàn tất!"
                    state.result = res
                    state.updated_at = time.time()
            except Exception as e:
                import traceback
                traceback.print_exc()
                with self._lock:
                    state.status = "failed"
                    state.error = str(e)
                    state.stage = f"Lỗi: {str(e)}"
                    state.updated_at = time.time()

        self.executor.submit(worker)
        return task_id

    def get_task(self, task_id: str) -> Optional[TaskState]:
        with self._lock:
            return self.tasks.get(task_id)

    def stream_task_progress(self, task_id: str, timeout_seconds: float = 300.0) -> Generator[str, None, None]:
        """
        Yields Server-Sent Events (SSE) formatting for real-time browser progress monitoring.
        """
        start = time.time()
        last_progress = -1
        last_stage = ""

        while time.time() - start < timeout_seconds:
            state = self.get_task(task_id)
            if not state:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                break

            if state.progress != last_progress or state.stage != last_stage or state.status in ("completed", "failed"):
                last_progress = state.progress
                last_stage = state.stage
                payload = state.to_dict()
                yield f"data: {json.dumps(payload)}\n\n"

            if state.status in ("completed", "failed"):
                break

            time.sleep(0.3)


# Global singleton task manager
TASK_MANAGER = TaskManager(max_workers=4)
