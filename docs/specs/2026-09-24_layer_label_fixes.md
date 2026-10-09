# 층 라벨 오분류 정정 + 독립 앱 2개 층 규칙 제외 (2026-09-24)

```yaml
spec:
  id: layer-label-fixes
  status: done
  files:
    modify:
      - configs/module_registry.overrides.json
      - configs/module_registry.json
      - tools/code_map/classify.py
  acceptance:
    - cmd: "python tools/code_map/skeleton_gate.py"
      expect: exit0
```

## 배경

`codebase_layer_audit`/`code_map` 재구축(OpenAI 유료 API 코드 삭제 후, import_edges 를
실제 import 로만 판정하도록 수정된 이후) 기준으로 층간 위반을 재계산하니 155건(사전 분석) →
**98건**(실측)이었다. 그중 다수가 룰 기반 이름 매칭(`auth`→L2, `gate`→L2, `workflow`/`batch`/
`runner`→L6, 근거 부족 시 기본값 L4)으로 인한 **라벨 오분류**였고, 실제 코드 로직과 불일치했다.

## 방법

1. `python tools/code_map/build.py && python tools/code_map/modules.py` 로 현재
   `data/code_map/map.json`·`inversions` 재계산.
2. `configs/module_registry.json` 의 `allowed_deps` 를 `import_edges` 에 직접 적용해
   (`__init__.py` 제외, L1~L10 대상만) 위반 목록 재산출 → 98건, `modules.py` 결과(98)와 일치 확인.
3. 위반이 큰 그룹부터 파일 내용을 직접 읽어(docstring·import·실제 동작) 라벨이 맞는지 검증.
   근거가 분명한 것만 `configs/module_registry.overrides.json` 에 `source: manual` 로 기록하고
   `python tools/code_map/classify.py` 로 `configs/module_registry.json` 에 반영.
4. `apps/ig-comment-dm-bot/`, `apps/marketing-standalone/` 는 독립 제품으로 분리 결정된 저장소이므로
   추적 파일 26개(코드 파일, `.py`)를 layer `"APP"` 으로 오버라이드. `"APP"` 은
   `configs/module_registry.json` 의 `allowed_deps`/`tools/code_map/modules.py` 의
   `CODE_LAYERS = {L1..L10}` 어디에도 없으므로 방향 검사에서 자동 제외됨(직접 코드 확인).
5. `classify.py` 요약 출력이 `"APP"` 처럼 숫자가 아닌 층 문자열에서 `int()` 캐스팅으로 죽는 버그를
   1줄 방어 처리(`x[0][1:].isdigit() else 999`)로 고쳤다 — 레지스트리 본문(`REGISTRY.write_text`)은
   이 줄보다 먼저 실행되므로 라벨 반영 자체는 이 버그와 무관했지만, 도구가 매번 비정상 종료하면
   안 되므로 함께 고쳤다.

## 결과: 위반 98 → 51

관계없는(코드 자체 문제, type C/D) 위반은 라벨을 건드리지 않고 그대로 남겼다.

## 라벨 정정 테이블 (라벨 오분류만, 코드 미변경)

