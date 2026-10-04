# 메일함 새 메일 알림 — 기준서 (초안, 승인 대기)

- 날짜: 2026-10-02 / 사용자 선택: 메일 후속 작업 중 "새 메일 알림"
- 전제: 메일함 탭·AI 업무 창 구현됨(`2026-10-01_naver_mailbox_tab.md`, `2026-10-02_mailbox_ai_window.md` §8 후속 항목).
- 성격: **읽기 전용**. 메일 상태·AI 기준점·발송 경로를 바꾸지 않는다.

## 1. 문제와 제약
- 네이버 IMAP 은 `IDLE` 미지원(CAPABILITY 실측) → 푸시 불가, **주기 확인(폴링)** 만 가능.
- 기존 `GET /naver-mailbox/new`(`reader.list_new`)는 **AI 업무 창의 기준점**(`checkpoint`)을 쓴다. 화면이 이것을 폴링하면 AI 가 "새 메일"을 놓치거나 화면 때문에 기준점이 움직이므로 **쓰지 않는다.**
- 열린 연결을 오래 두면 안 된다 → 기존 연결 풀(`mailbox.session`, 45초 폐기·NOOP)을 그대로 쓴다.

## 2. 설계
| 부분 | 내용 |
|---|---|
| 서버 확인 | `STATUS INBOX (UIDNEXT UIDVALIDITY UNSEEN)` **한 줄**만 보낸다. 폴더를 선택(SELECT)하지 않아 읽음 표시·캐시에 영향 없음. 본문·헤더를 받지 않아 가볍다 |
| API | `GET /api/v1/naver-mailbox/inbox-watch?account=` → `{ok, uidnext, uidvalidity, unseen}` (L8, 읽기, 기존 `_ADMIN` 인증) |
| 판정(순수) | `new_since(prev, cur)`: `uidvalidity` 가 다르면 "기준 재설정"(알림 없음), `cur.uidnext > prev.uidnext` 면 새 메일 있음(개수 = 차이, 상한 표기 "99+"). 처음 확인은 기준만 잡고 알리지 않는다 |
| 화면 | 폴링 30초(탭이 보일 때) / 120초(숨김). 연속 실패 시 간격 2배씩 최대 10분. 새 메일이 있으면 ① 토스트("새 메일 N통 — 보낸 사람·제목", 클릭하면 받은편지함 첫 쪽) ② 목차의 안 읽음 수 갱신 ③ 받은편지함을 보고 있으면 목록 자동 새로고침 ④ 브라우저 탭 제목 `(N) 메일함` ⑤ 선택: 브라우저 알림(`Notification`, 사용자가 켠 경우만) |
| 토스트 내용 | 새로 온 UID 의 헤더는 기존 `messages` API 1쪽에서 `uid >= prev.uidnext` 만 골라 표시(헤더 캐시 재사용, 추가 IMAP 호출 최소) |
| 설정 | "새 메일 알림" 켜기/끄기 + 브라우저 알림 허용 토글(`localStorage`, 화면별 편의 설정). 기본 켬(토스트·탭 제목), 브라우저 알림은 기본 끔 |

## 3. 하지 않는 것
- 메일을 읽음 처리하지 않는다. 이동·삭제·발송 없음. 앱이 꺼져 있을 때의 알림(백그라운드 서비스)은 범위 밖.
- 받은편지함 외 폴더(스팸 등)는 감시하지 않는다.
- AI 가 쓰는 `list_new`·`checkpoint` 는 변경하지 않는다(테스트로 고정).

## 4. 구성 (레이어·파일)
| 계층 | 파일 | 변경 |
|---|---|---|
| L3 | `scripts/naver/mail_imap/mailbox.py` | **추가만** — `inbox_status(account)` (STATUS 한 줄, `session(account, None)` 재사용) |
| L2 | `ai_orchestrator/gates/mail_new_policy.py` | **신규(순수)** — `new_since`, 개수 표기 |
| L6 | `ai_orchestrator/workflows/naver_mailbox_flow.py` | **추가만** — `inbox_watch(account)` |
| L8 | `ai_orchestrator/routers/naver_mailbox_router.py` | **추가만** — `GET /inbox-watch` (라우트 +1, 기준값 350→351) |
| L9 | `admin-web/src/app/mailbox/lib/useNewMailWatch.ts` | **신규** — 폴링·백오프·가시성 처리 훅 |
| L9 | `admin-web/src/app/mailbox/components/NewMailToast.tsx` | **신규** — 토스트 |
| L9 | `MailboxApp.tsx`, `lib/api.ts` | **추가만** — 훅 연결, 탭 제목, 목록 새로고침 |
| L11 | `tests/test_mailbox_new_alert.py` | **신규** |
- `mcp_server.API_REGISTRY` 는 **건드리지 않는다**(AI 허용 목록 집합 고정 테스트 유지 — 화면 전용 경로).
- 신규 파일 위치 근거: 순수 판정은 기존 `gates/mail_draft_policy.py` 와 같은 L2, 화면 훅은 `mailbox/lib/` 기존 구조.
- 새 sqlite·스키마·산식·응답 key 변경 없음. 보안 영향: 읽기 전용, 비밀번호·메일 내용 로그 없음(토스트는 화면에만).

## 5. 드라이런(수정 없이 확인한 것)
- `mailbox.session(account, None)` 은 선택 없이 로그인된 연결을 빌려준다(STATUS 용으로 `list_folders` 가 이미 같은 방식 사용).
- `list_folders` 의 `STATUS (MESSAGES UNSEEN)` 와 같은 형식이라 `_inbox_counts` 파서를 `UIDNEXT UIDVALIDITY` 까지 확장하거나 같은 규칙의 새 파서를 추가한다(기존 함수 시그니처 불변).
- 예상 게이트: 모듈 순환 82 유지(새 import 방향은 기존과 동일), 라우트 기준값 351 재고정, 레지스트리 신규 파일 3개 등록.

## 6. 테스트 계획
1. `new_since`: 첫 확인(기준만) / uidnext 증가 / uidvalidity 변경 / 변화 없음 / 개수 상한 표기.
2. `inbox_status`: 가짜 IMAP 으로 STATUS 응답 해석, 로그인 실패·응답 이상 시 `ok:false`.
3. `list_new` 의 기준점 파일이 `inbox-watch` 호출 전후 **동일**함(AI 기준점 불변).
4. `API_REGISTRY` 허용 집합 불변(기존 테스트 통과).
5. 화면: 타입체크·ESLint, 별도 헤드리스 브라우저로 토스트·탭 제목 확인(사용자 앱 창은 허락 없이 조작하지 않음).

## 7. 결정 대기
1. 폴링 간격 30초/120초(숨김) — 권장. 더 짧게 하면 네이버 접속 제한 위험(공식 한도 미확인).
2. 브라우저 알림(`Notification`)은 선택 기능으로 포함 — 권장.
3. 앱 종료 중 알림은 제외 — 권장.
