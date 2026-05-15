# Generic Site Automation Architecture Lock
**날짜**: 2026-05-15
**단계**: GENERIC_SITE_AUTOMATION_ARCHITECTURE_LOCK_01
**HEAD**: 1c56e32

---

## 1. 배경 및 목적

현재 프로젝트는 EUM·Hiworks·Naver·Smartstore·Google·Youtube 각각에 router/action/workflow를 사이트별로 계속 추가하는 구조로 성장해 왔다.
이 방식은 다음 문제를 반복 생산한다.

- CDP 직접 제어 코드가 사이트마다 중복 구현됨
- gate/approval 정책이 사이트별로 재구현됨
- form 필드 탐색 로직이 사이트마다 따로 존재함
- router가 비대해지면서 업무 로직과 제어 로직이 혼재함
- 신규 사이트 추가 시 기존 패턴을 다시 복사·붙여넣기함

**이 문서는 사이트별 기능 추가를 중단하고 범용 사이트 자동화 엔진(Generic Site Automation Engine) 구조로 전환하는 기준을 고정한다.**

---

## 2. 현재 구조 요약

### 2-1. 사이트별 모듈 규모

| site | router 규모 | 주요 파일 수 | 문제 |
|---|---:|---:|---|
| EUM | 541줄 | 20 | CDP 직접 제어, gate 분산, form 중복 |
| Hiworks | 278줄 | 11 | gates.py 존재하지만 공통 gate와 이중 구조 |
| Naver | 823줄 | 21 | 최대 비대. _gate_blog/_gate_mail 중복 |
| Smartstore | 344줄 | 3 | actions.py에 로직 누적 |
| Google | 233줄 | 16 | API/브라우저 이중 구현 |
| Youtube | 118줄 | 4 | 상대적으로 단순하나 동일 패턴 |

### 2-2. 현재 공통 인프라 현황

| 파일 | 역할 | 상태 |
|---|---|---|
| `scripts/gate.py` | risk gate, approval 정책 | ✅ 공통화됨 |
| `scripts/schemas.py` | DTO/Enum (OpStatus, RiskLevel 등) | ✅ 공통화됨 |
| `scripts/site_registry.py` | SiteSpec 정의, 로그인 함수 등록 | ✅ 부분 공통화 |
| `scripts/site_access.py` | 로그인 보장, 탭 열기 | ✅ 공통화됨 (608줄) |
| `scripts/site_watch.py` | StepWatcher, 진행 감지 | ✅ 공통화됨 |
| `scripts/form/discovery.py` | FormField, FormDiscovery | ✅ 공통 폼 탐색 |
| `scripts/form/human.py` | human_type, human_click | ✅ 인간형 입력 공통 |
| `scripts/form/orchestrator.py` | universal_login, 자격증명 | ✅ 공통화됨 |
| `scripts/form/profile.py` | 공통 프로필 필드 카탈로그 | ✅ 공통화됨 |
| `scripts/explorer/` | page_classifier, site_crawler, tab_explorer | ✅ 공통화됨 |
| `scripts/router.py` | dispatch 진입점 | ✅ 공통 dispatcher |

### 2-3. 여전히 사이트별로 중복되는 기능

