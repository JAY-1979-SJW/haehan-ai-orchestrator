# 앱 실검증 결함 D1~D4 수정 기준서 (2026-10-04)

근거: `docs/reports/2026-10-04_app_live_verification.md`. 사용자 지시("순서대로 해")에 따라 D1 → D2 → D3 → D4 순으로 항목마다 수정·검증한다.
각 항목은 기준서(이 문서) → 변경 → 영향 검증 → 로컬 커밋 순이며, 푸시는 모든 항목이 끝난 뒤 다시 확인받는다.

## D1 — 홈 AI 콘솔 등 메일 승인 카드 미표시

### 현상
홈 AI 콘솔에서 메일 초안을 요청하면 AI 가 초안을 만들고(상태 pending) "아래 카드에서 승인하세요"라고 안내하지만, 화면에는 `[[mail-draft:<id>]]` 표식만 보이고 카드가 없다. 사용자가 승인할 방법이 없다.

### 원인
`UniversalChat` 의 `MessageBody` 는 `[[fax-approve:…]]` 만 기본으로 카드로 바꾸고, 메일 카드 규칙(`[[mail-draft:…]]`)은 메일함 패널(`MailAiPanel`)만 `extraCards` 로 주입한다. 홈 콘솔(`app/page.tsx`)·`AiDock`(모든 화면의 AI 상담)·공무·블로그 창은 주입하지 않는다. 그런데 AI 는 직원 지침 6번("초안·승인 카드가 있는 기능은 카드로")과 앱 도구 설명 때문에 어느 창에서든 표식을 낸다.

### 변경 (admin-web, L9)
1. `components/chat/mailDraftCards.tsx` 신규: `MAIL_DRAFT_CARDS`(= `[[mail-draft:<32자 16진>]]` → `MailDraftCard`). 팩스 카드가 `components/chat/` 에 있는 것과 같은 위치.
2. `UniversalChat.tsx`: 기본 카드 목록에 `MAIL_DRAFT_CARDS` 를 포함하고 화면이 준 `extraCards` 와 합친다. 같은 규칙(`mark.source` 동일)은 한 번만 쓴다 — 메일함 패널은 그대로 두어도 카드가 두 번 그려지지 않는다.
3. `MailAiPanel.tsx` 는 변경 없음(중복 제거로 호환).

### 의존 방향 (개정)
최초 구현은 `components/chat/` → `app/mailbox/components/MailDraftCard` 역방향 import 였고, `verify_change` 가 모듈 순환 `app/mailbox` ↔ `components/chat`(80 → 81)을 새 문제로 잡아 FAIL 했다. 그래서 카드(`MailDraftCard.tsx`)·API 클라이언트(`mailDraftApi.ts`)·`formatSize` 를 `components/chat/` 로 옮기고(git mv), 메일함의 옛 경로(`lib/draftApi.ts`·`components/MailDraftCard.tsx`)는 재수출 파일로 남겨 메일함 안의 기존 import 가 그대로 동작하게 했다. `lib/format.ts` 는 `formatSize` 를 공용 위치에서 재수출한다. 의존은 화면(`app/mailbox`) → 공용(`components/chat`) 한 방향이다.

### 불변
API·DB·정책·승인 흐름 변경 없음. 보내기는 여전히 카드 버튼(사람)으로만 되고 AI 허용 API 에 send 는 없다.

### 검증
- `npm run typecheck`, `npm run lint`(바뀐 파일).
- 실제 앱: 홈 AI 콘솔에 초안 요청 → 카드(`승인하고 보내기`/`취소`)가 뜨는지 확인. 발송은 누르지 않고 `취소` 로 정리. 서버 로그에 send 호출 없음.
- 메일함 패널에서 카드가 한 번만 뜨는지(중복 없음) 확인.

### D1 구현 결과
`components/chat/mailDraftCards.tsx` 신규, `UniversalChat.tsx` `MessageBody` 가 기본 카드(메일 초안) + 화면 주입 카드를 합치고 같은 규칙은 한 번만 쓴다. 실제 앱: 홈 콘솔에서 초안 요청 → 승인 카드 표시(버튼 1개, 표식 텍스트 없음). 메일함 패널의 채팅 말풍선 안 카드는 1개(패널 아래 "승인 대기 초안 목록"의 카드는 기존 설계). typecheck·lint 통과. 발송 호출 0건.

