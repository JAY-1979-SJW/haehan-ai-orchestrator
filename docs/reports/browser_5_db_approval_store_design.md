# BROWSER-5: DB-Backed Approval Store Design

## Executive Summary

BROWSER-4F의 JSONL 파일 기반 persistent store를 운영 환경에서 사용 가능한
DB 기반 구조로 확장한다.

이번 단계 (PoC):
- SQLite 기반 `SQLiteBrowserApprovalStore` 구현
- 기존 verifier / task handler와 호환 검증 완료
- 동일 인터페이스 유지 (drop-in replacement)

---

## JSONL vs DB 비교

| 항목 | JSONL Store (4F) | DB Store (5) |
|------|-----------------|--------------|
| 저장 형식 | append-only `.jsonl` | SQLite 테이블 |
| 재시작 복원 | 이벤트 재생(replay) | SELECT 단일 쿼리 |
| 중복 방지 | 최신 이벤트로 덮음 | UNIQUE constraint |
| 조회 성능 | O(n) 선형 스캔 | O(log n) 인덱스 |
| 동시성 | threading.Lock | Lock + SQLite WAL |
| 감사 로그 | 이벤트 히스토리 자동 | 별도 audit table 필요 |
| 운영 전환 | 파일 기반 단순 | 운영 DB 마이그레이션 필요 |
| 다중 인스턴스 | 파일 충돌 위험 | DB 수준 동시성 처리 |

### JSONL 장점
- 구현 단순
- 파일만 있으면 동작 (DB 설치 불필요)
- 이벤트 순서 보존 (audit trail 내장)
- 로컬 개발/테스트에 적합

### JSONL 단점
- 레코드 수 증가 시 재시작 복원 O(n)
- 동시 쓰기 충돌 위험
- 상태 쿼리 불가 (전체 replay 필요)
- 다중 프로세스 미지원

### DB Store 장점
- 인덱스 기반 O(log n) 조회
- UNIQUE constraint 강제
- 트랜잭션으로 동시성 보장
- 다중 인스턴스 지원 (PostgreSQL)
- 상태/리스크별 집계 쿼리 가능

### DB Store 단점
- DB 설치 및 마이그레이션 필요
- 감사 이벤트 히스토리는 별도 구현
- 운영 배포 복잡도 증가

---

## Schema

```sql
CREATE TABLE browser_approvals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id             TEXT    NOT NULL UNIQUE,
    action_type             TEXT    NOT NULL,
    selector                TEXT    NOT NULL,
    token_hash              TEXT    NOT NULL,  -- SHA256 only, never raw token
    status                  TEXT    NOT NULL DEFAULT 'approved',
    risk_level              TEXT    NOT NULL DEFAULT 'low',
    final_approval_required INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT    NOT NULL,
    expires_at              TEXT,
    used_at                 TEXT,
    revoked_at              TEXT,
    metadata_json           TEXT    -- safe fields only
);

CREATE UNIQUE INDEX idx_approval_id ON browser_approvals(approval_id);
CREATE INDEX idx_status            ON browser_approvals(status);
CREATE INDEX idx_created_at        ON browser_approvals(created_at);
```

### 저장 금지 필드
- `approval_token` — 절대 저장 금지 (hash 후 원문 폐기)
- `final_approval_token`
- `typed_text`, `password`, `otp`
- `cookie`, `session`, `authorization`
- `localstorage`, `sessionstorage`

---

## 인터페이스 (JSONL ↔ DB 교체 가능)

```python
# 동일 인터페이스 — verifier/task handler 변경 없이 교체
store = SQLiteBrowserApprovalStore(db_path=Path("approvals.db"))
verifier = BrowserApprovalVerifier(store)  # 동일

# 기존 JSONL store
store = PersistentBrowserApprovalStore(store_path=Path("approvals.jsonl"))
verifier = BrowserApprovalVerifier(store)  # 동일
```

공통 메서드:
- `create_approval(approval_id, action_type, selector, approval_token, ...)`
- `get(approval_id) → BrowserApprovalRecord | None`
- `mark_used(approval_id) → bool`
- `revoke(approval_id) → bool`
- `clear()`

---

## 운영 전환 전략

### 1단계 (현재): SQLite PoC
- 로컬 개발 / 테스트
- JSONL store와 병렬 운영 가능
- 파일 기반 단일 프로세스

### 2단계: PostgreSQL 마이그레이션
- SQLAlchemy Engine으로 연결부 교체
- Schema 동일 (위 DDL에서 `INTEGER`→`SERIAL`, `TEXT`→`VARCHAR` 등)
- Alembic migration 스크립트 작성
- 환경변수 `APPROVAL_DB_URL` 으로 URL 주입

### 3단계: 운영 배포
- DB connection pool 설정
- WAL mode / 트랜잭션 격리 수준 검토
- 감사 로그 테이블 분리 (`browser_approval_events`)
- 만료 레코드 cleanup cron 등록

### 로컬 → 운영 코드 전환 (최소)

```python
# 로컬 (현재)
store = SQLiteBrowserApprovalStore(db_path=Path("approvals.db"))

# 운영 (목표)
from local_agent.browser_approval_pg_store import PostgresBrowserApprovalStore
store = PostgresBrowserApprovalStore(db_url=os.environ["APPROVAL_DB_URL"])
```

verifier / handler 코드는 변경 없음.

---

## 검증 결과

- 신규 BROWSER-5 tests: 20 PASS
- 기존 BROWSER-4F~4I + DESK-3 회귀: 전체 PASS
- token_hash만 저장, raw token DB 미포함 확인
- 스키마 금지 컬럼 부재 확인 (PRAGMA table_info)
- verifier / task_handler 호환 확인

---

## 남은 Gap

- PostgreSQL store 구현 (`browser_approval_pg_store.py`)
- Alembic migration script
- 감사 이벤트 테이블 (`browser_approval_events`)
- 만료 레코드 cleanup cron
- 운영 DB 연결 및 마이그레이션 실행