| 중복 기능 | 중복 위치 |
|---|---|
| CDP 직접 호출 (`cdp_client`, `CDP`) | eum, hiworks, naver/automation/* |
| gate/approval 정책 재정의 | eum/router.py, hiworks/gates.py, naver/router.py |
| form 필드 탐색 | eum/form_analyzer.py, archive/debug/* |
| 로그인 상태 확인 | site_registry에 있으나 일부 사이트가 자체 구현 |
| 팝업 탐지 | 사이트별 ad-hoc 구현 |

---

## 3. 범용 엔진 target 구조

```
scripts/site_engine/
├── __init__.py
├── profiles.py          # SiteProfile 정의 (SiteSpec 고도화)
├── registry.py          # 사이트 등록 및 조회 (site_registry 흡수)
├── capability_detector.py  # 현재 페이지에서 가능한 작업 탐지
├── execution_gate.py    # 통합 실행 판단 (gate.py 확장)
├── form_resolver.py     # 폼 필드 탐색 (form/discovery 흡수)
├── action_planner.py    # click/input/download/submit 계획 생성
├── workflow_runner.py   # 업무 흐름 조합 실행기
├── validators.py        # 실행 전후 결과 검증
├── audit.py             # 실행 근거, 승인 기록, 실패 사유 로그
└── adapters/
    ├── browser.py       # CDP/Playwright 통합 (cdp_client 추상화)
    ├── local_agent.py   # 로컬 에이전트 전환
    └── file.py          # 파일 첨부/다운로드/HWPX/Excel/CAD
```

### 3-1. 사이트별 모듈 역할 재정의

각 `scripts/<site>/`는 아래 역할만 갖는다:

```
scripts/<site>/
├── profile.py      # SiteProfile 구현 (base_url, 허용/금지 작업, 실행 위치 정책)
├── schemas.py      # 사이트별 입력/출력 DTO
├── gates.py        # 사이트별 gate 보정 (공통 gate 위에 thin override만)
├── workflows.py    # 업무 흐름 정의 (workflow_runner 경유)
├── actions.py      # site-specific action 매핑
└── validators.py   # 결과 검증 (사이트별 화면/파일 확인)
```

**router.py는 thin dispatcher로만 유지한다.**
업무 로직, CDP 호출, gate 정책은 router에 넣지 않는다.

---

## 4. 공통화 대상 vs 사이트별 잔류 대상

### 4-1. 공통화 대상 (site_engine으로 이관)

| 기능 | 현재 위치 | 공통 엔진 후보 | 우선순위 |
|---|---|---|---|
| 로그인 상태 확인 | site_registry + 사이트별 auth.py | `site_engine/profiles.py` | Phase B |
| 팝업 탐지 | cdp_client/popup_watcher (분산) | `site_engine/capability_detector.py` | Phase B |
| 메뉴/페이지 탐색 | explorer/* | `site_engine/capability_detector.py` | Phase C |
| 폼 필드 탐색 | form/discovery.py + 사이트별 중복 | `site_engine/form_resolver.py` | Phase D |
| 버튼 탐색 | form/discovery.py 일부 | `site_engine/form_resolver.py` | Phase D |
| 인간형 입력/클릭 | form/human.py | `site_engine/adapters/browser.py` | Phase D |
| 파일 첨부/다운로드 | 사이트별 중복 | `site_engine/adapters/file.py` | Phase D |
| 제출/저장/발행/상신 | 사이트별 router | `site_engine/action_planner.py` | Phase E |
| 승인 gate | gate.py + 사이트별 재구현 | `site_engine/execution_gate.py` | Phase C |
| 사용자 직접 조작 요구 | 분산 | `site_engine/execution_gate.py` | Phase C |
| 로컬 에이전트 전환 | 분산 | `site_engine/adapters/local_agent.py` | Phase C |
| 결과 검증 | 사이트별 ad-hoc | `site_engine/validators.py` | Phase G |
| 감사 로그 | audit_logger (공통) + 분산 | `site_engine/audit.py` | Phase B |
| CDP 추상화 | cdp_client 직접 호출 분산 | `site_engine/adapters/browser.py` | Phase D |

### 4-2. 사이트별 잔류 대상

| site | 남길 항목 | 이유 |
|---|---|---|
| EUM | 단말기 임대/설치/철거 업무 흐름 정의 | EUM 도메인 고유 |
| EUM | EUM 테이블 파싱 로직 (2행→1단말기) | 사이트 구조 특화 |
| Hiworks | 메일 분류/본문 파싱 로직 | Hiworks 메일 도메인 고유 |
| Hiworks | 결재 상신 workflow 정의 | 사이트 도메인 고유 |
| Naver | 블로그/카페/쇼핑/캘린더 workflow 정의 | 네이버 서비스 구조 특화 |
| Google | Drive/Docs/Sheets API 연동 | Google API 특화 |
| Smartstore | 상품/주문/통계 DTO | 스마트스토어 도메인 고유 |
| Youtube | 동영상 업로드/녹화 workflow | Youtube 도메인 고유 |

---

## 5. 금지 규칙

| 규칙 | 목적 | audit 가능 여부 |
|---|---|---|
| `scripts/<site>/router.py`에서 CDP 직접 import 금지 | router 비대화 방지 | ✅ grep 가능 |
| `scripts/<site>/router.py`에서 approval/gate 정책 직접 구현 금지 | gate 분산 방지 | ✅ grep 가능 |
| site module에서 secret/session/cookie 값 직접 출력 금지 | 보안 | ✅ grep 가능 |
| submit/upload/delete/publish/send는 execution_gate 없이 실행 금지 | 비가역 작업 보호 | ✅ grep 가능 |
| site-specific form resolver 중복 구현 금지 | form/discovery 중복 방지 | ✅ grep 가능 |
| site workflow는 site_engine.workflow_runner 경유 권장 | 실행 흐름 통합 | ⚠️ 경고 수준 |
| router가 300줄 초과 시 WARN | router 비대화 감지 | ✅ wc -l 기반 |
| 신규 사이트 추가 시 profile.py/schemas.py 없으면 WARN | 구조 준수 강제 | ✅ 파일 존재 여부 |

---

## 6. execution_gate 정책 정의

```python
class ExecutionGate(str, Enum):
    READ_ONLY_ALLOWED      = "READ_ONLY_ALLOWED"      # 서버/로컬 모두 허용
    SERVER_BROWSER_ALLOWED = "SERVER_BROWSER_ALLOWED"  # 서버 브라우저 허용
    LOCAL_AGENT_REQUIRED   = "LOCAL_AGENT_REQUIRED"    # 로컬 에이전트 필수
    USER_DIRECT_REQUIRED   = "USER_DIRECT_REQUIRED"    # 사용자 직접 조작 필수
    APPROVAL_REQUIRED      = "APPROVAL_REQUIRED"       # 사전 승인 필수
    BLOCKED                = "BLOCKED"                  # 실행 금지
```

| Gate | 적용 예시 |
|---|---|
| READ_ONLY_ALLOWED | 페이지 조회, 목록 추출, 다운로드 |
| SERVER_BROWSER_ALLOWED | 검색, 필터, 탐색, 정보 수집 |
| LOCAL_AGENT_REQUIRED | 로컬 HWP/CAD 파일 처리, Windows 앱 제어 |
| USER_DIRECT_REQUIRED | 전자서명, 공동인증서, OTP, 생체인증 |
| APPROVAL_REQUIRED | 메일 발송, 상신, 결제, 게시, 투찰 |
| BLOCKED | 계정 삭제, 대량 데이터 삭제, 약관 위반 작업 |

---

## 7. 마이그레이션 계획

| Phase | 작업 | 완료 조건 |
|---|---|---|
| Phase A | 이 문서 고정. audit rule 초안 등록 | 문서 커밋 완료 |
| Phase B | `site_engine/` 디렉터리 생성. profiles.py, registry.py, audit.py 이관 | SiteSpec → SiteProfile 전환, smoke test 통과 |
| Phase C | `execution_gate.py` 공통화. site_registry의 gate 분산 제거 | gate.py + 사이트별 gates.py 통합 |
| Phase D | `form_resolver.py`, `adapters/browser.py` 공통화. 사이트별 CDP 직접 호출 제거 | form/discovery 흡수, cdp_client 추상화 완료 |
| Phase E | `workflow_runner.py` 공통화. 각 사이트 workflow를 thin definition으로 교체 | naver/router.py ≤ 150줄, eum/router.py ≤ 150줄 |
| Phase F | 사이트별 router를 thin dispatcher로 축소 | 모든 site router ≤ 150줄 |
| Phase G | E2E smoke test, quality gate rule 고정 | 신규 사이트 추가 시 구조 검사 자동화 |

**Phase A~C는 EUM archive(Phase 3 root cleanup) 이후 진행한다.**
**Phase D~G는 Flask→FastAPI 마이그레이션과 병행 가능하다.**

---

## 8. quality gate / audit rule 추가 후보

```python
# codebase_layer_audit.py 추가 후보
SITE_ROUTER_LINE_LIMIT = 300  # 초과 시 WARN ROOT_PY_SCRIPT

# quality_gate.py 추가 후보
BANNED_IN_SITE_ROUTER = [
    "cdp_client",         # CDP 직접 import 금지
    "force_approved",     # gate 우회 금지
    "session.cookie",     # 세션 값 직접 출력 금지
]

GATED_ACTIONS = [
    "mail_send", "submit", "upload", "delete", "publish", "bid"
]
# 위 액션이 gate_check 없이 실행되면 WARN
```

---

## 9. 다음 실행 지시문

```text
1. ROOT_ARCHIVE_EUM_COMMIT_01
   - Phase 3 root cleanup 마무리
   - extract_*.py / EUM standalone scripts → scripts/archive/eum_legacy/

2. SITE_ENGINE_PHASE_B_INIT
   - scripts/site_engine/ 디렉터리 신설
   - profiles.py (SiteProfile), registry.py, audit.py 초안
   - 기존 site_registry.py 보존하며 wrapper 구조로 전환

3. SITE_ENGINE_PHASE_C_GATE
   - execution_gate.py 공통화
   - hiworks/gates.py, naver/router.py gate 중복 제거
```

---

## 10. 설계 원칙 요약

```text
사이트별 router를 계속 키우지 않는다.                        ❌
공통 엔진을 만든다.                                          ✅
사이트별 코드는 profile + adapter + workflow 정의만 둔다.     ✅
실행 판단, gate, form 탐색, 버튼/입력/첨부/다운로드/승인은
공통 엔진이 담당한다.                                        ✅
```