## D2 — `data/logs/app.log` 로그 회전 실패 (WinError 32)

### 원인
`scripts/logger.py` 가 `data/logs/app.log` 를 표준 `RotatingFileHandler`(5MB×3)로 쓴다. 여러 프로세스(API·에이전트·CDP 데몬)가 같은 파일을 열고 있는 Windows 에서는 회전(`os.rename`)이 막히고, 표준 핸들러는 로그 한 줄마다 회전을 다시 시도하며 매번 "--- Logging error ---" 를 낸다(실검증 중 112회). 파일이 이미 5MB(5,243,153바이트)를 넘어 계속 재시도 상태였다. (`ai_orchestrator/logging_setup.py` 는 다른 파일 `ai_orchestrator/storage/app.log` 라 무관.)

### 변경
`scripts/logger.py` 에 `_BlockedRotateSafeHandler` 추가: 회전이 `OSError` 로 막히면 60초 동안 재시도하지 않고 기존 파일에 계속 이어 쓰며, 표준 `doRollover` 가 닫은 스트림을 되살린다. 루트 핸들러만 교체. 다른 `RotatingFileHandler` 사용처(`logger.py`·`audit_logger.py`·`executor.py`·`critical_logger.py`)는 서로 다른 파일이라 이번에 변경하지 않는다.

### 검증
- 새 시험 3건(`tests/test_scripts_logger_rotation.py`): 막힌 회전에도 기록 유지·오류 0·재시도 1회, 대기 후 회전 재개, 정상 회전 불변.
- 실제 재현(다른 프로세스가 파일을 연 상태에서 50줄 기록): 표준 핸들러 오류 44건 → 수정 핸들러 0건.
- 실제 앱 기동(5MB 초과 상태의 app.log): 서버 로그 "Logging error" 0건.

## D3 — `/hanafax/status` 500, `/hanafax/address-groups` 사유 불명

### 원인
`get_status` 가 `test_login()` 예외를 잡지 않아 Playwright 브라우저(Chromium) 미설치 시 500. `address_groups` 는 예외 클래스 이름("Error")만 보여 원인을 알 수 없었다.

### 변경
`ai_orchestrator/connectors/hanafax_router.py`: `_failure_text()` 로 미설치를 "브라우저(Playwright Chromium)가 설치돼 있지 않습니다. 관리자가 설치해야 합니다" 로 안내하고, 그 밖은 `<작업> 실패: <예외 이름>`. `/status` 는 기존 로그인 실패와 같은 규약(200 + `ok:false` + 메시지), `/address-groups` 는 502 + 같은 안내문. 응답 모델·키 불변.

### 검증
- 새 시험 4건(`tests/test_hanafax_status_failure.py`) + 기존 하나팩스 시험 7개 파일 151건 통과.
- 실제 앱: `/status` 200 `ok:false` + 안내문, `/address-groups` 502 + 안내문.

## D4 — AI 가 앱의 예약 작업을 조회하지 못함

### 원인
AI 허용 API 목록(`mcp_server.API_REGISTRY`)에 예약 작업 조회가 없어, "예약 작업 있어?" 질문을 Claude Code 세션의 예약 도구(`CronList`)로 답했다(질문과 다른 대상).

### 변경
`API_REGISTRY` 에 `scheduled.list`(GET `/api/v1/scheduled-jobs`, 읽기 전용) 한 건 추가. 만들기·수정·일시정지·지금 실행·삭제·실행 승인은 목록에 없다(화면에서 사람이 한다). 라우트 추가 없음 → 라우트 수 기준선 불변.

### 검증
- `tests/test_employee_protocol.py` 에 시험 추가: `scheduled.` 항목은 `scheduled.list` 하나뿐이고 `scheduled-jobs` 경로의 쓰기 항목이 없다.
- 실제 앱: 같은 질문에 AI 가 앱 기능 `scheduled.list` 로 조회하고 출처를 밝힘.

## D5 — 화면 기능과 AI 허용 API 불일치 (구글 허브)