| 파일 | 이전 → 정정 | 근거 | 해소된 위반 |
|---|---|---|---|
| `scripts/eum/auth.py` | L2 → L5 | eum.cw.or.kr 전용 ID/PW 자동로그인 구현(WEBLOG400M00 URL, `human_input`/`web_connector` 호출). 정책 판단이 아니라 사이트별 자동화. `auth` 이름만으로 L2 룰 매칭됨 | L2→L4 3건 |
| `scripts/gabia/auth.py` | L2 → L5 | 가비아 사이트 전용 로그인 자동화(`login_detector` 호출) | L2→L4 1건 |
| `scripts/google/auth.py` | L2 → L5 | 구글 사이트 전용 로그인 자동화(`login_detector`·`local_agent` 호출) | L2→L4 2건 |
| `scripts/hanafax/auth.py` | L2 → L5 | 하나팩스 사이트 전용 로그인 자동화(`credentials` 호출) | L2→L4 1건 |
| `scripts/kakao/auth.py` | L2 → L5 | 카카오 사이트 전용 로그인 자동화(`login_detector` 호출) | L2→L4 1건 |
| `scripts/naver/auth.py` | L2 → L5 | 네이버 ID/PW 자동 로그인 모듈 — 사람처럼 타이핑, 캡차 감지, `login_detector` 호출. 정책 게이트가 아니라 자동화 구현체 | L2→L4 2건 |
| `scripts/naver/searchad/auth.py` | L2 → L5 | 네이버 검색광고 사이트 전용 로그인 자동화(`credentials` 호출) | L2→L4 1건 |
| `scripts/auth_session.py` | L2 → L4 | 쿠키/localStorage/sessionStorage 저장·복원 범용 엔진 — 특정 사이트 로직 없음, 어느 사이트든 재사용. `auth` 이름만으로 L2 룰 매칭됨 | L2→L4 2건(자체 해소) |
| `scripts/naver/auth_window_gate.py` | L2 → L4 | 파일 docstring 이 자기 자신을 `"L4 Browser Engine 계층"` 이라고 명시. `scripts.common.auth_window_gate` 범용 엔진에 `NAVER_PROFILE` 만 주입하는 하위호환 래퍼 | 표기 정합성 |
| `scripts/google/oauth_console_fill.py` | L2 → L5 | Google Cloud Console(`console.cloud.google.com`) OAuth 클라이언트 생성 화면을 실제로 채우는 사이트 자동화(`web_connector`·`managed_console` 호출, `FINAL_BUTTON_LABELS` 등 DOM 라벨 처리). `gate` 계열 이름으로 L2 오분류 | L2→L5 1건, L2→L4 1건 |
| `scripts/quality_gate.py` | L2 → L12 | 리포지토리 스테이지 변경 감사 CLI(quality gate) — 앱 도메인 정책이 아니라 운영 도구. `gate` 이름만으로 L2 오분류. L12(문서·운영 도구)는 방향 규칙 밖 | L2→L4 1건 |
| `scripts/required_quality_gate.py` | L2 → L12 | pre-commit/pre-push 필수 게이트 실행 CLI(빌드·배포·브라우저 미실행) — 운영 도구 | L2→L4 1건 |
| `scripts/module_quality_gate_common.py` | L2 → L12 | `module_quality_gate` 운영 도구의 공용 상수·dataclass·헬퍼 | L2→L4 1건 |
| `scripts/credentials.py` | L4(기본값) → L1 | 자격증명 Fernet 암호화 저장/로드 순수 유틸(`data/credentials.json`) — 브라우저·CDP 없음. `security_utils.py` 와 동일 성격의 공용 헬퍼 | L2→L4 4건, L4→L1 자체 해소 |
| `scripts/runtime_temp.py` | L4(기본값) → L1 | 런타임 임시 디렉터리 후보 경로 계산 순수 함수 — 외부 IO 없음 | L2→L4 2건 |
| `scripts/realtime_audit.py` | L4(기본값) → L7 | `data/logs/realtime_audit.jsonl` 에 감사 이벤트 기록/조회 — L7(저장·감사) 정의에 정확히 부합 | L2→L4 3건, L7→L4 2건 |
| `security_utils.py` | L4(기본값) → L1 | 로그·감사 이벤트 민감정보 마스킹 정규식/헬퍼(`REDACTED`, `SENSITIVE_KEYS`) 순수 함수 | L1→L4 1건 |
| `app.py` | L4(기본값) → L8 | "시나리오 실행기" — `policy_engine`/`risk_assessor`/`approval_manager` 오케스트레이션 후 `dashboard.py`(Flask, L8) 부팅. 브라우저 엔진이 아니라 최상위 실행 진입점 | L4→L8 1건 |
| `scripts/gabia/site_profile.py` | L5(저신뢰) → L2 | `SiteProfile`(`SiteActionPolicy`·`GateDecision`·`SiteCapability`) 선언만 포함, 실제 자동화 코드 없음 — 정책 선언 | L2→L5 1건 |
| `scripts/g2b/site_profile.py` | L5(저신뢰) → L2 | G2B 사이트 프로필 — action 분류 상수 골격 정책 선언만(docstring: "실제 접속·로그인·투찰 구현 없음") | L2→L5 1건 |
| `scripts/google/workflows.py` | L6 → L5 | google 도메인 site module 내부에서만 쓰는 public API aggregator(leaf 모듈 re-export). 다른 도메인이 부르는 범용 업무흐름이 아님. `workflow` 이름으로 L6 오분류 | L5→L6 10건 |
| `scripts/google/workflows_actions.py`/`_catalog.py`/`_common.py`/`_execute.py`/`_report.py` | L6 → L5 | `workflows.py` aggregator 의 leaf 모듈(google 도메인 내부 상세 구현) — `workflows.py` 와 함께 정정 필요(정정 안 하면 새 L5→L6 위반 5건 생성됨을 재계산으로 확인) | L5→L6 5건 |
| `scripts/hanafax/batch.py` | L6 → L5 | 하나팩스 큐(JSONL) 기반 순차 발송 — `router.py`(L5)와 같은 폴더의 hanafax 도메인 전용 상세 구현 | L5→L6 1건 |
| `scripts/hiworks/mail_batch.py` | L6 → L5 | 하이웍스 1건씩 순차 발송 배치 계획/실행 — hiworks 도메인 전용 상세 구현 | L5→L6 1건 |
| `scripts/hiworks/workflows.py` | L6 → L5 | 하이웍스 영업메일 준비(`mail.fill_compose`·`schemas` 호출) — 다른 도메인이 재사용하지 않는 hiworks 전용 구현 | L5→L6 1건 |
| `scripts/naver/cafe/list_background_runner.py` (re-export stub) | L6 → L5 | naver/cafe 도메인 background 수집 러너로 재export하는 하위호환 stub | L5→L6 1건 |
| `scripts/naver/cafe/background/list_background_runner.py` (실 구현) | L6 → L5 | 위 stub 이 감싸는 실제 구현 — 함께 정정하지 않으면 새 위반 생성됨을 확인 | 표기 정합성 |

