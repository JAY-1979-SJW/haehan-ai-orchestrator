# 기준서 — 로그인 세션 모니터 수정 (frozen-safe 능동 점검)

작성일: 2026-06-05 / 사용자 승인: (A) 세션 모니터 버그 수정

## 1. 문제

1. **frozen exe 서브프로세스 실패**: `/sessions/refresh` 가
   `subprocess.run([sys.executable, login_session_monitor.py, --once])` 실행.
   frozen exe 에서 `sys.executable` = `haehan-server.exe`(파이썬 아님) → 모니터가
   실행되지 않아 결과 파일이 갱신 안 됨 → 앱 `로그인 세션` 페이지가 항상 "아직 확인 안 됨".
2. **수동 점검의 한계**: 기존 `check_site` 는 CDP에 **이미 열린 탭**만 검사
   (`_find_tab_for_site`). 해당 사이트 탭이 없으면 `NO_TAB` → 실제 로그인 여부를 못 봄.

## 2. 수정

| 파일 | 변경 |
|------|------|
| `tools/runtime/session_probe.py` **(신규)** | Playwright `connect_over_cdp(9222)` → 9개 사이트 게이트 URL을 **임시 탭으로 접속** → 최종 URL의 로그인 리다이렉트/비밀번호 폼으로 판정 → `data/login_session_monitor_latest.json`(기존 포맷) 기록 |
| `ai_orchestrator/connectors/session_status_router.py` | `/refresh`: subprocess 대신 `session_probe.probe_all()` **in-process** 호출(frozen-safe). 파일 못 읽으면 기존 동작 폴백 |

- **보존**: `login_session_monitor.py`(실시간 감시 루프)는 그대로 둠. 새 프로버는 on-demand 점검용 별도 모듈.
- 결과 포맷: `{checked_at, cdp_available, sites:[{key,status,detail,href,has_session_cookie,checked_at}]}` — `_build_response` 가 그대로 소비.
- status: `LOGGED_IN | LOGIN_REQUIRED | ERROR`.

## 3. 점검 대상 (key → 게이트 URL → 로그인 판정 키워드)

| key | 게이트 URL | 로그아웃 판정(최종 URL/폼) |
|-----|-----------|--------------------------|
| naver | nid.naver.com/user2/help/myInfoV2 | nidlogin |
| smartstore | sell.smartstore.naver.com | nidlogin |
| google | myaccount.google.com | accounts.google.com/signin, ServiceLogin |
| youtube_studio | studio.youtube.com | accounts.google.com, ServiceLogin |
| gabia | my.gabia.com | accounts.gabia.com, /login |
| eum | eum.cw.or.kr/web/man/WEBMAN390M00 | /login, nidlogin |
| hiworks | office.hiworks.com | login.office.hiworks, /login |
| kakao | accounts.kakao.com/weblogin/account/info | /login |
| dataportal | data.go.kr/mypage/mylogin/index.do | /login, auth.data.go.kr |

- naver/smartstore 는 NID_AUT+NID_SES 쿠키도 `has_session_cookie` 신호로 사용.

## 4. 안전/영향

- 임시 탭 1개만 열고 닫음 → 사용자의 다른 탭/세션 영향 없음.
- 로그인 자체는 사용자(최초 로그인/OTP) — 변경 없음.
- DB·secret·외부발행 없음. 정방향 import(L8→ops). 게이트: layer/security/quality 재실행.
