# Site Engine Phase F: Thin Router Migration Plan
**날짜**: 2026-05-15
**단계**: SITE_ENGINE_PHASE_F_THIN_ROUTER_MIGRATION_PLAN_01
**상태**: PLAN (read-only — 기존 코드 변경 없음)

---

## 1. 현재 site router 현황

| site | router 파일 | line 수 | command 수 | CDP 직접 import | gate 직접 구현 | 주요 문제 |
|---|---|---:|---:|:---:|:---:|---|
| EUM | scripts/eum/router.py | 541 | 25 | 참조(usage 출력) | ✅ gate_check 직접 | 541줄, 비가역 submit 로직 내부, workflow 혼재 |
| Hiworks | scripts/hiworks/router.py | 278 | 13 | 참조(usage 출력) | ✅ gates.check_send | 278줄, gates.py 경유하여 일부 분리 |
| Naver | scripts/naver/router.py | 823 | 25 | 참조(usage 출력) | ✅ gate_check 직접 다수 | 823줄 최대 비대, blog_publish/write_blog_post gate 직접 |
| Smartstore | scripts/smartstore/router.py | 344 | 19 | 참조(usage 출력) | ✅ gate_check 직접 | 344줄, build_submit_plan 내부 누적 |
| Google | scripts/google/router.py | 233 | 5 | 참조(usage 출력) | ✅ gate_check 직접 | 233줄, API/브라우저 이중 구조 |
| Youtube | scripts/youtube/router.py | 118 | 4 | 참조(usage 출력) | approval_gated dict | 118줄 가장 작음, record/upload approval 명확 |

---

## 2. site별 책임 분류

