# 앱 트리맵

전체 모듈·통신·게이트·레이어 구조: **`docs/architecture/APP_TREEMAP.md`**  
(포트맵, 라우터 트리, L1~L12 레이어, 게이트 체계, 알려진 이슈 포함)

---

# 기존 구현 확인 의무 (위반 = 중복 구현 금지)

## 자동화·수집·사이트 작업 전 필수 실행

사이트 자동화, 데이터 수집, CDP 조작, 스크래핑 코드를 **새로 작성하기 전에** 반드시 아래를 먼저 실행한다.

```bash
python tools/hooks/capability_check.py <도메인>
# 예시
python tools/hooks/capability_check.py cafe
python tools/hooks/capability_check.py smartstore
python tools/hooks/capability_check.py eum
python tools/hooks/capability_check.py naver mail
```

출력에서 기존 구현(API 엔드포인트, Python 함수, CLI 커맨드)이 확인되면:
- **기존 것을 사용한다** — 새로 짜지 않는다
- API가 있으면 API 호출, Python 함수가 있으면 import해서 사용
- 없을 때만 신규 작성 허용

**CDP 직접 조작(websocket, JS 실행)은 기존 구현이 전혀 없을 때의 최후 수단이다.**

## `[0] 벤더 공식 API` 섹션을 반드시 읽는다 (2026-08-15 추가)

`capability_check` 출력 맨 위의 **`[0] 벤더 공식 API`** 를 확인하지 않고 CDP 작업을 시작하지 않는다.

- 목록: `configs/vendor_apis.json` / 조회: `tools/hooks/vendor_api_registry.py`
- ✅ 표시된 기능은 **API로 구현**한다. CDP로 만들지 않는다.
- ❌ 표시된 것만 CDP가 정당한 경로다.
- 목록에 없는 새 도메인이면 **벤더 API 존재 여부를 검색해 확인**하고 결과를 목록에 추가한다.

**사고 사례:** 스마트스토어 상품등록을 CDP로 구현했다. 검색태그에 5회, 옵션 그리드에
여러 번 헛짚고 접힌 섹션 때문에 4회 오판했다. 그런데 **네이버 커머스API가 무료로**
태그·옵션·원산지·인증·배송·A/S를 전부 제공하고 있었다(스마트에디터 상세페이지만 예외).
`capability_check`는 돌렸지만 그 도구는 **저장소 안**만 보므로 잡히지 않았다.
→ 그래서 `[0]` 섹션을 만들었다. 저장소 밖을 먼저 본다.

---

# 배포 운영규칙

## 로컬 Docker 없음 — 로컬 Docker CLI 호출 금지

- **로컬 PC에 Docker CLI 미설치** → `docker` / `docker-compose` 명령어 로컬 실행 불가
- 배포는 **원격 서버에서만** 수행: `git push` 후 서버가 `git pull` + `docker compose up` 자체 처리
- Python 스크립트에서 `subprocess`로 `docker` / `docker-compose` 직접 호출 금지
- 위반 시 quality gate `NO_LOCAL_DOCKER_CLI` 에러로 커밋 차단됨
- 삭제된 스크립트(복구 금지): `deploy_api_with_runtime_gates.py`, `verify_compose_project_boundary.py`, `verify_docker_context_policy.py`, `verify_container_orphans.py`, `docker/docker-compose.dev.yml`, `docker/docker-compose.file-map-executor.yml`

### 정책 예외 (Scoped Exception) — `tools/server_deploy.py`

