"""local_agent USER_PRESENT_TASK in-memory 전송 대기 큐 (공유 leaf, 상태).

여러 라우트군(task/browser/user-present)이 공유하는 agent_id → [task_message]
전송 대기 큐. WS heartbeat/pull 시 드레인하여 전송. 라우트 없음.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

import threading as _threading

# agent_id → [task_message, ...]
_up_task_queue: dict[str, list] = {}
_up_task_queue_lock = _threading.Lock()


def _enqueue_up_task(agent_id: str, task_message: dict) -> None:
    with _up_task_queue_lock:
        _up_task_queue.setdefault(agent_id, []).append(task_message)


def _drain_up_tasks(agent_id: str) -> list:
    with _up_task_queue_lock:
        tasks = _up_task_queue.pop(agent_id, [])
    return tasks