### 현상
구글 허브 화면은 "캘린더: 오늘 일정" 등 읽기 버튼을 보여 주지만, AI 는 "앱에서 읽을 방법이 없다"고 답했다. AI 허용 API 목록(`mcp_server.API_REGISTRY`)에 해당 항목이 없었다. (하나팩스 화면의 "자동 발송 전체 정지" 상태도 같은 불일치였으나 아래 정정 참고.)

### 변경 (`ai_orchestrator/server/mcp_server.py`)
- 읽기 전용 6개 추가: `google.calendar_today`·`calendar_week`·`drive_recent`·`docs_recent`·`sheets_recent`(OAuth API 기본), `google.youtube_studio_status`.
- 제외: `google/tools/gcp/status`(사용자 Chrome 에 탭을 여는 CDP 방식), `calendar/create-event`(쓰기).
- 가드: 구글 5개는 `source` 쿼리 인자를 줄 수 없다(`forbid_query`). `source=cdp` 는 사용자 브라우저를 여는 방식이라 설명으로만 말리지 않고 `_api_call` 이 요청을 보내기 전에 거부한다. 항목 형식은 `dict[str, str]` 을 유지(쉼표 구분 문자열).
- 라우트 추가 없음(기존 GET 을 AI 가 부를 수 있게 한 것).

### 정정 (하나팩스 kill-switch)
최초 구현은 `hanafax.kill_switch`(GET) 도 허용했으나, 기존 안전 시험 `tests/test_hanafax_p3.py::test_ai_registry_exposes_draft_only_not_approve_or_run` 이 "승인·발송·정지·수신거부 경로는 허용목록에 없어야 한다"(금지 경로 단어에 `kill-switch` 포함)고 정해 두었고 `verify_change` 가 이를 새 실패로 잡았다(D5 이후 하나팩스 시험을 다시 돌리지 않은 누락). 정책을 완화하지 않고 `hanafax.kill_switch` 를 제거했다. 따라서 AI 는 하나팩스 정지 상태를 읽을 수 없다(정책). 정지 상태 확인이 필요하면 화면에서 사람이 본다.

### 검증
- 시험 3건 추가(`tests/test_employee_protocol.py`): 구글 항목·경로·메서드, CDP·쓰기 부재, 어떤 경로도 `kill-switch` 를 포함하지 않음, `source` 거부(요청 0건), 허용 인자는 통과. `API_REGISTRY` 를 쓰는 시험 9개 파일 전부 통과(하나팩스 정책 시험 48건 포함).
- 실제 앱: 구글 패널이 `google.calendar_today`·`google.drive_recent` 를 `source` 없이 호출(서버 로그 확인). 이 PC 에는 구글 OAuth 자격증명이 없어 그 오류를 그대로 보고했다. CDP 우회 없음. (하나팩스 정지 상태 질문에 AI 가 답한 최초 확인은 제거한 항목에 대한 것이라 유효하지 않다.)

## D6 — `/mypage` "가입일 Invalid Date"
원인: 데스크톱 소유자 모드(`AUTH_ENABLED=false`)의 `/users/me` 가 `created_at: ""` 를 돌려주는데 화면이 `new Date("")` 를 그대로 표시했다. 변경: `admin-web/src/app/mypage/page.tsx` — 값이 없거나 날짜가 잘못되면 "-". 서버·API 불변. 검증: typecheck·lint, 실제 앱에서 "가입일 -", "Invalid Date" 없음.

## D7 — 읽기 전용 상태 확인이 Chrome 을 시작함 (재정의)
최초 기록은 "CDP 가 없으면 20초 대기"였으나 원인을 파 보니 `GET /naver/session/live` → `observe` → `default_deps().detect()` 가 CDP 가 꺼져 있으면 `_start_cdp()`(= `cdp_force_start.cmd_start`)로 **Chrome 을 직접 시작**하고 응답을 최대 20초 기다리는 설계였다. 화면(`/naver/session`)이 상태를 폴링하므로 사용자 PC 에서 브라우저가 저절로 뜬다. 앱 실검증 중 실제로 5회 시작됐다(원인의 한 부분은 점검 런처의 포트 치환, 아래 정정 참고).