- **유일하게 docker 호출이 허용된 스크립트.** `configs/quality_gate.json` 의 `no_local_docker_cli_allow_paths` 에 등록.
- 사유: 서버 배포는 docker compose가 정당하게 필요(서버는 docker로 구동). 배포 스크립트를 repo에 두어 버전관리·리뷰 대상으로 유지하기 위함.
- 안전장치: 스크립트 최상단 `_guard_server_only()` 가 docker 미설치(=로컬 PC) 시 `exit 3`로 즉시 차단 → 로컬에서 절대 실행 불가.
- 이 예외는 **이 파일 1개에만** 적용. 다른 파일의 docker 호출은 그대로 차단.
- ⚠️ **정정(2026-09-29, docs/defect_index.json #6):** 이 스크립트를 호출하던 배포 데몬
  `scripts/ops/deploy_trigger_daemon.py`는 2026-06-02 커밋 `b4ad2f70`에서 "좀비 스크립트"로
  **삭제됨**(`deploy_router.py`의 관련 참조도 같은 커밋에서 제거). 그런데 `ai_orchestrator/routers/deploy_router.py`의
  GitHub webhook 핸들러(`/api/v1/deploy/webhook`)는 여전히 호스트의 `TRIGGER_URL`
  (`host.docker.internal:8401/trigger`)로 전달을 시도한다 — 그 주소를 리슨하는 데몬이
  더 이상 없으므로 **현재 webhook 자동배포는 끊긴 상태로 추정**(운영 서버 직접 확인 전까지
  "추정"). 상세 배경은 `docs/architecture/PROD_DEPLOY_PLAN.md`(2026-06-02, 운영 HEAD가
  origin보다 23커밋 밀려 있던 걸 실측한 문서, 그 이후 최신 상태 미확인)와
  `docs/architecture/DEPLOY_PIPELINE_REPAIR.md` 참고. 실제 배포는 여전히 `server_deploy.py`를
  운영 서버에서 직접 실행(SSH 등)하는 방식으로 우회 가능 — 데몬 복구/재설계는 운영 서버
  접근이 필요해 별도 사용자 승인 후 진행(docs/defect_index.json #4 와 동일 범위).

---

# 외부 유료 AI API 호출 승인제 (2026-07-28 추가)

**GPT/OpenAI 등 외부 유료 AI API를 호출하는 작업은 반드시 사용자 사전 승인 후에만 실행한다.**

- 대상: `ai_orchestrator/openai_proxy_caller.py`(`call_openai_agent`, `call_openai_chat`), `OPENAI_API_KEY` 사용, `api.openai.com` 직접 호출 등 모든 유료 외부 AI API 경로.
- **자동 차단 훅**: `.claude/settings.json` → `hooks.PreToolUse` (matcher `Bash|PowerShell`) → `tools/hooks/guard_openai_call.py`. 위 키워드가 명령어에 포함되면 `bypassPermissions` 모드여도 강제로 사용자 확인(ask)을 받는다.
- 사유: 이 프로젝트의 `permissions.defaultMode`는 `bypassPermissions`(자동 실행)라서, 승인 없이 유료 API를 호출하는 사고가 실제로 발생함(2026-07-28, KPI PDF 비전 파싱 작업 중 사용자 확인 없이 GPT 호출 시도).
- 신규 기능에서 OpenAI/GPT 호출이 필요하면: 먼저 사용자에게 비용·목적을 설명하고 명시적 승인("진행해", "GPT 써도 돼" 등)을 받은 뒤에만 실행한다. 승인 없이 "일단 테스트해본다"는 금지.
- 이 훅은 Bash/PowerShell 명령어 문자열 매칭 방식이라 완벽하지 않음(예: 변수로 우회한 코드는 못 잡음) — 최종 책임은 AI가 실행 전에 스스로 확인하는 것.

## MK 카탈로그 — GPT 비전 API 차단, Claude Code 직접 판독 (2026-08-16 추가)

`scripts/mk_catalog/vision_extract.py`(GPT-4o vision)는 **코드 레벨에서 차단됨**(호출 시 `RuntimeError`).

- 사유: 쿼터 초과로 다수 페이지 처리 실패 + 색상별 variant를 별도 제품으로 오분리하는 정확도 문제.
- 남은 페이지는 **Claude Code가 이미지를 직접 Read 도구로 읽어** 제품을 판독하고,
  `scripts/mk_catalog/append_rows.py` 에 JSON을 stdin으로 넘겨 `data/mk_catalog/products_manual.csv` 에 누적한다.
- 진행 상황: `data/mk_catalog/remaining_pages.json` 에 미처리 페이지 목록, `data/mk_catalog/products.csv`(자동 처리분) + `products_manual.csv`(수동 처리분) 분리 관리.
- `vision_extract.py` 재활성화는 신규 기능과 동일하게 사용자 사전 승인 필요.

---

# 작업 원칙

## 토큰 절약 — 필요시에만 사용 (2026-08-16 추가)

불필요한 탐색적 조사·중복 확인·장황한 출력을 줄이고, 꼭 필요한 조사·실행만 간결하게 수행한다.

- 이미 확인된 사실을 다시 조회하지 않는다 (같은 파일 재확인, 같은 셀렉터 재검증 등).
- 탐색은 목적에 맞는 최소 범위로 — "혹시나" 하는 부가 확인을 반복하지 않는다.
- 보고는 핵심만: 과정 서술보다 결과와 다음 액션 위주로 짧게.
- 코드 작성 전 3단계(기준서→드라이런→승인) 등 필수 절차는 유지하되, 그 절차 안에서의 설명은 간결하게.

## 수동 실행 요청 절대 금지

사용자에게 명령어 직접 실행을 요청하지 않는다.

**금지 표현 (절대 사용 불가):**
- "터미널에서 실행하세요"
- "직접 입력하세요"
- "! python ... 입력하시면"
- "다음 명령을 실행하세요"
- "수동으로 진행하세요"
- "콘솔에서 직접 확인하세요"
- "오류 내용을 보여주세요"
- "화면에 표시된 메시지를 알려주세요"
- "어떤 오류인지 알려주세요"

**오류 발생 시 AI가 직접:**
- 현재 사이트/URL/페이지 상태를 CDP로 확인
- 오류 원인 파악 후 수정
- 재실행

**대신 AI가 직접:**
- Bash/PowerShell 도구로 명령 실행
- 스크립트 직접 실행
- CDP 브라우저 조작
- 파일 읽기/쓰기

**예외 — 사용자가 직접 해야 하는 것 (보안 구조적 한계):**
- 로그인 OTP / SMS / 생체인증
- 결제·과금 최종 확인
- 비가역 작업 최종 저장 버튼

위 예외가 아닌 모든 작업은 AI가 도구를 사용해 직접 수행한다.

## 사용자 승인 후 자동 진행

사용자가 명시적으로 한 흐름을 승인하면 ("진행해", "자동으로 해줘", "모두 동의해" 등) 그 흐름 내 모든 sub-step을 중간 컨펌 없이 끝까지 자동 진행한다. 매 클릭/입력마다 재확인하지 않는다.

**예외 — 매번 재확인 필수:**
- 외부 공개 발행 (블로그/카페/SNS 게시)
- 메일/메시지 전송
- 결제·과금
- 데이터 삭제
- repo boundary 외부에 영향
- 정책/약관상 위험 작업

흐름 도중에는 짧은 진행 보고만, 막힘이나 종료 시점에만 사용자에게 결정 요청.

## 코드 작성 전 기준서 → 드라이 런 → 승인 → 실행

신규 코드 작성 또는 기존 코드 변경 전에 반드시 다음 3단계를 거친다.

1. **기준서 작성** — 무엇을 왜 어떻게 변경하는지 설계 문서를 먼저 작성한다.  
   - 변경 범위, 레이어, 영향 파일, 보안/DB/API 영향 여부를 명시한다.
2. **드라이 런** — 실제 파일 수정 없이 변경 시뮬레이션을 실행하고 결과를 보고한다.  
   - 예상 diff, 게이트 통과 여부, 예상 사이드 이펙트를 보여준다.
3. **사용자 승인 후 코드 실행** — 사용자가 "진행해" 등으로 승인해야만 실제 파일을 수정한다.

**예외 (즉시 실행 허용):**
- 오타·변수명·주석 수정 등 단순 1줄 수정
- 테스트 실행, 로그 조회 등 read-only 작업
- 사용자가 명시적으로 "바로 해줘", "기준서 생략해" 등을 요청한 경우

## 직렬 진행

단계는 직렬로 진행하되, 각 단계는 자동으로 다음으로 이어진다. 검증은 코드가 수행하며, 사용자 컨펌은 흐름 시작 시점에만 받는다.

## 백그라운드 작업 지시

"백그라운드로 해", "알아서 해", "백그라운드 작업" 등의 지시가 있으면:
- 스크린샷·파일 읽기·빌드·실행 등 모든 중간 단계를 사용자 개입 없이 완주
- 중간에 tool use 결과를 사용자에게 확인받거나 흐름을 끊지 않음
- 완료 후 1회 결과 요약만 전달
- Agent 서브에이전트 또는 연속 도구 호출로 끝까지 진행

## 외부 사이트 자동화 — 수동요청 금지 원칙

사용자가 외부 사이트 작업을 지시하면 AI가 CDP 브라우저로 직접 수행한다. "사용자가 직접 하세요", "수동으로 진행하세요" 안내 금지.

**AI가 직접 수행하는 것 (사용자 수동 요청 금지):**
- 개발자 콘솔 앱 등록 (카카오, 네이버, 구글 등)
- Redirect URI / 플랫폼 / 동의항목 설정
- API 키 발급 및 조회
- 도메인·DNS 레코드 입력 준비 (가비아 등)
- 공공데이터포털 활용신청·인증키 발급 신청
- 폼 자동 입력·화면 이동·설정 변경

**사용자가 직접 해야 하는 것 (AI 자동화 불가 — 보안상 구조적 한계):**
- 최초 로그인 / OTP / SMS 인증 / 카카오앱 인증
- 결제·과금·환불
- 최종 저장·제출 버튼 (DNS 변경, 도메인 연장 등 비가역 작업)

**흐름:**
1. 사용자가 작업 지시
2. AI가 로그인 감지 시작 → 사용자가 브라우저에서 로그인 (1회만)
3. 로그인 감지 후 AI가 나머지 모든 단계 자동 수행
4. 완료 후 결과 보고

## 코드 보존

기존 코드 무단 삭제/변경 금지. 기능 추가는 신규 모듈/함수로. "다시 개발" 요청은 기존 파일 보존하고 별도 구현.

## 로그인 세션 보존 (필수)

로그인된 세션은 CDP 영구 프로필에 유지된다. **AI는 작동 중인 로그인 세션을 임의로 파기하지 않는다.**

**금지 (위반 = session-guard 훅 차단):**
- `nidlogin.logout` 등 **로그아웃 URL 접속**으로 세션 종료
- `clear_cookies` / `delete_cookies` / `deleteAllCookies` 등 **쿠키 삭제**
- 로그인 테스트를 위해 **실제 세션을 로그아웃** (필요하면 별도 프로필/계정으로)

**원칙:**
- 한 번 로그인하면 계속 유지 → "매번 로그인" 방지. AI가 깨지 않는 한 세션은 남는다.
- 세션 확인은 `session_probe`(읽기 전용 점검)로만. 로그인 상태를 *바꾸지* 않는다.
- 만료/로그아웃 감지 시: 파기하지 말고 **사용자에게 재로그인 요청**(OTP/캡차는 사용자만 가능).
- 정당한 로그아웃 코드(예: 사용자가 명시 요청한 로그아웃 기능)는 해당 줄에 `# session-ok` 주석.

---

# 앱 구조/보안/레이어 운영규칙

## 레이어 기준

```
L1 Shared Contracts  — 스키마, DTO, 모델, 리덕션 헬퍼
L2 Policy/Gate       — 리스크 게이트, 정책, 승인, 허용목록
L3 Connectors        — 외부 클라이언트, 저수준 IO 래퍼
L4 Browser Engine    — 브라우저/세션/폼 자동화 (범용)
L5 Site Modules      — 사이트별 라우터, 셀렉터, 능력
L6 Business Workflows— 업무 흐름 오케스트레이션, 큐
L7 Persistence/Audit — DB, 감사, 운영 로그, 마이그레이션
L8 Server API        — FastAPI/Flask 라우터, 서버 태스크 API
L9 Admin UI          — 프론트엔드/관리/데스크톱 UI
L10 Local PC App     — Excel/HWP/CAD/재고/파일맵 자동화
L11 Tests/Fixtures   — 테스트 및 픽스처
L12 Docs/Reports     — 설계서, 운영규칙, 감사 결과
```

## 의존성 방향 (위반 = FORBIDDEN_IMPORT 게이트 FAIL)

허용: 상위 레이어 → 하위 레이어  
금지:
- core/domain(L2) → API(L8) / UI(L9) / DB 직접
- site router(L5) → DB 직접
- 서로 다른 업무 도메인 간 직접 import (hiworks ↔ eum ↔ youtube ↔ g2b)
- 하위 레이어 → 상위 레이어 역방향

## 신규 코드 위치 규칙

신규 코드 작성 전 반드시 확인:
1. 이 기능이 어느 레이어에 속하는가
2. 기존 모듈이 있는가 (재사용 우선)
3. 새 파일 생성 위치가 허용된 위치인가
4. 기존 API 응답 key / DB schema / SQL / 산식 / 정책을 변경하는가
5. 보안 영향이 있는가
6. 순환 의존성 또는 역방향 import가 생기는가
7. 테스트와 audit gate가 있는가

금지:
- router에 SQL 작성
- UI에 업무 산식
- core/domain에 환경변수 직접 접근
- 외부 API 호출 코드 여러 곳 중복
- 거대 파일에 기능 누적

## 보안 금지선 (위반 = SECURITY_PATTERN 게이트 FAIL)

```
secret/token/password 값 출력/로깅 금지
.env 값 원문 출력 금지
운영 DB update/delete/drop/truncate 승인 없이 금지
schema 변경 승인 없이 금지
chmod/chown 자동 변경 금지
투찰/전자서명/송금/결제 자동 실행 금지
쿠키/session 추출 금지
```

## 게이트 실행 의무

작업 후 반드시 실행:
```bash
python tools/repo_gates/codebase_layer_audit.py
pytest tests/test_codebase_layer_audit.py -q
python tools/quality/quality_gate.py --staged --enforce --allow-existing-code-change
```

FORBIDDEN_IMPORT > 0 → STOP  
SECURITY_PATTERN > 0 → STOP  
CIRCULAR_IMPORT > 0 → STOP  
quality gate errors > 0 → STOP  
지도↔골격 대조(`tools/code_map/skeleton_gate.py`, pre-commit 자동·차단) FAIL → 안내된 `registry_sync.py --fix` 로 정본 맞춘 뒤 재커밋. master 병합은 `python tools/merge_stage.py <branch>`(verify_change PASS 일 때만) — 설계 docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md

## 코딩 컨벤션 및 완료 보고 기준 (2026-09-26 추가)

### 재사용 우선
새 함수/유틸을 만들기 전 `tools/hooks/capability_check.py`, `tools/hooks/duplicate_code_check.py`,
Grep으로 유사 기능이 있는지 먼저 확인한다. 있으면 재사용/import, 없을 때만 신규 작성.
검증 안 된 추측성 코드 금지 — 불확실하면 Grep/Read로 실제 시그니처·동작을 확인한 뒤 작성한다.

### 완료 보고 기준
작업이 끝났다고 보고하기 전에 반드시 테스트를 실행하거나 빌드/타입체크를 통과시켜 증거를
확인할 것. 실행해보지 않은 코드를 '완료'로 보고하지 말 것.

### audit-kit 검증 강제 (2026-10-05 추가)
코드를 쓴 직후 `tools/hooks/audit_kit_gate.py`(PostToolUse/Stop 훅)가, 커밋 시점에는 pre-commit 의
`audit_kit_gate.py --staged` 가 **이번 변경으로 새로 생긴** 개발 기준서·구조 문제를 막는다(기존 문제는 안 막음).
audit-kit 는 공개 저장소 `pip install git+https://github.com/JAY-1979-SJW/audit-kit` 로 설치하며, 위치는
`AUDIT_KIT_BIN` 으로 지정한다. **`AUDIT_KIT_REQUIRED=1` 이면 audit-kit 를 못 찾을 때 건너뛰지 않고 막는다** —
검증 없이 통과되는 것을 막으려면 개발 PC 환경변수에 켜 둔다.

### 워크플로
복잡하거나 여러 파일에 걸친 작업은 Explore → Plan(Plan Mode) → Implement → Verify → Commit
순서로 진행한다. Verify 단계는 `tools/verify_change.py`(전체) 또는 세션 빠른 게이트
(ruff+영향 테스트, 바뀐 파일 기준)로 한다 — 전체 pytest는 21분+ 걸리고 멈추는 결함이 있어
매번 돌리지 않는다(2026-10-05 실측: CI 조건 약 16분 25초, 위 gotcha 정정 참조).

### 반복 실수(gotcha)
- 전체 `pytest` 실행 금지 — `tests/test_local_agent_installer_package.py`에서 멈춤. 영향 테스트만.
  (2026-10-05 정정: 위 파일은 커밋 `b13d1216`에서 삭제되어 현재 없다. 같은 날 CI 조건 전체 시험은
  약 16분 25초에 정상 종료했다. 다만 다른 파일에서 '멈춤'이 재현되는지는 확인하지 않았으므로
  금지는 유지한다 — 전체 시험은 오래 걸리므로 영향 시험만 돌린다.)
- ruff는 레거시 오류가 많은 파일이 다수 존재 — 새 훅은 "이번 편집으로 새로 생긴 오류"만 차단.
- Windows에서 훅은 셸 스크립트가 아니라 python 스크립트로 작성(기존 관례, PowerShell/cmd 차이 회피).
- `tools/hooks/stop_fast_verify.py`는 세션별 편집 기록(`data/.session_edits/<session_id>.json`,
  `post_edit_fast_gate.py`가 PostToolUse마다 기록)만 검사한다 — 최초 구현은
  `git status --porcelain` 전체를 대상으로 해서 다른 세션의 미커밋 변경분까지 차단 사유에
  끼어드는 문제가 있었고(code-reviewer 서브에이전트 실측 지적, 2026-09-26), 세션별 목록 방식으로
  수정해 해결됨. 기록이 없거나 비어 있으면 즉시 통과. 기록 파일은 7일 지나면 자동 정리된다.
- **CDP/Playwright 브라우저 연결은 항상 `scripts/web_connector.py`의 공유 연결
  (`run_on_browser_thread` + `open_page`/`get_page_by_url`)을 쓴다 — 호출마다
  독자적으로 `sync_playwright().start()` + `connect_over_cdp()` 를 새로 맺지 않는다.**
  (2026-09-29, docs/defect_index.json #72~#76) 새 연결을 매번 맺으면 웹소켓 자체는
  즉시 붙어도(`<ws connected>`) Playwright 내부 핸드셰이크가 브라우저의 기존 탭
  상태에 따라 정확히 180000ms(Playwright 고정 타임아웃) 멈출 수 있다 — 원시 CDP
  HTTP(`/json`)는 항상 0.5초 이내 응답하므로 브라우저 자체 문제가 아니라
  "매번 새로 연결"하는 방식 자체가 문제다. Gmail(`gmail_cdp_reader.py`)은 처음부터
  공유 연결을 써서 이 문제를 겪은 적이 없었다.
- **CDP 자동화 호출(브라우저 클릭 시뮬레이션·API 재현 등)이 이유 없이 광범위하게
  느려지거나 타임아웃되면(이전엔 멀쩡했던 Gmail 등 무관한 경로까지 같이 깨지면)
  코드보다 먼저 브라우저 자체 상태를 의심한다** — 장시간 세션에서 탭을 많이
  열고 닫으며 반복 테스트하면 브라우저(Chrome) 세션 자체가 오염돼 이후의 모든
  CDP 연결 핸드셰이크가 느려질 수 있다(2026-09-29 실측: 여러 시간 테스트 후 새로
  기동한 FastAPI 프로세스의 첫 Gmail 호출조차 멈춤 → `scripts/browser/cdp/cdp_force_start.py
  stop` 후 `start`로 브라우저만 재시작(프로필 유지, 로그인 세션 그대로 보존됨)하니
  즉시 정상화). 코드를 계속 고치기 전에 이 재시작부터 시도한다.
- Google 서비스 URL은 `scripts/common/config.py`의 `GOOGLE_URLS` 딕셔너리에서 가져온다
  (하드코딩 금지) — 실제 인증된 세션에서 도착 URL을 확인하지 않고 추측으로
  적으면 리다이렉트/마케팅 페이지로 빠질 수 있다. 새 URL을 추가하기 전엔 실제
  로그인된 CDP 세션으로 `page.goto()` 후 `page.url`을 찍어 확인한다.
- **9222 데몬 Chrome 의 로그인 유지·깨끗한 시작 정책은 `scripts/common/config.py` 의 `CDP_BROWSER_POLICY`
  한 곳에서 정한다**(상세·근거: `docs/architecture/CDP_BROWSER_POLICY.md`). (2026-10-05 실측) 로그인(세션
  쿠키)은 `--restore-last-session` 스위치(**값 없이** — `=false` 도 켜진다) + CDP `Browser.close` 정상
  종료일 때만 재시작 뒤에도 남는다. 종료 신호·강제 종료·전원 차단은 로그인을 잃는다 → 데몬 재시작은
  `python scripts/browser/cdp/cdp_daemon.py restart` 로만. 시작 페이지는 구글 홈(복원된 옛 탭은 시작 직후 정리).
  로그인 확인은 쿠키 이름 존재 여부(참/거짓)로만 하고 값은 읽지 않는다.
- **시험·검증 도구가 9222 브라우저에 접속하면 안 된다** — 사용자 탭이 이동·소멸하고 로그인이 풀린다
  (2026-10-05: 패치가 잘못된 모듈에 걸린 YouTube 시험과, 파일 이름 지정만으로 수집되던
  `tests/integration/manual/` 이 원인). 시험은 가짜 객체만 쓰고 패치는 **실제 호출이 일어나는 모듈**에
  건다. 수동 시험은 `HAEHAN_RUN_MANUAL=1` 일 때만 실행된다. 탭 이동 주체는
  `data/logs/browser_watch.jsonl` 의 `cdp_clients`·`browser_process` 기록으로 추적한다.
- **시험 중 9222 접속은 가드가 막는다 — 해제는 사용자 확인 후에만** (2026-10-05). 루트 `conftest.py` 가
  `tests/cdp_port_guard.py` 로 루프백 9222 접속(소켓·Playwright `connect_over_cdp`)을 시험 중 차단하고,
  실제 9222 를 쓰는 시험(같은 파일의 `REAL_CDP_TESTS`)은 기본 skip 한다. 해제 환경변수
  `HAEHAN_ALLOW_REAL_CDP=1` 은 **사용자 확인 없이 쓰지 않는다.** 가드는 소켓·Playwright 경로만 막으므로
  subprocess 의 curl/taskkill 같은 경로는 못 막는다 — CDP·browser·gmail·youtube·cafe 계열 시험은
  사용자 Chrome 세션 보호를 위해 이 PC 에서 임의로 돌리지 않는다.
- **CI 의 audit-kit·mypy 검사** (2026-10-05). `.github/workflows/ci.yml` 의 verify 단계는 audit-kit 과 mypy 를
  별도 가상환경에 설치(`AUDIT_KIT_BIN` 지정)하고 `verify_change.py` 로 **기준 대비 신규 오류**만 검사한다
  (CI 는 전체 pytest 를 돌리지 않는다). 로컬 커밋 훅에서 "audit-kit 를 찾지 못해 검사 생략"이 나오면 원인은
  `AUDIT_KIT_BIN` 미설정이다 — `AUDIT_KIT_REQUIRED=1` 로 두면 생략 대신 차단된다(위 'audit-kit 검증 강제').
- **Python 3.14 문법 `except A, B:`(괄호 없는 다중 예외)는 유효하다** (2026-10-05, 로컬 3.14 로 실행 확인).
  3.13 이하 기준 도구·검수가 이를 문법 오류로 오판할 수 있으니 오류로 단정하기 전에 실제 인터프리터로 확인한다.
- **`configs/module_registry.json` 병합 충돌** (2026-10-05). master 쪽 내용을 취한 뒤(`git checkout --theirs`)
  `python tools/code_map/registry_sync.py --fix` 로 내 새 파일만 다시 등록하고 `--check` 로 일치를
  확인한다. PR 브랜치는 푸시 직전에 `git merge origin/master` 로 최신을 병합한다.

### 코딩 컨벤션 (2026-09-26 실측 확인)

**언어/프레임워크 버전**
- Python: `3.14.3` (로컬 `python --version` 실측, `pythoncore-3.14` 사용 중)
- FastAPI: `requirements.txt` 기준 `fastapi>=0.111.0` (pydantic은 별도 고정 없이 FastAPI 종속으로 따라감 — 직접 버전 지정 필요 시 `requirements.txt`에 명시)
- admin-web (`admin-web/package.json`): Next.js `14.2.35`, React `^18`, TypeScript `^5`

**네이밍**
- Python 파일·함수: `snake_case` (예: `action_router.py`, `code_map/query.py`)
- 클래스: `PascalCase`
- 사이트/도메인 라우터 파일: `*_router.py` (예: `ai_orchestrator/routers/action_router.py`, `browser_api/router.py`)
- 테스트 파일: `tests/test_*.py` (프로젝트 루트 `tests/` 및 `ai_orchestrator/tests/` 양쪽 존재)

**폴더 구조 (L1~L12 레이어 대응)**
- L2 Policy/Gate → `ai_orchestrator/gates` 등 게이트/정책 모듈
- L3 Connectors → `ai_orchestrator/connectors`, `scripts/<도메인>` (naver, google, eum 등)
- L5 Site Modules → `ai_orchestrator/sites`, 사이트별 `*_router.py`
- L6 Business Workflows → `ai_orchestrator/services`
- L7 Persistence → `ai_orchestrator/persistence`
- L8 Server API → `ai_orchestrator/routers`, `browser_api/router.py`
- L9 Admin UI → `admin-web/`
- L10 Local PC App → `apps/*-standalone` (예: `apps/marketing-standalone`, `apps/youtube-analyzer-standalone`)
- L11 Tests → `tests/`, `ai_orchestrator/tests/`
- 운영 스크립트/게이트: `scripts/ops`
- 레이어 배치의 **정본은 `configs/module_registry.json`** — 이 문서의 "신규 코드 위치 규칙", `docs/architecture/APP_TREEMAP.md`와 배치되면 레지스트리 값을 우선한다.

### 테스트·빌드·린트 명령 (2026-09-26 실행 확인)

- **린트 (파일 단위)**: `python -m ruff check --config configs/ruff.toml <파일경로>` — 새 편집으로 생긴 오류만 확인 (레거시 오류 다수 존재, 위 gotcha 참조)
- **영향 테스트 조회 → 실행**: `HAEHAN_NO_BROWSER_LAUNCH=1 python tools/code_map/query.py tests-for <변경파일>` 로 관련 테스트 목록을 얻은 뒤 해당 테스트만 `pytest` 실행 (전체 pytest 금지, 위 gotcha 참조)
- **전체 변경 검증**: `python tools/verify_change.py --base <기준커밋> --head <대상커밋> [--expect-routes N]`
- **게이트 3종**: 위 "게이트 실행 의무" 섹션 참조 (`codebase_layer_audit.py`, `test_codebase_layer_audit.py`, `quality_gate.py --staged --enforce --allow-existing-code-change`)
- **프론트 타입체크**: `cd admin-web && npm run typecheck` (`tsc --noEmit -p tsconfig.app.json`) — 확인 완료(통과)
- **프론트 빌드**: `cd admin-web && npm run build` (`next build`) — 시간이 걸리므로 필요할 때만
- **서버 기동**: 위 "로컬 개발 스택 포트 구성" 섹션 참조 (FastAPI 8401, Next.js 3000)

## 병렬 실행 규칙

병렬 가능: read-only 감사, 문서 조사, 독립 정적 분석  
병렬 금지: git, DB, 배포, 서버 재시작, 파일 삭제, 권한 변경, secret 작업, 같은 파일 수정  
병렬 결과는 통합 리포트로 병합 → 전체 게이트 직렬 재실행 → commit은 1회만

## 지시문 공통 블록

모든 지시문에 포함할 원칙:
1. 신규 코드는 정해진 레이어, 정해진 디렉터리에만 작성
2. 기존 구현이 있으면 재사용, 중복 구현 금지
3. router = HTTP 처리만 / service = 업무 흐름만 / core = 순수 정책·산식·판정만 / repository = DB만 / adapter = 외부 연동만
4. 역방향 import, 순환 import 금지
5. API 응답 key, DB schema, SQL, 핵심 산식, 보안 정책 임의 변경 금지
6. secret/token/password/env 값 출력 금지
7. 운영 DB write, schema 변경, 서버 배포/재시작, 파일 삭제, 권한 변경은 승인 없이 금지
8. 신규 파일 생성 시 왜 이 위치가 맞는지 보고
9. 작업 후 layer audit, cycle audit, security audit, test 실행
10. PASS/WARN/FAIL로 최종 판정, FAIL 즉시 STOP 보고

---

# EUM (건설근로자공제회) 사이트 탐색 결과 (2026-05-11)

## 사이트 구조

```
eum.cw.or.kr
├── 메인: https://eum.cw.or.kr/main (진입점)
├── 마이페이지: https://eum.cw.or.kr/mypage
└── 관리 섹션
    ├── WEBMAN380M00: 현장별 단말기 목록 (프로젝트별)
    ├── WEBMAN381M00: 단말기 설치계획 (접근 제한)
    ├── WEBMAN382M00: 단말기 철거 (접근 제한)
    ├── WEBMAN390M00: 단말기설치현황 ⭐ 핵심 데이터 소스
    └── WEBMAN400M00: 단말기별 이력관리
```

## 핵심 발견사항 (2026-05-11 재탐색 확정)

### 1️⃣ 단말기 데이터 (최종 확정)
- **현재 임대 중: 22대** (전체 사이트 확인)
- **임대 현장: 22개** (모두 "정상" 상태, 철거일 없음 = 임대 진행 중)
- **임차인: 비전아이(주)** (22개 현장 전체 동일)
- **구매/기타: 사이트에 미표시** (임대 단말기만 목록에 표시)

### 2️⃣ WEBMAN390M00 (단말기설치현황) - 핵심 페이지 + 올바른 추출 방법
- **테이블#1에 실제 44행(헤더2+데이터42)** - `table.querySelectorAll('tr')` 사용 (tbody 아닌 전체 table)
- **각 단말기 = 2행으로 표현**: 행1(14열 주정보) + 행2(13열 보조정보) = 27개 컬럼
- **헤더도 2행**: 행0(NO~총비용 14열) + 행1(단말기ID~잔존가치 13열)
- **필터:** 13개 select (시범사업장여부, 관할지사, 전자카드구분, 의무/자율, 승인상태, 단말기유형, 운용상태, 통신상태, 설치유형, 계약유형, 예외여부, 표시개수, 검색조건)
- **추출 방법:** `table.querySelectorAll('tr')` → 2행씩 묶어 단말기 1개 매핑

### 3️⃣ 27개 컬럼 구조
```
행1 (14열): NO, 고유번호, 단말기번호, 공제가입번호, 공사명, 발주기관, 전자카드구분, 지정업체, 단말기유형, 운용상태, 설치일, 처리건수, 계약유형, 총비용
행2 (13열): 단말기ID, 공사번호, 공사상태, 공사업체, 관할지사, 설치예외, 유통업체, 지정단말기명, 통신상태, 철거일, 설치일수, 설치유형, 잔존가치
```

### 4️⃣ 임대 현장 목록 22개 (2026-05-11 확인)
| NO | 공사명 | 임차인 | 관할지사 |
|----|--------|--------|---------|
| 1 | 부곡커뮤니티센터 신축공사(소방) | 비전아이(주) | 경기지사 |
| 2 | 서울신남초 교사 개축 소방공사 | 비전아이(주) | 서울남부센터 |
| 3 | 양주회천 A-25BL 아파트 정보통신공사 8공구 | 비전아이(주) | 의정부센터 |
| 4 | 2024~2026년 부천지역 열수송관시설 유지보수공사 | 비전아이(주) | 인천지사 |
| 5 | 구둔-일신간 도로확포장공사(1차) | 비전아이(주) | 경기지사 |
| 6 | 수내교 교통우회용 가설교량 설치공사 | 비전아이(주) | 경기지사 |
| 7 | 논현동 221-16 청년주택 신축공사 | 비전아이(주) | 서울남부센터 |
| 8 | 분당 어린이종합지원센터 건립 소방공사 | 비전아이(주) | 경기지사 |
| 9 | 평택우체국 건립 소방공사 | 비전아이(주) | 경기지사 |
| 10 | 인천부평 행복주택 및 도시재생뉴딜 혁신센터 전기공사 | 비전아이(주) | 인천지사 |
| 11 | 연수체육센터 건립 소방공사[계속비] | 비전아이(주) | 인천지사 |
| 12 | 인천남부초 공간재구조화 증개축 소방공사(계속비) | 비전아이(주) | 인천지사 |
| 13 | 서울애니메이션센터 건립 통신공사(장기1차) | 비전아이(주) | 서울지사 |
| 14 | 서울면중초 그린스마트 미래학교 개축 소방공사(장기계속) | 비전아이(주) | 서울지사 |
| 15 | 자전거주차장 내 소공연장 증축 및 리모델링 공사(소방) | 비전아이(주) | 서울지사 |
| 16 | 신선어린이공원 지하주차장 조성공사 | 비전아이(주) | 인천지사 |
| 17 | (주)수정실업 공장 신축공사 | 비전아이(주) | 경기지사 |
| 18 | 만경지구 수리시설개보수사업 토목건축기계공사 | 비전아이(주) | 전주센터 |
| 19 | 그린스타트업타운 복합허브센터 건립공사(건축) | 비전아이(주) | 광주지사 |
| 20 | MTV근로자지원시설 건립공사(전기) | 비전아이(주) | 인천지사 |
| 21 | 영천경마공원 1단계 건설 전기공사 | 비전아이(주) | 대구지사 |
| 22 | 24-D-00부대 생활관 개수 통신공사(2040) | 비전아이(주) | 대전지사 |

## 단말기 임대 전체 파이프라인

```
[1단계] 신규 현장 발굴/홍보
  EUM WEBMAN380M00 → 신규 공사 목록 → 홍보 메일 발송 → 계약 체결

[2단계] 계약 및 EUM 등록 (수동)
  임대 계약서 → EUM 설치 신청 등록 → 공제회 승인 확인

[3단계] 단말기 설치 (수동)
  현장 방문 → 설치 → EUM 설치일 등록 → 통신 확인

[4단계] 운용 모니터링 (자동화됨)
  주 1회 WEBMAN390M00 추출 → 통신단절/미사용 감지 → 조치

[5단계] 준공/임대 종료 (수동)
  준공 통보 → EUM 철거 신청 → 단말기 회수

[6단계] 정산 및 서류 종료 (수동)
  임대료 정산(설치일수 기준) → 계약 종료 서류 → 재고 복귀
```

## 자동화 로직

> 2026-09-29 정정(docs/defect_index.json #28): 아래에서 예전에 안내하던
> `scripts/eum_extract_all_devices.py` / `scripts/eum_business_dashboard.py` /
> `scripts/archive/eum_legacy/eum_device_inventory_automation.py` 는 2026-09-23
> 정리에서 삭제됨(`docs/deleted_code_index.md`의 `scripts` 항목, 복원은 그 문서 안내
> 그대로 `git checkout backup/pre-cleanup-20260923 -- <경로>`). 삭제 후에도 실행법을
> 계속 안내하고 있었던 걸 바로잡는다. 현재 단말기설치현황(WEBMAN390M00) 자동 점검의
> 실제 진입점은 `scripts/eum/daily_check.py`(매일 자동 실행, 로그인 세션 없으면 조용히
> 건너뛰고 다음날 재시도 — 단, 이 건너뛰기가 정말 "정상"인지는 defect_index #13 참고:
> 매번 `cdp_unavailable`로 건너뛰어 조용한 실패일 수 있음, 별도 확인 필요).

### 올바른 추출 로직 (WEBMAN390M00, 삭제된 스크립트가 실측으로 확인했던 내용 — 여전히 유효)
```python
# table.querySelectorAll('tr') 로 전체 TR (tbody 아닌 table 전체)
# 2행씩 묶기: 14열(주정보) + 13열(보조정보) → 단말기 1개
# 헤더2행 스킵 (td_count == 0인 행)
```

### 실행 방법
```bash
python scripts/eum/daily_check.py
```

## 사이트맵 파일
- `data/sitemap/eum.cw.or.kr_complete_sitemap_v2.json` - 전체 구조 + 자동화 가이드
- `data/eum_all_devices_complete.json` - 최신 완전 추출 데이터 (22대)

## 주의사항
- ⚠️ 철거일 없음 = 임대 진행 중 (22개 현장 전부 정상 임대 중)
- ⚠️ 영천 현장 = NO 21 (영천경마공원 1단계 건설 전기공사) 확인됨
- ⚠️ 임차인은 모두 "비전아이(주)" - 단말기 사용하는 실제 공사업체는 "공사업체" 컬럼에 별도 기재
- ⚠️ tbody 기반 추출은 실패 → 반드시 `table.querySelectorAll('tr')` 사용

---

# 네이버 OpenAPI 운영규칙 (2026-05-29 확인)

## 앱 정보

| 항목 | 값 |
|------|-----|
| 앱 이름 | 해한AI검색 |
| Client ID | `.env` 의 `NAVER_OPENAPI_CLIENT_ID` 참조 |
| Client Secret | `.env` 의 `NAVER_OPENAPI_CLIENT_SECRET` 참조 |
| 개발 상태 | **개발 중** (검수 전 — 본인 계정만 로그인 가능) |
| 카테고리 | 기타 |
| 앱 URL | `https://developers.naver.com/apps/#/myapps/cSW_L1d1Gic9ElCbzA_k/overview` |

## 등록된 API

| API | 유형 | 일일 허용량 | 상태 |
|-----|------|------------|------|
| **검색** (`search/**`) | 비로그인 오픈 API | 25,000 회/일 | ✅ 활성 |
| 네이버 로그인 | 로그인 오픈 API | — | 개발 중 (검수 전) |

## 서비스 환경 설정

| 환경 | URL |
|------|-----|
| 비로그인 WEB | `http://localhost` |
| 로그인 PC 웹 서비스 URL | `http://localhost` |
| 로그인 Callback URL | `http://localhost/callback` |

⚠️ 실서비스 배포 시 위 URL을 실제 도메인으로 변경 필요

## 운영 정책

```
NAVER_OPENAPI_DRY_RUN=false   # 실제 호출 활성화
NAVER_SEARCH_DB_ENABLED=true  # SQLite DB 적재 활성화
일일 한도: 25,000 회 (검색 API)
```

### 금지 사항 (개발자센터 정책 + 보안 정책)
- 유료 API 키 발급 금지
- 광고 캠페인 생성 / 예산 설정 / 결제 등록 금지
- 카페 쓰기 API — 현재 앱에 미등록, 사용 금지
- Client ID / Secret 원문 로그 출력 금지
- 일일 허용량 초과 자동 호출 금지

### 허용 범위 (비로그인 검색 API) — 2026-08-14 실측 검증

| 엔드포인트 | 실제 결과 |
|---|---|
| 블로그 `GET /v1/search/blog.json` | ✅ 정상 |
| 뉴스 `GET /v1/search/news.json` | ✅ 정상 |
| 쇼핑 `GET /v1/search/shop.json` | ❌ **404 `SE05` — 앱에 미등록** |

- 정렬: `sim`(유사도) / `date`(날짜) 만 허용
- ⚠️ **쇼핑 검색 API는 이 앱에 등록되어 있지 않다.** 같은 키로 블로그·뉴스는
  정상 응답하는데 쇼핑만 `SE05 (존재하지 않는 검색 api)` 를 반환한다.
  개발자센터에서 쇼핑 검색 API를 앱에 추가 등록하기 전까지 사용 불가.
- 경쟁사 가격 조사는 `scripts/naver/shopping/crawl.py`(공개 검색결과 CDP 수집)를 사용.
  단, 네이버가 자동화 브라우저에 축소된 결과를 주므로 **페이지당 5건**이 한계이고,
  `max_pages=10` 으로 약 50건(광고 포함) 수집이 현실적 상한이다.

## 카페 API 미등록 확인

사용자가 앱 등록 시 **카페 API를 선택하지 않음** — 검색 API만 등록됨.
카페 자동화는 **CDP 브라우저 세션 방식**으로만 운영 (OpenAPI 미사용).

## 네이버 블로그 이미지 첨부 — Unsplash API (2026-08-14 추가)

네이버 블로그 글에 사진을 첨부할 때는 **Unsplash API**를 사용한다 (AI API 아님, 승인 절차 대상 아님, 상시 허용).

- 환경변수: `UNSPLASH_ACCESS_KEY` (`.env` 참조, 원문 로그 출력 금지)
- 이미 구현되어 있음 — 신규 코드 불필요: `ai_orchestrator/connectors/naver_blog/naver_blog_router.py`
  - 검색: `GET https://api.unsplash.com/search/photos` (쿼리 영어 3단어 이내, orientation=landscape)
  - 로컬 캐시: `data/unsplash_images.json`
  - 다운로드: `data/blog_uploads/unsplash_*.jpg` (Unsplash 정책상 `download_location` 트리거 필요)
- 원본 출처: `C:\work\30. 해한 AI 홈페이지\haehan-ai\.env.local` 에서 최초 발급됨. 이 프로젝트 `.env`에도 동일 키 보관.
- 사용자가 매번 "사진 API 써서" 지시하지 않아도, 네이버 블로그 사진 첨부 요청 시 기본으로 이 경로를 사용한다.

## CDP 강제 시작

브라우저 CDP가 내려갔을 때:
```bash
python scripts/browser/cdp/cdp_force_start.py start [URL]
python scripts/browser/cdp/cdp_force_start.py status
python scripts/browser/cdp/cdp_force_start.py stop
```
- 샌드박스 게이트 우회 버전 (`assert_browser_launch_allowed` 미호출)
- 프로필: `data/cdp_profile/ai_chrome`
- PID 파일: `data/cdp_force_pid.json`

---

# YouTube Data API / OAuth 운영규칙 (2026-05-30 설정 완료)

## GCP 프로젝트 정보

| 항목 | 값 |
|------|-----|
| 프로젝트 | haehan-ai |
| API 키 이름 | haehan-youtube-data-api |
| OAuth 클라이언트 | haehan-youtube-server-captions (웹 애플리케이션) |
| 콜백 URI | `https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback` |

## 환경변수 (.env 기준)

```
YOUTUBE_DATA_API_KEY=<.env 파일의 실제 값 참조 — 문서에 원문 기록 금지, 2026-09-30 유출 정정>
YOUTUBE_CLIENT_SECRETS_FILE=ai_orchestrator/storage/secrets/youtube_oauth_client.json
YOUTUBE_OAUTH_TOKEN_FILE=ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json
YOUTUBE_OAUTH_REDIRECT_URI=https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback
YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED=true
```

## OAuth 토큰 스코프 (2026-05-30 인가 완료)

| 스코프 | 용도 |
|--------|------|
| `youtube.force-ssl` | 자막 조회, 댓글 읽기 |
| `youtube.upload` | 영상 업로드 |
| `userinfo.profile` / `email` / `openid` | 계정 확인 |

- 토큰 파일: `ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json`
- refresh_token 포함 → 자동 갱신 가능
- 인가 계정: skyjwshin@gmail.com

## 토큰 만료 시 재인가 절차

```python
from scripts.youtube import oauth
result, _ = oauth.build_auth_plan({'scope': 'force-ssl upload'})
# result['auth_url'] 을 브라우저에서 열어 승인
# 콜백 code= 파라미터 추출 후:
result2, _ = oauth.exchange_code({'code': '<CODE>'})
```

또는 데스크 앱에서 자동 처리 (아래 참조).

## 데스크 앱 YouTube OAuth 자동 로그인

- `admin-web/electron/main.js` — 앱 시작 시 토큰 유효성 검사
- 토큰 없거나 만료 시 → 승인 다이얼로그 표시
- 사용자 승인 → OAuth 팝업 자동 열기 → 콜백 감지 → 토큰 저장
- 토큰 파일 경로: `config.json`의 `youtube_token_file` 키로 관리

## 금지 사항

- API 키 / client_secret 원문 로그 출력 금지
- 타 계정 영상 무단 업로드 금지
- youtube.upload 스코프 자동 실행 — 사용자 명시 승인 후에만
- public 공개 영상 업로드 — 별도 승인 필수 (기본값: private)

---

# 로컬 개발 스택 포트 구성 (2026-05-30 기준)

| 서비스 | 포트 | 비고 |
|--------|------|------|
| FastAPI 서버 | 8401 | `python -m uvicorn ai_orchestrator.asgi:app --host 127.0.0.1 --port 8401` |
| Next.js 프론트엔드 | 3000 | `cd admin-web && npm run dev` |
| Electron 앱 | — | `dist-electron/win-unpacked/Haehan AI.exe` |

## 서버 시작 순서
1. FastAPI: `python -m uvicorn ai_orchestrator.asgi:app --host 127.0.0.1 --port 8401`
2. Next.js: `cd admin-web && npm run dev`
3. Electron 앱 실행

## Electron 앱 설정 경로
- userData: `%APPDATA%\Haehan AI\config.json`
- 라이선스 키: config.json 의 `license_key` 참조 (원문 출력 금지)
- asar 위치: `dist-electron\win-unpacked\resources\app.asar`

## Electron asar 패치 절차
```powershell
$asarPath = "C:\work\01. haehan-ai-orchestrator\dist-electron\win-unpacked\resources\app.asar"
$extractDir = "C:\work\01. haehan-ai-orchestrator\dist-electron\app-extracted"
Set-Location "C:\work\01. haehan-ai-orchestrator\admin-web\electron"
# 1. 추출
node -e "const asar=require('@electron/asar');asar.extractAll(process.argv[1],process.argv[2]);console.log('ok');" -- $asarPath $extractDir
# 2. 수정된 파일 복사
Copy-Item "admin-web\electron\main.js" "$extractDir\main.js" -Force
Copy-Item "admin-web\electron\shell.html" "$extractDir\shell.html" -Force
# 3. 재패킹
node -e "const asar=require('@electron/asar');asar.createPackage(process.argv[1],process.argv[2]).then(()=>console.log('packed'));" -- $extractDir $asarPath
```

## YouTube OAuth 자동 팝업 정책 (2026-05-30 변경)
- 앱 시작 시 자동 팝업 **제거** (기존: 2초 후 자동 표시)
- 연결 방법: 트레이 메뉴 "YouTube 계정 재연결" 또는 화면 내 "● YouTube 미연결" 버튼 클릭
- `checkYouTubeToken()` 은 packed app에서 `process.execPath` 기준 경로로 토큰 파일 탐색

## shell.html webview 레이아웃
- body: `display: flex; flex-direction: column; height: 100%`
- webview: `flex: 1; min-height: 0` — calc(100vh) 대신 flex로 전체 높이 채움
