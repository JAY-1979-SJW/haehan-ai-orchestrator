# Development Governance Rules
**날짜**: 2026-05-15
**버전**: v1.0
**상태**: LOCKED

---

## 1. 목적

앞으로 모든 코드 개발은 아래 구조·모듈화·보안·품질 규칙을 통과해야만 진행한다.
규칙을 위반하는 코드는 layer audit, quality gate, pre-commit hook에서 차단된다.
규칙 변경은 별도 governance 문서 업데이트와 사용자 승인을 거쳐야 한다.

---

## 2. 현재 기준선

| 항목 | 값 |
|---|---|
| HEAD | `356817c` |
| server status | clean |
| Phase 3 | CLOSED |
| BLOCK_REFACTORING | 0 |
| UNKNOWN | 0 |
| consistency | ok |
| HOLD | close_2_more.py, eum_docs.py |

---

## 3. Layer Responsibility

| Layer | 역할 | 금지 |
|---|---|---|
| UI | 화면 표시, 사용자 입력 수신 | DB/OS/browser 직접 접근 금지 |
| API/router | request validation, auth 확인, service 호출, response 반환 | 업무 로직/SQL/외부 자동화 직접 구현 금지 |
| Service | usecase 조합, 흐름 제어 | UI 직접 의존, DB raw 직접 write 금지 |
| Core/Domain | 순수 판단, 정책, 산식 | API/UI/browser 직접 의존 금지 |
| Adapter | 외부 API, 브라우저, 파일, HWPX, Excel, CAD 연결 | 업무 정책 판단 금지 |
| Persistence | DB/audit/task state 저장 | route/core 직접 write 금지 |
| Security/Gate | 권한, 승인, 실행 위치, 위험도 판단 | site별 중복 구현 금지 |
| Site module | profile/workflow/action/schema/validator | 공통 엔진 중복 구현 금지 |
| Ops/Test | 감사/검증 도구 | 운영 변경 자동 실행 금지 |

**위반 시**: layer audit WARN 또는 BLOCK_REFACTORING 발생.

---

## 4. Generic Site Engine Rule

사이트별 기능 추가 방식을 중단하고 공통 엔진 구조로 전환한다.

```
site_engine/                 ← 공통 엔진 (순차적으로 구현)
  profiles.py                ← SiteProfile (SiteSpec 고도화)
  registry.py                ← 사이트 등록/조회
  capability_detector.py     ← 현재 페이지 작업 탐지
  execution_gate.py          ← 통합 실행 판단
  form_resolver.py           ← 폼 필드 탐색
  action_planner.py          ← 작업 계획 생성
  workflow_runner.py         ← 업무 흐름 실행
  validators.py              ← 결과 검증
  audit.py                   ← 실행 근거/승인 로그
  adapters/
    browser.py               ← CDP/Playwright 추상화
    local_agent.py           ← 로컬 에이전트 전환
    file.py                  ← 파일 첨부/다운로드/HWPX

scripts/<site>/              ← thin profile/workflow/action만 허용
  profile.py
  schemas.py
  gates.py                   ← thin override만
  workflows.py
  actions.py
  validators.py
```

**금지 사항**:
- 사이트별 router에서 CDP/Playwright 직접 import
- 사이트별 router에서 approval/gate 정책 직접 구현
- 사이트별 form resolver 중복 구현
- site module에서 비밀번호/OTP/session/cookie 자동입력·추출
- EUM/Hiworks/Naver/Smartstore/Google/Youtube에 전용 기능 계속 추가

**EUM/Hiworks/Naver/Smartstore/Google/Youtube는 site_engine 위의 profile/workflow/adapter다.**

---

## 5. Security Rule

| 규칙 | 설명 |
|---|---|
| 비밀번호/OTP/인증서/session/cookie 자동입력 금지 | 사용자 직접 입력만 허용 |
| session/cookie 추출 금지 | CDP get_cdp_cookies() 실행 결과 출력 금지 |
| 서버에서 보안 사이트 브라우저 자동화 금지 | 은행/정부/공인인증/카드/보험 사이트 포함 |
| local-agent 또는 user-direct 전환 정책 유지 | LOCAL_AGENT_REQUIRED / USER_DIRECT_REQUIRED gate 사용 |
| submit/publish/send/upload/delete/상신/투찰/전자서명 | APPROVAL_REQUIRED gate 없이 실행 금지 |
| secret/token/password/API key 값 출력 금지 | 로그, 프린트, 보고서에 실제 값 포함 금지 |

**위반 시**: 즉시 STOP. 사용자 보고 후 판단 대기.

---

## 6. Permission Rule

| 규칙 | 적용 |
|---|---|
| chmod/chown/sudo/ACL 변경 금지 | 권한 문제는 STOP 후 사용자 보고 |
| 실행 파일 권한 변경 금지 | 기존 권한 그대로 유지 |
| repo 밖 temp/cache 디렉터리만 우회 허용 | 필요 시 사용자 명시 승인 후 |
| 권한 오류 발생 시 | 원인 보고 후 STOP. 권한 변경으로 해결하지 않는다 |

---

## 7. Git/Deploy Rule

| 규칙 | 설명 |
|---|---|
| 작업 전 local/origin/server 3자 HEAD 일치 확인 | 불일치 시 STOP |
| server status clean 확인 | dirty 상태 시 원인 파악 후 진행 |
| git add . / git add -A 금지 | 파일 단위 stage만 허용 |
| git clean/reset --hard/checkout --/stash 금지 | 작업 완료 전 파일 상태 보존 |
| 파일 삭제 금지 | 불필요 파일은 repo 밖 이동 또는 git rm --cached만 |
| 파일 이동은 명시된 리팩터링 대상만 | git mv만 허용 |
| 한 커밋 = 하나의 목적 | 목적이 다르면 커밋 분리 |
| 서버 재시작/배포는 별도 승인 단계 | 이번 작업 흐름에 포함하지 않는다 |