| site | 책임/위치 | 현재 위치 | 목표 위치 | 분류 |
|---|---|---|---|---|
| 공통 | gate_check 직접 호출 | 각 router | site_engine.execution_gate | MOVE_TO_SITE_ENGINE_EXECUTION_GATE |
| 공통 | submit/publish/send/delete 직접 실행 | 각 router | site_engine.action_planner | MOVE_TO_SITE_ENGINE_ACTION_PLANNER |
| 공통 | workflow 조합 | router 내부 | site_engine.workflow_runner | MOVE_TO_SITE_ENGINE_WORKFLOW_RUNNER |
| Hiworks | gates.check_send() | hiworks/gates.py | site_engine.execution_gate 경유 | MOVE_TO_SITE_ENGINE_EXECUTION_GATE |
| Hiworks | build_action_catalog / build_prepare_plan | hiworks/actions.py | site_engine.action_planner 호환 | KEEP → 점진 전환 |
| Hiworks | 메일 분류/본문 파싱 | hiworks/mail*.py | hiworks/ 유지 | KEEP_SITE_DOMAIN_WORKFLOW |
| Hiworks | 결재 상신 workflow 정의 | hiworks/workflows.py | hiworks/ 유지 | KEEP_SITE_DOMAIN_WORKFLOW |
| Naver | blog_publish / write_blog_post gate | naver/router.py | site_engine.execution_gate | MOVE_TO_SITE_ENGINE_EXECUTION_GATE |
| Naver | 블로그/카페/쇼핑/캘린더 workflow | naver/workflows.py | naver/ 유지 | KEEP_SITE_DOMAIN_WORKFLOW |
| EUM | 단말기 등록/철거 workflow | eum/workflows.py | eum/ 유지 | KEEP_SITE_DOMAIN_WORKFLOW |
| EUM | EUM 테이블 파싱 (2행→1단말기) | eum/ | eum/ 유지 | KEEP_SITE_DOMAIN_WORKFLOW |
| Smartstore | 상품/주문/통계 DTO | smartstore/actions.py | smartstore/ 유지 | KEEP_SITE_DTO_SCHEMA |
| Google | Drive/Docs/Sheets API 연동 | google/*_api.py | google/ 유지 | KEEP_SITE_DOMAIN_WORKFLOW |
| Youtube | 동영상 upload/record workflow | youtube/uploader.py | youtube/ 유지 | KEEP_SITE_DOMAIN_WORKFLOW |
| 모든 site | command dispatch (match/if) | router.py | router.py 유지 (thin) | ROUTER_DISPATCH_KEEP |

---

## 3. migration 난이도

| site | 난이도 | 위험 요인 | 선행 조건 | 권장 순서 |
|---|---|---|---|---:|
| Hiworks | LOW | gates.py 경유 구조 이미 있음 / 테스트 19건 | - | 1 |
| Youtube | LOW | 118줄 / workflow 명확 / 테스트 1건 | - | 2 |
| Google | MEDIUM | API/browser 이중 / 테스트 2건 | Google API adapter 경계 확인 | 3 |
| Smartstore | MEDIUM | 344줄 / submit 내부 누적 / 테스트 1건 | Smartstore 상품 DTO 유지 | 4 |
| EUM | HIGH | 541줄 / 테스트 11건 / 업무 흐름 복잡 | EUM 테이블 파싱 별도 유지 | 5 |
| Naver | HIGH | 823줄 최대 / 게이트 분산 다수 / 테스트 10건+ | blog/cafe/shopping 분리 선행 | 6 |

---

## 4. thin router 목표 구조

| 항목 | 기준 |
|---|---|
| 1차 목표 (Phase F-1) | 300줄 이하 |
| 2차 목표 (Phase F-2) | 150줄 이하 |
| 허용 항목 | command dispatch, site profile 조회, workflow/action planner 호출, response formatting |
| 금지 항목 | CDP 직접 호출, form field 직접 탐색, approval policy 직접 구현, submit/send/publish/delete 직접 실행, workflow 내부 로직 누적, 민감값 출력 |
| 예외 처리 | 150줄 초과 시 사유를 보고서에 명시 |

---

## 5. site별 migration plan

| site | Phase | 작업 | 완료 조건 | 테스트 |
|---|---|---|---|---|
| Hiworks | F-HIWORKS-1 | dispatch table 정리, gates.py → site_engine.execution_gate 연결 준비 | router ≤ 200줄, gates 중복 제거 | tests/test_hiworks_*.py 19건 PASS |
| Hiworks | F-HIWORKS-2 | submit/send action을 site_engine action_planner로 포장 | approval flow 유지, 기존 동작 동등 | 동일 |
| Youtube | F-YOUTUBE-1 | upload/record workflow를 site_engine workflow_runner plan으로 감쌈 | approval required 유지 | tests/test_youtube_workflow.py PASS |
| Google | F-GOOGLE-1 | gate_check 직접 호출 → site_engine.execution_gate 연결 | API adapter 경계 유지 | tests/test_google_*.py PASS |
| Smartstore | F-SMARTSTORE-1 | submit_plan → site_engine action_planner 호환 포장 | DTO 유지, submit approval 유지 | tests/test_smartstore_actions.py PASS |
| EUM | F-EUM-1 | router 분리 (explore/register/deregister sub-router) | 업무 흐름 동일, 단말기 파싱 유지 | tests/test_eum_*.py 11건 PASS |
| Naver | F-NAVER-1 | blog/cafe/shopping/calendar sub-router 분리 | 각 sub ≤ 200줄 | tests/test_naver_*.py PASS |

---

## 6. 첫 migration 대상

| 순위 | site | 이유 | 예상 작업 | 위험도 |
|---:|---|---|---|---|
| 1 | **Hiworks** | gates.py로 이미 gate 분리 / 테스트 19건 / 278줄로 관리 가능 / 결재 상신 workflow 검증에 적합 | router 정리 + gates.py → site_engine gate 연결 준비 | LOW |
| 2 | Youtube | 118줄 최소 / approval 구조 명확 / upload/record 분리 완료 | workflow_runner plan 포장 | LOW |
| 3 | Google | API/browser 이중 구조 명확히 분리 가능 | adapter 경계 확인 후 gate 연결 | MEDIUM |

---

## 7. audit rule 후보

| rule | 감지 대상 | 적용 시점 | 우선순위 |
|---|---|---|---|
| SITE_ROUTER_DIRECT_CDP_IMPORT | router.py에서 cdp_client 직접 import | SITE_ENGINE_PHASE_F | HIGH |
| SITE_ROUTER_GATE_POLICY_DUPLICATION | router.py에서 gate_check 직접 호출 | SITE_ENGINE_PHASE_F | HIGH |
| SITE_ROUTER_LINE_THRESHOLD_300 | router.py 300줄 초과 → WARN | 즉시 추가 가능 | HIGH |
| SITE_ROUTER_LINE_TARGET_150 | router.py 150줄 초과 → WARN | Phase F-2 완료 후 | MEDIUM |
| APPROVAL_REQUIRED_ACTION_WITHOUT_SITE_ENGINE_GATE | submit/send/delete가 gate 없이 실행 경로 | SITE_ENGINE_PHASE_F | HIGH |
| SITE_ROUTER_FORM_RESOLVER_DUPLICATION | router.py 내부 form field 탐색 코드 | SITE_ENGINE_PHASE_D | MEDIUM |
| SITE_ROUTER_ACTION_PLANNER_DUPLICATION | router.py 내부 action 계획 코드 | SITE_ENGINE_PHASE_E | MEDIUM |
| SENSITIVE_FIELD_WITHOUT_FORM_RESOLVER | password/otp field 직접 처리 | SITE_ENGINE_PHASE_D | MEDIUM |
| BROWSER_ACTION_WITHOUT_ADAPTER_PLAN | cdp.click/type 직접 호출 | SITE_ENGINE_PHASE_D | LOW |

---

## 8. 다음 실행 지시문

```text
SITE_ENGINE_PHASE_F_HIWORKS_THIN_ROUTER_01

목표:
Hiworks router를 thin dispatcher 구조로 전환한다.
기존 테스트 19건이 모두 PASS인 상태를 유지하며 진행한다.

주요 작업:
1. hiworks/router.py 내부 gate_check → site_engine execution_gate 연결 준비
2. hiworks/gates.py를 site_engine.execution_gate와 호환 wrapper로 전환
3. submit/send action이 execution_gate result 없이 실행되지 않는 구조 고정
4. router에서 workflow 조합 로직을 hiworks/workflows.py로 분리
5. router ≤ 200줄 달성

완료 조건:
- router ≤ 200줄
- tests/test_hiworks_*.py 19건 PASS
- layer audit BLOCK 0 / UNKNOWN 0
- quality gate errors 0
- 기존 hiworks 기능 동작 동등
```
