"""
인메모리 Task 레지스트리 (6단계)
task_id → {task, risk, policy} 를 저장해서 executor.py가 조회할 수 있게 함.
approval_manager._store와 같은 in-process 공유 방식.
"""
from typing import Optional

_store: dict = {}


def register(task, risk, policy: dict) -> None:
    _store[task.task_id] = {
        "task":   task,
        "risk":   risk,
        "policy": policy,
    }


def get(task_id: str) -> Optional[dict]:
    return _store.get(task_id)


def clear() -> None:
    _store.clear()