---

## 8. New Code Checklist

### 8.0 App Baseline Rule

The locked app baseline is `docs/baseline/APP_BASELINE.md`.

Before changing server, local-agent, browser, AI, approval, desktop runtime, or
release logic, the change must be checked against that baseline. Every code
change report must answer these four points:

```text
[ ] input/output contract
[ ] authorization boundary
[ ] state changes
[ ] regression gate
```

If a planned change weakens the baseline, stop and request explicit user
approval for a baseline/governance change before editing runtime code.

새 코드 작성 전 반드시 아래를 먼저 확인한다:

```
[ ] 어느 layer에 속하는가?
[ ] 기존 모듈로 해결 가능한가?
[ ] 새 파일이 필요한가? 기존 파일 확장인가?
[ ] API key/response shape가 바뀌는가?
[ ] DB schema/write가 발생하는가?
[ ] approval/gate가 필요한가?
[ ] local-agent/user-direct 전환이 필요한가?
[ ] 테스트는 무엇인가? (unit/integration/manual)
[ ] quality gate/audit rule 추가가 필요한가?
[ ] secret 출력이 없는가?
[ ] 권한 변경이 없는가?
```

---

## 9. Commit Checklist

커밋 전 반드시 확인:

```
[ ] staged 범위가 이번 목적의 파일만인가?
[ ] secret/token/password 값이 포함됐는가?
[ ] layer audit PASS (BLOCK_REFACTORING 0, UNKNOWN 0)
[ ] quality gate errors 0
[ ] 관련 테스트 PASS
[ ] 권한 변경 없음
[ ] HOLD 파일 미포함
[ ] diff --cached --check 통과
[ ] local/origin/server HEAD 일치 확인 완료
```

---

## 10. Forbidden Changes

아래 변경은 별도 승인 없이 진행 불가:

| 금지 항목 | 이유 |
|---|---|
| API response key 변경 | 기존 client 파손 |
| DB schema 변경 | 마이그레이션 필요 |
| approval policy 우회 | 비가역 작업 보호 |
| site별 gate 중복 구현 | site_engine 원칙 위반 |
| router 비대화 (300줄 초과) | 업무 로직 분리 위반 |
| 브라우저 자동화 직접 확장 | cdp_client 추상화 원칙 위반 |
| 권한 변경 | 보안 원칙 위반 |
| 파일 삭제 | 데이터 손실 위험 |
| 서버 재시작/배포 (미승인) | 운영 중단 위험 |
| Flask root module 이동 | systemd 서비스 중단 위험 |

---

## 11. Pending Audit Rules (반영 예정)

현재 audit/quality gate에 미구현 상태이며 후속 단계에서 추가한다:

| 규칙 | 목적 | 구현 예정 단계 |
|---|---|---|
| site router에서 CDP 직접 import 감지 → WARN | router 비대화 방지 | SITE_ENGINE_PHASE_B |
| site router에서 approval/gate 정책 직접 구현 감지 → WARN | gate 분산 방지 | SITE_ENGINE_PHASE_C |
| router 300줄 초과 → WARN | router slim 강제 | SITE_ENGINE_PHASE_F |
| submit/send/delete gate 없는 실행 경로 감지 → WARN | 비가역 보호 | SITE_ENGINE_PHASE_C |
| chmod/chown/sudo 코드 내 포함 → ERROR | 권한 변경 방지 | 즉시 추가 예정 |
| server-side local PC 구현체 direct import → WARN | 실행 위치 정책 | SITE_ENGINE_PHASE_C |
| site-specific form resolver 중복 구현 감지 → WARN | form_resolver 공통화 강제 | SITE_ENGINE_PHASE_D |

---

## 12. Next Implementation Order

```text
1. SITE_ENGINE_PHASE_B_INIT_01
   - scripts/site_engine/ 신설
   - profiles.py, registry.py, audit.py
   - SiteSpec → SiteProfile 전환

2. SITE_ENGINE_PHASE_C_EXECUTION_GATE_01
   - execution_gate.py 공통화
   - gate.py + 사이트별 gates.py 통합

3. SITE_ENGINE_PHASE_D_BROWSER_FORM_RESOLVER_01
   - form_resolver.py, adapters/browser.py
   - cdp_client 추상화, 사이트별 CDP 직접 호출 제거

4. SITE_ENGINE_PHASE_E_ACTION_WORKFLOW_RUNNER_01
   - action_planner.py, workflow_runner.py
   - 사이트별 workflow thin definition 전환

5. SITE_ROUTER_THIN_DISPATCHER_MIGRATION_01
   - 모든 site router <= 150줄

6. FLASK_TO_FASTAPI_MIGRATION
   - Flask active root module 29건 이관 포함
   - systemd 서비스 재설정 포함
```

---

## 13. 관련 문서

| 문서 | 내용 |
|---|---|
| docs/reports/structure_refactor_baseline_lock_20260515.md | Phase 1 layer 기준선 |
| docs/reports/generic_site_automation_architecture_lock_20260515.md | 범용 site_engine 구조 설계 |
| docs/reports/structure_refactor_phase3_root_py_closeout_20260515.md | Phase 3 root cleanup 완료 기록 |
| configs/codebase_layer_audit.json | layer audit 기준 (tracked_residuals 포함) |
| configs/quality_gate.json | quality gate 기준 |
