# CDP 데몬 브라우저 정책 (단일 출처: `scripts/common/config.py` 의 `CDP_BROWSER_POLICY`)

L12 문서 · 2026-10-05 · 근거 실험과 상세: `docs/specs/2026-10-05_cdp_clean_start_login_retention.md`

9222 데몬 Chrome(프로필 `data/cdp_profile/ai_chrome`)을 **깨끗하게 시작하고 로그인(세션 쿠키)은 유지**하기 위한 정책이다.
`cdp_daemon.py`·`cdp_force_start.py` 는 이 값만 읽는다(값이 코드에 흩어지지 않는다). 구현은 `scripts/browser/session/browser_lifecycle.py`(L4).

| 키 | 값 | 뜻·근거 |
|---|---|---|
| `start_url` | `https://www.google.com/` | 시작 페이지(홈). 옛 탭을 정리한 뒤 이 주소 탭 하나만 남긴다. 로그인·동작 없음. Chrome 의 홈페이지·시작 설정은 변조 방지로 파일 수정이 무시돼 이 방식을 쓴다 |
| `restore_last_session` | `True` | `--restore-last-session` 스위치(**값 없이**). 세션 쿠키(로그인)가 재시작 뒤에도 남는 조건. `=false` 를 붙여도 켜진다 |
| `clean_start` | `True` | 스위치 때문에 복원된 옛 탭을 시작 직후 닫는다(복원이 끝날 때까지 탭 목록이 안정되기를 기다림) |
| `graceful_stop_first` | `True` | 종료는 CDP `Browser.close` 가 먼저. 종료 신호·강제 종료는 로그인 쿠키를 잃는다 |
| `restore_settle_s` | `10.0` | 세션 복원이 끝나기를 기다리는 최대 시간(1~60초) |

## 지켜야 할 것 (시험이 강제)
- 세 불리언(`restore_last_session`·`clean_start`·`graceful_stop_first`)은 끄지 않는다 — `browser_lifecycle.validate_policy` 와 `tests/test_browser_lifecycle.py::test_central_policy_is_valid_and_guardrails_are_on` 이 막는다.
- 실행 인자에 `--restore-last-session=값` 형태를 쓰지 않는다 — `tests/test_chrome_launch_flags.py`.
- 원격 디버깅 포트는 반드시 별도 `--user-data-dir` 과 함께(Chrome 136+ 는 기본 프로필에서 포트를 무시한다, developer.chrome.com/blog/remote-debugging-port).
- 데몬 재시작은 `python scripts/browser/cdp/cdp_daemon.py restart`(정상 종료 경로)로만 한다. 프로세스 강제 종료·`taskkill /F`·전원 차단은 로그인을 잃는다.
- 로그인 여부는 쿠키 **이름 존재 여부(참/거짓)** 로만 확인한다(NID_AUT/NID_SES, SID/SAPISID). 값은 읽지 않는다.

## 데몬 브라우저를 건드리는 시험 금지
9222 는 사용자의 로그인된 브라우저다. 시험·검증 도구(`verify_change` 등)가 이 브라우저에 접속하면 탭이 이동·소멸하고 로그인이 풀린다(2026-10-05 실측).
- 시험은 가짜 객체만 쓴다. 패치는 **실제 호출이 일어나는 모듈**에 건다(`search_analyze` 처럼 `import` 한 이름은 껍데기 모듈에 걸어도 닿지 않는다).
- `tests/integration/manual/` 은 파일 이름을 직접 지정해도 `HAEHAN_RUN_MANUAL=1` 일 때만 실행된다.
- 탭 이동 주체 추적: `data/logs/browser_watch.jsonl` 의 `cdp_clients`(연결 프로세스 이름·스크립트명)·`browser_process`(출현·소멸+직전 프로세스).
