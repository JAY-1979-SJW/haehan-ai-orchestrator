# Storage Boundary Policy (저장소 허용/금지 정책)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_SHARED_WAREHOUSE_LOCK_01  
상태: LOCKED

STORAGE_BOUNDARY 게이트가 이 정책을 기준으로 검사한다.

핵심 금지: session/cookie/token/password 저장 금지 — 모든 창고 공통 적용

---

## 1. 허용 목록 (ALLOWED)

### 허용되는 저장 행위

| 행위 | 조건 | 창고 |
|------|------|------|
| 초안 생성 | task_id 있음 | `data/drafts/{domain}/{task_id}/` |
| 보고서 생성 | - | `docs/reports/` (MD) / `data/reports/{domain}/` (JSON) |
| 증거 저장 | task_id 있음, 실행 후 | `data/evidence/{domain}/{task_id}/` |
| 승인 레코드 생성 | 승인 게이트 경유 | `data/approvals/{domain}/{task_id}/` |
| 실행 계획 저장 | 승인 후 | `data/execution_plans/{domain}/{task_id}/` |
| 산출물 저장 | task_id 있음 | `data/artifacts/{domain}/{task_id}/` |
| 업로드 원본 보존 | 사용자 직접 또는 LOCAL_AGENT | `data/uploads/{domain}/{task_id}/` |
| Manual visit snapshot | 사용자 직접 방문 | `data/manual_visits/{host}/` |
| 감사 로그 기록 | APPEND_ONLY | `data/logs/` |

### 허용되는 조회 행위

| 행위 | 조건 |
|------|------|
| 초안 조회 | - |
| 보고서 조회 | READ_ONLY |
| 증거 조회 | READ_ONLY, 원본 불변 |
| Manual visit 참조 | READ_ONLY_EVIDENCE, 자동화 재사용 금지 |
| 감사 로그 조회 | 운영자 READ_ONLY |

---

## 2. 금지 목록 (BLOCKED)

### 절대 금지 (위반 즉시 STOP)

| 금지 행위 | 이유 |
|----------|------|
| `data/sessions/*.json` 읽기 | 서버 사이드 세션 재사용 = 무단 로그인 |
| `data/sessions/*.json` 파싱 | session 내 cookie/token 추출 위험 |
| `data/sessions/*.json` 재사용 | 외부 사이트 자동 로그인 시도 |
| `data/sessions/` 신규 파일 생성 | session 자동화 시도 |
| cookie/session/token/password 창고 저장 | 자격증명 유출 위험 |
| secret/env 값 evidence/report에 저장 | 비밀 노출 |
| 전자서명 자동화 실행 기록 생성 | 규정 위반 |
| 투찰 자동 실행 기록 생성 | 규정 위반 |
| 결제 자동 실행 기록 생성 | 규정 위반 |

### 구조적 금지

| 금지 행위 | 이유 |
|----------|------|
| task_id 없는 창고 사용 (신규) | 추적 불가 |
| evidence 삭제/수정 | 증거 위변조 |
| report 삭제/수정 | 감사 무결성 침해 |
| 원본 업로드 파일 수정 | 원본 불변 원칙 |
| 임시 파일을 evidence로 승격 (승인 없이) | 허위 증거 |
| report와 evidence 혼용 | 역할 혼재 |
| manual visit snapshot 자동화 재사용 | 로그인 우회 시도 |
| docs/reports와 data/reports 역할 혼용 | 구조 오염 |
| 루트 `data/` 직접 저장 (신규) | 위치 불명확 |

### 금지 파일 패턴

```
*cookie*
*session*
*token*
*password*
*.env
*.pem
*.key
*secret*
*credential*
*auth_token*
```

---

## 3. Session Store 봉인 정책

```
[data/sessions/] — 봉인된 위험구역 (SEALED DANGER ZONE)

상태: BLOCKED
파일: eum.cw.or.kr.json, gabia.com.json, my.gabia.com.json,
      naver.com.json, office.hiworks.com.json

접근 방법: 없음 (코드에서 읽기/파싱/재사용 전면 금지)
삭제: 가능하지만 사용자 명시 승인 필요
신규 생성: 금지

접근 필요성 발견 시:
  1. 즉시 STOP 보고
  2. 설계 변경 승인 요청
  3. 승인 후에만 접근 방법 설계
  4. 반드시 LOCAL_AGENT_REQUIRED 또는 USER_DIRECT_REQUIRED로만
```

---

## 4. Manual Visit Snapshot 사용 정책

```
[data/manual_visits/{host}/] — Read-Only Evidence

사용 목적: 사용자가 직접 방문한 화면의 스냅샷을 증거로 보존
접근 방법: READ_ONLY_EVIDENCE (참조만)

허용:
  - 화면 스냅샷 조회 (내용 확인)
  - 보고서 작성 시 참조
  - 감사 증거로 첨부

금지:
  - 서버 사이드 자동화 재사용
  - session/cookie 추출
  - 로그인 우회 재사용
  - 재실행 자동화에 사용
```

---

## 5. Upload 원본 불변 정책

```
[data/uploads/{domain}/{task_id}/] — Immutable Origin

원칙: 사용자가 업로드한 원본은 절대 자동 수정 금지
처리 결과: 별도 data/artifacts/{domain}/{task_id}/에 저장
삭제: USER_DIRECT_REQUIRED

체크리스트:
  □ 원본 파일 해시 기록 (저장 시)
  □ 처리 후 원본 해시 재검증
  □ 원본 != 처리 결과 (경로 분리)
```

---

## 6. Evidence 무결성 정책

```
[data/evidence/{domain}/{task_id}/] — Immutable Evidence

원칙: 생성 후 수정/삭제 금지
필수 연결: task_id 없는 evidence 생성 금지
내용 금지: session/cookie/token/password/secret/env 포함 금지
승격 경로: manual_visit → evidence 직접 승격 금지 (참조만)

체크리스트:
  □ task_id와 연결됨
  □ 생성 시각 기록됨
  □ 민감 정보 포함되지 않음
  □ 원본 불변 (수정 이력 없음)
```

---

## 7. STORAGE_BOUNDARY 게이트 적용 기준

STORAGE_BOUNDARY 게이트는 다음을 자동 검사한다:

```python
# 금지 패턴 (신규 코드에서 발견 시 WARN)
- open(... "data/sessions" ...) 또는 read_text(... sessions ...)
- cookie 관련 파일 저장 코드
- token 값 파일 직접 기록 코드
- DB import가 저장소 레이어 외부에 있음

# Known Debt (기존 코드 — INFO + [KNOWN_DEBT])
- allowlist에 등록된 기존 파일
```

---

## 8. 관련 문서

- `docs/architecture/shared_warehouse_model.md` — 창고 상세 정책
- `docs/architecture/domain_warehouse_allocation.md` — Domain별 창고 배정
- `docs/architecture/shared_warehouse_manifest.json` — 기계 검사용 manifest
- `docs/architecture/storage_audit_evidence_model.md` — 기존 저장소 모델
- `tools/repo_gates/codebase_layer_audit.py` — STORAGE_BOUNDARY 게이트 구현