변경(`ai_orchestrator/workflows/naver_session_guard.py`): `observe(..., start_browser=False)` 기본은 브라우저를 시작하지 않고 CDP 가 꺼져 있으면 바로 `unavailable`. `GuardDeps.detect_starting`(선택 필드, 기존 가짜 부품 호환)을 추가해 자동 로그인 흐름(`ensure_login`·`_observe_after_login`)만 브라우저를 시작한다. `default_deps()` 는 `detect`(시작 안 함)와 `detect_starting` 을 모두 제공. API 응답 형식·키 불변.
검증: 시험 3건 추가(읽기 전용은 시작 안 함, ensure 는 시작 가능, 기본 부품은 CDP 꺼짐에서 Chrome 을 띄우지 않음) + 기존 세션 지킴이 시험 77건 통과(총 80건). 실제 앱: `/live` 20.1초 → 0.06초, 브라우저 시작 시도 0건, Chrome 프로세스 목록 불변. mypy·ruff 통과.
정정: 점검 런처가 `scripts.config.CDP_PORT` 를 9998 로 바꿔 CDP 를 "꺼짐"으로 오판하게 만든 것이 시작을 유발했다. 런처를 브라우저 시작 함수 차단 방식으로 교체했다.

## D8 — `APP_HOST` 0.0.0.0 경고 (종결, 결함 아님)
코드 기본값은 이미 `127.0.0.1` 이다(`config.py`). 이 작업 폴더에는 `.env` 가 없어 `load_dotenv()` 가 상위 폴더를 탐색하다 메인 체크아웃 `.env`(`APP_HOST=0.0.0.0`)를 읽었다. 경고는 그 값에 대해 정확히 동작한 것이므로 코드는 바꾸지 않는다. 서버 배포(`docker-compose.yml`)는 0.0.0.0 을 명시하며 정상이다.

## D9 — 메일함 AI 창이 다른 계정 요청을 말없이 화면 계정으로 처리 (추가 발견)

### 현상
메일함 패널은 화면에서 선택한 계정(`skyjwshin`)에 묶인 창인데(지침: 모든 호출에 이 화면의 계정), 사용자가 "skyjwsin 계정으로 …"라고 해도 AI 가 알리지 않고 `skyjwshin` 으로 초안을 만들었다(보내는 계정은 승인 카드에 표시됨). 또 지침이 "모든 mailbox.* 호출의 query 에 account" 라고 해서 `mailbox.draft`(body 에 account 필요)를 query 로만 불러 첫 호출이 422 로 실패한 뒤 재시도했다.

### 변경 (`admin-web/src/app/mailbox/components/MailAiPanel.tsx`, 지침 문구만)
- 이 화면은 해당 계정 전용이다 — 사용자가 다른 계정을 말하면 호출 없이 "화면 위의 계정 선택을 바꾼 뒤 다시 요청해 주세요"라고만 안내하고, 초안을 만든 뒤에는 보내는 계정을 답변에 적는다.
- `mailbox.*` 조회는 query 의 account, `mailbox.draft` 는 body 의 account (query 에 넣으면 422)로 구분해 명시.
API·DB·정책 불변. 승인 흐름(보내기는 카드 버튼, 사람)도 그대로.

### 검증
typecheck·lint 통과. 실제 앱(메일함 AI 업무 창): ① 다른 계정 요청 → 호출 0건, 화면 계정 전용이라 만들지 않고 계정 선택 변경 안내 ② 화면 계정 요청 → 초안 생성, 답변에 "보내는 계정: skyjwshin@naver.com" 명시, 승인 카드 표시, 초안 API 호출 POST 1건(200)·422 재시도 없음. 테스트 초안은 모두 취소, 발송 호출 0건.

## 영향 검증 (D1~D4 합산)
영향 테스트 197개 파일: 수정 전 164건 실패 → 수정 후 165건. 새로 실패한 2건은 변경과 무관한 기존 문제다 — `test_approval_read_api::test_history_limit_capped_at_500` 는 수정 없는 HEAD 에서도 단독 실패, `test_duplicate_code_check::test_run_against_real_repo_smoke` 는 `.claude/worktrees/` 아래 경로에서만 실패(스캔 제외 목록에 `.claude` 포함, 변경을 치운 상태에서도 동일). 실제로 고쳐진 시험 1건.

## 이번에 하지 않은 것
메일함 패널이 사용자가 말한 계정(skyjwsin)이 아니라 화면에서 선택된 계정(skyjwshin)으로 초안을 만든 점(패널 지침 설계 확인 필요).