## 검증한 결과 라벨 유지(변경 안 함)

- `ai_orchestrator/connectors/naver_blog_router.py` — 실제 `fastapi.APIRouter` 정의, 엔드포인트
  본체(`require_role`, `naver_blog_router = APIRouter(...)`). 이미 L8 정답, 정정 불필요.
- `ai_orchestrator/browser_tool/g2b_public_notice_dryrun_adapter.py`,
  `..._execution_gate.py` — 레지스트리에 이미 `source: confirmed`(사람이 확정)로 L6 유지 사유가
  명시돼 있음("dryrun 감싸는 워크플로 어댑터", "실행 여부를 게이트하고 직접 트리거하는 오케스트레이터").
  기존 확정을 뒤집을 새 근거가 없어 **재정정하지 않고 unresolved 로 남김**.

## 독립 앱 2개 — 층 규칙 제외

`apps/ig-comment-dm-bot/` (13개 코드 파일), `apps/marketing-standalone/` (13개 코드 파일) 총 26개
추적 파일을 `configs/module_registry.overrides.json` 에 `layer: "APP"` 로 등록.
사유: `"독립 제품 — 저장소 층 규칙 제외(사용자 결정 2026-09-24)"`.

확인: `tools/code_map/modules.py` 의 `CODE_LAYERS = {f"L{i}" for i in range(1, 11)}` 및
`ls not in CODE_LAYERS` 가드(85·104행)가 `"APP"` 층 파일을 방향 검사·역방향 검사에서 자동 스킵함을
코드로 직접 확인했다(수정 불필요).

## 도구 버그 수정 (1줄)

`tools/code_map/classify.py` 요약 출력에서 `"APP"` 처럼 숫자가 아닌 층 문자열을
`int(x[0][1:])` 로 캐스팅하다 `ValueError` 로 비정상 종료하는 버그를
`int(x[0][1:]) if x[0][1:].isdigit() else 999` 로 방어. 레지스트리 파일 쓰기는 이 줄보다 먼저
실행되므로 라벨 반영에는 영향 없었지만, 도구가 매번 실패 종료하면 안 되므로 함께 고쳤다.

## 미해결(unresolved) — 라벨 근거 불충분, 코드 미변경

아래는 내용을 확인했으나 라벨을 바꿀 만한 명확한 근거가 없어 그대로 남긴 것들이다(위반으로 계속
집계됨, 코드/아키텍처 조정이 필요한 type C/D 성격에 가까움):

- `ai_orchestrator/agent_hub/models.py -> ai_orchestrator/agent_hub/registry/facade.py` (L1→L4):
  `local_agent_registry.py` 는 에이전트/작업큐 lifecycle 관리 aggregator로 L4(브라우저 엔진)는
  명백히 틀렸지만, L6(업무흐름)·L7(상태 저장소) 둘 다 그럴듯해 라벨을 확정하지 못함.
- `scripts/site_registry.py -> {eum,gabia,google,kakao,naver}/auth.py, login_detector.py`
  (L1→L5, L1→L4): site_registry.py 자체가 여러 도메인의 구체 구현을 직접 import하는 레지스트리라
  L1(순수 계약)이 맞는지 자체가 의문 — 라벨보다 구조 조정이 필요한 문제로 판단, 손대지 않음.
- `L4→L5`(8), `L7→L5`(8), `L4→L6`(7), `L6→L8`(3), `L7→L2`(2), `L4→L8`(2), `L2→L4`(2),
  `L2→L6`(1), `L1→L2`(1), `L1→L6`(1) 그룹 나머지: 파일 내용은 라벨과 일치하고(예:
  `local_agent/browser_approval_db_store.py`(L7)가 `browser_approval_verifier.py`(L2)를 부르는 것은
  저장소가 정책 검증기를 부르는 역방향 — 라벨 문제가 아니라 호출 방향 자체가 역전된 실제 설계
  이슈), 라벨을 바꿔서 해소할 성격이 아니므로 그대로 둠.

## 검증

- `python tools/code_map/skeleton_gate.py` → PASS(4/4)
- `python tools/code_map/registry_sync.py --check` → OK(2362 == 2362)
- `pytest tests/test_skeleton_gate.py tests/test_codebase_layer_audit.py tests/test_module_boundaries.py -q` → 35 passed
- 위반 수: `python tools/code_map/modules.py` → `inversions=51`(재계산 스크립트와 일치)
