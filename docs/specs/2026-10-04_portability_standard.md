# 이식성·재현성 표준 — 다른 PC에 설치해도 같은 방식으로 항상 동작하게 (조사 결과 + 처리 기준서)

- 날짜: 2026-10-04 / 사용자 요청: "IT 표준으로 해서 오류 없게, 다른 컴퓨터에 설치해도 상시 문제없게 조사해서 처리".
- 계기: 사이트 업무 지도 M4 화면 확인 중 (1) 새 탭 `goto` 가 멈추고 (2) CDP 포트(9222)가 죽어 있었으며 (3) 같은 시험이 폴더 위치에 따라 통과/실패(.env 덮어쓰기)하는 등, **이 PC 의 상태에 기대는 부분**이 반복해서 드러남.

## 1. 조사 결과 (외부 표준 · 공식 문서)
| 주제 | 근거 | 이 프로젝트에 주는 의미 |
|---|---|---|
| Chrome 136+ 원격 디버깅 | Chrome 개발자 블로그 *Changes to remote debugging switches to improve security* (developer.chrome.com/blog/remote-debugging-port): 기본 사용자 데이터 폴더에서는 `--remote-debugging-port` 가 **오류 없이 무시**되고, 반드시 `--user-data-dir` 로 **비표준 폴더**를 줘야 함 | 이 프로젝트는 `data/cdp_profile/ai_chrome` 별도 프로필이라 **해당 없음(올바름)**. 단 누군가 `HAEHAN_CDP_PROFILE` 을 기본 Chrome 폴더로 바꾸면 포트가 조용히 안 열림 → 점검 필요 |
| Playwright 연결 방식 | Playwright 문서 *BrowserType*: `connect_over_cdp` 는 "Playwright 프로토콜 연결보다 **충실도가 크게 낮다**", 기본 타임아웃 30초. 로그인 유지가 목적이면 `launch_persistent_context(userDataDir)` 가 설계 목적에 맞음 | 이 앱은 한 브라우저를 FastAPI·로컬 에이전트·스크립트가 **공유**해야 해서 `connect_over_cdp` 를 유지한다(영속 컨텍스트는 한 프로세스가 프로필을 잠금). 대신 **연결·탭 열기는 검증된 단일 경로만** 쓰고 상태를 점검한다 |
| 실행 환경 재현성 | pip 공식 *Constraints files*: 직접 의존성은 범위(`>=`)로 두더라도 **검증된 전체 버전 집합은 제약 파일로 고정**해 같은 환경을 재현 | 현재 `requirements.txt` 는 `>=` 만 있어 **PC·시점마다 다른 버전**이 깔림 |
| 훅·스크립트의 인터프리터 | Python Launcher for Windows(`py -3`)는 설치된 최신 3.x 를 고름. `py -3.14` 처럼 **마이너 버전을 박으면** 3.14 가 없는 PC 에서 전부 실패 | `.claude/settings.json` 훅 15곳이 `py -3.14` 고정. 안전 훅(OpenAI 호출 차단·세션 보호)이 **다른 PC 에서 조용히 안 돌 수 있음** |

## 2. 저장소 점검 결과 (2026-10-04 실측)
| 항목 | 상태 | 판정 |
|---|---|---|
| Chrome 경로 탐색 | `scripts/browser_paths.find_chrome()` 단일 모듈(Program Files·LOCALAPPDATA 순). 일부는 아직 직접 하드코딩(`scripts/naver/browser_gate.py`) | 대체로 양호, 중복 1곳 |
| CDP 프로필 | `HAEHAN_CDP_PROFILE` 환경변수 우선, 기본 `data/cdp_profile/ai_chrome`(비표준 폴더) | 양호 |
| CDP 포트 | 9222 상수 | 이 PC 에서 다른 프로그램과 충돌하면 실패 → 점검에서 충돌을 구분해 알린다 |
| 새 탭 열기 | `cdp_tabs.open_tab`(HTTP, 도착 확인)이 검증된 경로. 내 탐색 실행기만 `ctx.new_page()+goto` 사용 | **결함(내가 만든 것)** — 교정 |
| 훅 인터프리터 | `py -3.14` 15곳 | **결함** — `py -3` 로 교정 + 최소 버전은 점검에서 확인 |
| 의존성 | `requirements.txt` 범위만(`playwright>=1.40.0`, `fastapi>=0.137.0` …), 잠금 없음 | **결함** — 제약 파일 추가 |
| PC 전용 경로 | 추적 코드 148곳 중 대부분 시험·문서·예시. 실행 경로에 영향을 주는 것은 소수(주석·기본 계정명) | 신규 유입을 막는 시험 추가 |
| 설치 점검 도구 | 없음(`install_git_hooks`, `selector_health` 만) | **부재** — `preflight` 신설 |
| CI | ubuntu(secrets·frontend) + windows-latest(verify, Python 3.14) | 제약 파일은 CI 에 아직 연결하지 않음(다음 단계 제안) |

## 3. 처리 (이번 범위, 모두 추가·교정이며 동작을 넓히지 않는다)
1. **`scripts/ops/preflight.py`** — 설치·실행 환경 점검(비밀 값은 읽지도 출력하지도 않음). 파이썬 버전·필수 패키지 버전·Chrome 존재와 버전·CDP 프로필이 비표준 폴더인지(136 규칙)·포트 상태(내 브라우저/다른 프로그램 구분)·쓰기 가능한 데이터 폴더·훅이 쓰는 인터프리터 존재·Node/admin-web 의존성·git 훅 설치·선택 도구(audit-kit, mypy)를 PASS/WARN/FAIL 로 보고. 종료코드 0/1. 시험은 가짜 환경으로.
2. **훅 인터프리터** — `.claude/settings.json` 의 `py -3.14` → `py -3`(최소 버전은 preflight 가 검사). 이 PC 는 3.14 가 최신이라 동작 동일.
3. **`constraints.txt`** — 검증된(시험이 도는) 환경의 전체 버전 집합을 `scripts/ops/make_constraints.py` 로 **재생성 가능하게** 만든다(손으로 쓰지 않음). 설치: `pip install -r requirements.txt -c constraints.txt`.
4. **탐색 실행기 탭 열기** — `ctx.new_page()+goto` → `cdp_tabs.open_tab`(HTTP 생성 + 도착 확인) 기반으로 교체, 만든 탭만 닫는다.
5. **이식성 시험** — 훅 명령에 마이너 버전 고정·사용자 홈 절대경로가 다시 들어오면 실패.
6. (제안, 이번에 하지 않음) CI 에서 `-c constraints.txt` 사용, 중복 Chrome 경로(`naver/browser_gate.py`)를 `browser_paths` 로 통합, 포트 9222 를 설정값으로.

## 4. 하지 않는 것
- Playwright 연결 방식 전면 교체(`launch_persistent_context`/`connect`)는 공유 브라우저 구조를 바꾸는 큰 설계 변경이라 별도 승인 사안.
- 브라우저·로그인 세션을 지우거나 프로필을 옮기는 일.
- 다른 PC 에 실제 설치/배포(서버 배포는 `server_deploy.py` 영역).
