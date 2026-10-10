# 하드코딩 경로 정리 (결함 #17) — 기준서

## 1. 측정 (2026-10-01, 테스트·archive·admin-web 제외)
- 따옴표 문자열 안의 **절대경로 하드코딩 74줄 / 45개 파일**.
- `__file__` 기준으로 경로를 계산하는 곳 475곳 / 453개 파일(대부분 모듈마다 `ROOT = Path(__file__).resolve().parents[N]`).

| 종류 | 예 | 판단 |
|---|---|---|
| OS 표준 위치 | Chrome 설치 경로(5곳 복붙), 맑은 고딕 폰트(9개 파일) | 정당한 상수지만 **목록을 여러 곳에 복붙** — 한 곳으로 모은다 |
| 사용자 컴퓨터 고유 경로 | `C:\Users\skyjw\...`, `OneDrive\...`, `C:\work\...` | 컴퓨터·계정이 바뀌면 깨진다(이식성 결함). 대부분 사이트·캠페인 코드 |
| 서버 경로 | `/home/ubuntu/...`(ops 점검 스크립트) | 서버 배치 기준이라 정당 |
| 안전 차단 목록·예시 문자열 | `C:/Windows/` 차단 목록 | 정당 |

## 2. 범위 결정
- **사이트·캠페인 코드의 이식성 문제는 이번에 건드리지 않는다**(사이트 작업 보류 방침): hanafax, mk_catalog, eum 견적 경로, 블로그 계정 이미지, instagram/video 캠페인 도구, `scripts/naver/browser_gate.py`.
- 사이트와 무관한 공통 부분만 처리한다.
  1. **Chrome/Edge/ffmpeg 위치 탐색을 한 곳으로**: `scripts/browser_paths.py` (표준 라이브러리만). `scripts/common/` 에 두면 루트 스크립트가 가져다 쓸 때 폴더 순환(`scripts ↔ scripts/common`, common 이 이미 scripts/logger.py 를 import)이 생겨 `scripts/` 최상위에 둔다.
     - 후보 목록·순서는 기존과 동일하게 유지(Program Files → Program Files (x86) → `%LOCALAPPDATA%`; Edge 는 기존 순서).
     - 사용처 3곳: `scripts/cdp_daemon.py`(`_find_browser`), `scripts/cdp_force_start.py`(`_find_chrome`), `scripts/browser/cdp/start_chrome_with_cdp.py`(`_find_chrome_exe`).
     - `start_chrome_with_cdp.py` 는 `C:\Users\skyjw\AppData\...` 를 하드코딩해 다른 계정에서 Chrome 을 못 찾는 결함이 있다 → `%LOCALAPPDATA%` 로 바뀐다(현재 컴퓨터에서는 같은 경로).
     - `scripts/ops/record_promo_video.py/record_promo_video.py` 의 ffmpeg 경로(WinGet 패키지 폴더에 계정명·버전 하드코딩) → 환경변수 `FFMPEG_PATH` → PATH 의 `ffmpeg` → WinGet 패키지 폴더 탐색 순.
  2. **새 하드코딩 방지 게이트**: `codebase_layer_audit.py` 에 `HARDCODED_USER_PATH` 검사 추가 — `C:\Users\<이름>` 또는 `C:\work` 리터럴이 **알려진 부채 목록 밖의 파일**에 새로 생기면 경고. 기존 파일은 known debt 로 등재(STORAGE_BOUNDARY 와 같은 방식).
- `__file__` 기준 ROOT 계산 453개 파일은 일괄 치환하지 않는다: 많은 스크립트가 `sys.path` 를 설정하기 **전에** ROOT 가 필요해서 공용 모듈 import 로 바꿀 수 없고, 변경량 대비 이득이 작다. 신규 코드는 `scripts/common/data_paths.py` / `ai_orchestrator/config.py` 를 쓰도록 규칙으로 남긴다.

## 3. 영향·위험
- 탐색 후보 순서와 목록은 그대로라 같은 컴퓨터에서 같은 브라우저가 선택된다. 브라우저 **실행**(`assert_browser_launch_allowed` 등 게이트)은 호출부에 그대로 둔다 — 탐색만 옮긴다.
- 새 파일 1개 + 테스트 1개 → module_registry 등록 필요. 외부 API·DB·보안 영향 없음.
- 롤백: 호출부 3곳을 되돌리면 된다.
