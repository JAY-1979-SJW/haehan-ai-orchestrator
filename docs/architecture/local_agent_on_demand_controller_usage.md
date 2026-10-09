# Local Agent On-Demand Controller

## 개요

로컬 에이전트는 상시 데몬이 아니라 AI가 작업 단위로 ON/OFF 한다.

## 핵심 원칙

- 상시 데몬 금지 (Windows service, 시작프로그램, 무한 루프 금지)
- AI가 승인된 작업 시작 시 start
- 작업 완료/실패/취소 시 stop
- cookie/session/token/password 접근 금지
- data/sessions/*.json 읽기/파싱/재사용 금지
- 서버 사이드 로그인 브라우저 실행 금지

## API

```python
from core.agent_runtime.connection.controller import (
    start_local_agent,
    get_local_agent_status,
    stop_local_agent,
    cleanup_stale,
)

# 1. 시작
result = start_local_agent(
    task_id="task-001",
    domain="gabia",
    approved_scope=["dns_read"],
    approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False},
)

# 2. 상태 확인
status = get_local_agent_status()

# 3. 완료 후 종료
stop_local_agent(reason="completed")

# 4. stale 정리 (dry_run 기본)
cleanup_stale(dry_run=True)
```

## 파일 위치

| 파일 | 용도 |
|------|------|
| `core/agent_runtime/connection/controller.py` | start/status/stop/cleanup |
| `core/agent_runtime/connection/status_store.py` | 상태 파일 읽기/쓰기, lock |
| `core/agent_runtime/connection/process_guard.py` | stale 감지, cleanup |
| `data/local_agent/status.json` | 실행 상태 파일 |
| `data/local_agent/agent.lock` | lock 파일 |

## 정책 문서

`docs/architecture/local_agent_on_demand_controller.md`
