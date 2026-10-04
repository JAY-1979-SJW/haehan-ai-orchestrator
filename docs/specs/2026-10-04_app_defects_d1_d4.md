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

## 영향 검증 (D1~D4 합산)
영향 테스트 197개 파일: 수정 전 164건 실패 → 수정 후 165건. 새로 실패한 2건은 변경과 무관한 기존 문제다 — `test_approval_read_api::test_history_limit_capped_at_500` 는 수정 없는 HEAD 에서도 단독 실패, `test_duplicate_code_check::test_run_against_real_repo_smoke` 는 `.claude/worktrees/` 아래 경로에서만 실패(스캔 제외 목록에 `.claude` 포함, 변경을 치운 상태에서도 동일). 실제로 고쳐진 시험 1건.

## 이번에 하지 않은 것
D5(AI 허용 API 와 화면 기능 불일치: 하나팩스 kill-switch·구글 캘린더 등)~D8, 승인 카드 컴포넌트의 공용 위치 이동(역방향 import 정리), 메일함 패널이 사용자가 말한 계정(skyjwsin)이 아니라 화면에서 선택된 계정(skyjwshin)으로 초안을 만든 점(패널 지침 설계 확인 필요).
