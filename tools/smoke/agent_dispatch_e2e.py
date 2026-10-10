# module_category: audit
# primary_trade: common
"""작업 분배 종단 시험 하니스 — 실제 Claude Code(action_run_claude_agent)로 계획·하위 작업을 실행한다.

사용: python tools/smoke/agent_dispatch_e2e.py "<조사 목표>" [동시 처리 수=2] [계획자 원문 저장 경로]
비용: 실제 `claude -p` 호출(계획 약 $0.02 + 하위 작업 약 $0.03씩). 외부 유료 AI API 가 아니라 사용자 PC 의 Claude Code 이며,
읽기 전용 목표로 시험한다(제한 모드). 기준서: docs/specs/2026-10-02_app_agent_dispatch.md

공유 서버/로컬 에이전트/keyring 을 건드리지 않는다: 작업 큐만 스레드 실행기로 대체하고 DB 는 임시 폴더를 쓴다.
(WebSocket 전송 구간은 tests/test_agent_parallel_p1.py 가 따로 검증한다.)
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))

from ai_orchestrator.agent_dispatch import agent_dispatch_service as svc  # noqa: E402
from ai_orchestrator.agent_dispatch import agent_dispatch_store as store  # noqa: E402
from ai_orchestrator.agent_hub.redaction import _strip_result_data  # noqa: E402
from core.agent_runtime.connection.actions import action_run_claude_agent  # noqa: E402
from core.agent_runtime.connection.websocket_client import _build_result_message  # noqa: E402

T0 = time.monotonic()
LOCK = threading.Lock()
EVENTS: list[tuple[float, str]] = []
RUNNING_NOW = 0
PEAK = 0


def log(msg: str) -> None:
    line = f"[{time.monotonic() - T0:6.1f}s] {msg}"
    with LOCK:
        EVENTS.append((time.monotonic() - T0, msg))
    print(line, flush=True)


class ThreadReg:
    """local_agent_registry 대역: enqueue 하면 스레드에서 실제 claude -p 를 실행한다."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.tasks: dict[str, SimpleNamespace] = {}
        self.n = 0

    def list_agents(self):
        return [{"agent_id": "e2e-agent", "agent_status": "idle"}]

    def select_agent(self, agents):
        return agents[0] if agents else None

    def get_agent_capacity(self, _a):
        return self.capacity

    def get_task(self, _agent, task_id):
        return self.tasks.get(task_id)

    def cancel_task(self, *_a, **_k):
        pass

    def enqueue_task(self, *, agent_id, action, params, requested_by):
        self.n += 1
        tid = f"e2e{self.n}"
        task = SimpleNamespace(
            task_id=tid, status="running", result_data=None, result_summary="", error="", failure_reason=""
        )
        self.tasks[tid] = task
        label = requested_by
        log(f"START {tid} ({label}) tools={params['allowed_tools']} budget=${params['max_budget_usd']}")
        threading.Thread(target=self._run, args=(task, params, label), daemon=True).start()
        return task

    def _run(self, task, params, label):
        global RUNNING_NOW, PEAK
        with LOCK:
            RUNNING_NOW += 1
            PEAK = max(PEAK, RUNNING_NOW)
        started = time.monotonic()
        try:
            result = action_run_claude_agent(dict(params))
            msg = _build_result_message({"task_id": task.task_id}, result)  # 실제 에이전트와 같은 변환
            data = _strip_result_data(msg.get("data")) if isinstance(msg.get("data"), dict) else None  # 서버 필터
            task.result_data = data
            task.result_summary = msg["summary"]
            task.error = msg["error"]
            task.status = "completed" if msg["success"] else "failed"
            cost = (msg.get("data") or {}).get("cost_usd")
            log(
                f"END   {task.task_id} ({label}) {task.status} {time.monotonic() - started:.0f}s cost={cost} err={msg['error'][:120]!r}"
            )
        except Exception as exc:  # noqa: BLE001
            task.status, task.error = "failed", f"{type(exc).__name__}: {exc}"
            log(f"CRASH {task.task_id}: {task.error}")
        finally:
            with LOCK:
                RUNNING_NOW -= 1


def _view(did: str) -> dict[str, Any]:
    """분배안 조회 — 없으면(None) 이 스크립트는 더 진행할 수 없으므로 중단한다."""
    d = svc.view(did)
    assert d is not None, f"분배안을 찾을 수 없음: {did}"
    return d


def main() -> int:
    goal = sys.argv[1]
    capacity = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    tmp = Path(tempfile.mkdtemp(prefix="dispatch_e2e_"))
    store._DB_PATH = tmp / "dispatch.db"
    reg = ThreadReg(capacity)
    svc_any: Any = svc  # 모듈 속성 교체(시험용)라 정적 형은 Any 로 본다
    svc_any._reg = reg
    log(f"임시 DB: {store._DB_PATH}  목표: {goal}")

    did = svc.create_dispatch(goal, "e2e")["id"]
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        d = _view(did)
        if d["status"] != store.PLANNING:
            break
        time.sleep(2)
    d = _view(did)
    log(f"계획 결과 status={d['status']} note={d['note']!r}")
    if d["status"] != store.PROPOSED:
        t = reg.tasks["e2e1"]
        raw = (t.result_data or {}).get("result", t.result_summary)
        Path(sys.argv[3] if len(sys.argv) > 3 else "planner_raw.txt").write_text(raw, encoding="utf-8")
        print("--- 계획자 원문(앞 300자) ---")
        print(raw[:300])
        return 2
    for s in d["subtasks"]:
        log(f"  계획: {s['tid']} [{s['role']}] deps={s['depends_on']} res={s['resources']} :: {s['title']}")
    log(f"  미리보기 waves={d['waves']} blocked={d['blocked_reason']!r}")
    if d["blocked_reason"]:
        return 3

    started_before_approval = len(reg.tasks)
    svc.tick(did)
    assert len(reg.tasks) == started_before_approval, "승인 전에 하위 작업이 시작됨!"
    log("승인 전 tick: 하위 작업 시작 없음 (확인)")

    svc.approve(did, "e2e-admin")
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        status = svc.tick(did)
        if status != store.RUNNING:
            break
        time.sleep(3)
    d = _view(did)
    log(f"최종 status={d['status']} note={d['note']!r} 동시 실행 최대={PEAK}")
    for s in d["subtasks"]:
        log(f"  {s['tid']} [{s['role']}] {s['state']} err={s['error']!r} 결과 {len(s['result_text'])}자")
    print("\n=== 최종 결과(final_result) ===")
    print(d.get("final_result", "(없음)")[:3000])
    return 0 if d["status"] == store.COMPLETED else 1


if __name__ == "__main__":
    sys.exit(main())
