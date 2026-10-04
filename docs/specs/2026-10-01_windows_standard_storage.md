# 윈도우 표준 저장소로 이전 + 하드코딩 경로 전면 제거 — 기준서

사용자 지시(2026-10-01): "프로그램 저장소 및 설치 프로그램을 윈도우 표준 저장소를 생성하게 하고 기존 하드코딩은 모두 삭제하자."
선행: `2026-10-01_hardcoded_paths_consolidation.md`(결함 #17 1단계: 브라우저·ffmpeg 위치 탐색 통합, 신규 하드코딩 방지 게이트).

## 1. 사용자 결정 (2026-10-01 확인)
| 항목 | 결정 |
|---|---|
| 데이터 위치 | **사용자별 `%LOCALAPPDATA%\HaehanAI\Orchestrator\`** — `HaehanAI` 는 이미 해한 제품군 공용 상위 폴더(아래 `CADQuantity\`·`runtime\`·`inventory\`)이므로 제품 하위 폴더 규칙을 따른다. 설정 파일만 로밍 `%APPDATA%\HaehanAI\Orchestrator\` |
| 프로그램 설치 위치 | **사용자별 설치** `%LOCALAPPDATA%\Programs\HaehanAI Orchestrator\` (관리자 권한 불필요, Electron/electron-builder 기본) |
| 기존 데이터 | **첫 실행 때 자동 이전**: 새 위치가 비어 있으면 기존 폴더에서 **복사**(원본 보존) + 이전 기록. 로그인 세션·브라우저 프로필 포함(재로그인 방지) |
| 개발 모드 | **항상 윈도우 표준 위치**. 저장소 상대 경로(`data/`, `ai_orchestrator/storage/`) 가정 제거. 다른 위치는 환경변수 `HAEHAN_DATA_ROOT` 로만(테스트·격리용) |

## 2. 현재 상태 (측정 2026-10-01)
- **데이터 규모(이 PC)**: 저장소 `data/` **8.2GB·23,639개 파일**(브라우저 프로필 `cdp_profile` 5.5GB, `kpi_elib` 0.9GB, `mk_catalog` 0.4GB, `cmpi` 0.4GB, `browser_sessions` 0.1GB 등), `ai_orchestrator/storage/` 3.4MB(19개), `C:\AI 에이전트` 9개 파일. → 이전의 시간·디스크 비용이 크고, 대부분 재생성 가능한 캐시·임시 프로필이다. 이전 대상을 **필수 / 선택(재생성 가능) / 제외(임시)** 로 나눈다(§5).
- `%LOCALAPPDATA%\HaehanAI\` 는 이미 존재하며 `CADQuantity\`(CAD 프로그램 자격증명·저장소, 현재 사용 중)·`runtime\`(테스트 임시, 85MB)가 있고 `inventory\` 를 쓰는 코드도 있다 → 이 폴더 바로 아래에는 쓰지 않는다.
- 데이터가 저장소 폴더 안에 있다: `data/`(DB·캐시·로그·세션·브라우저 프로필·보고서), `ai_orchestrator/storage/`(sqlite DB 3개, 비밀 파일 `secrets/`).
- 경로 해석기가 갈라져 있다: `ai_orchestrator/config.py`(`LOCAL_DATA_DIR`, 기본 저장소 `data/`), `scripts/common/data_paths.py`(`AI_DATA_ROOT`, `C:\AI 에이전트\{앱폴더}` 하드코딩 매핑), 모듈마다 `Path(__file__).resolve().parents[N] / "data"`(453개 파일).
- Electron 앱은 이미 `%APPDATA%\Haehan AI`(Roaming, `userData`)에 `config.json`·`.env`·`logs/` 를 둔다 — 파이썬 쪽과 위치가 다르다.
- 절대경로 하드코딩 74줄/45개 파일(사용자 폴더 `Downloads`·`OneDrive`, `C:\work`, 서버 경로 등).
- `HARDCODED_USER_PATH` 게이트의 알려진 부채 16개 파일.

## 3. 목표 구조
```
%LOCALAPPDATA%\Programs\HaehanAI Orchestrator\   ← 설치(실행 파일, 읽기 전용). 업데이트 때 통째로 교체
%LOCALAPPDATA%\HaehanAI\                           ← 제품군 공용 상위(이미 존재: CADQuantity, runtime, inventory) — 건드리지 않는다
%LOCALAPPDATA%\HaehanAI\Orchestrator\              ← 이 앱의 데이터 루트(HAEHAN_DATA_ROOT 로 대체 가능)
    data\            DB·캐시·수집 결과·보고서 (앱별 하위: cafe, blog, smartstore, ...)
    db\              sqlite DB 파일(스키마 버전 관리 대상: sqlite_schema)
    sessions\        로그인 세션
    browser_profile\ CDP 브라우저 프로필(ai_chrome)
    logs\            로그
    cache\           재생성 가능한 캐시
    secrets\         비밀(자격증명·토큰) — 사용자 전용 ACL
    migration\       이전 기록(migration.json: 무엇을 언제 어디서 복사했는지)
%APPDATA%\HaehanAI\Orchestrator\                 ← 로밍 설정(config.json 등 작은 설정만)
```
- 사용자 폴더(다운로드·문서·바탕화면)는 하드코딩하지 않고 **Known Folder API**(`SHGetKnownFolderPath`)로 얻는다.
- 서버(Linux) 배포 코드는 윈도우 경로를 쓰지 않는다: 같은 해석기가 비윈도우에서는 `HAEHAN_DATA_ROOT` 필수 → 없으면 `~/.local/share/haehanai/orchestrator` 로 폴백.

## 4. 설계: 단일 해석기 `app_paths`
- 위치: `scripts/app_paths.py` — **표준 라이브러리만**, 다른 프로젝트 모듈을 import 하지 않는다. (코드맵 폴더 순환 방지: `scripts/browser_paths.py` 와 같은 이유로 `scripts/` 최상위. `ai_orchestrator/` 에서는 `scripts` 를 import 하지 않는 경계를 지키기 위해 **얇은 어댑터** `ai_orchestrator/paths.py` 가 같은 규칙을 호출한다 — 구현 단계에서 레이어 규칙과 대조해 확정.)
- 공개 함수(전부 `Path` 반환, 호출 시 디렉터리 자동 생성 옵션):
  - `data_root()` → `HAEHAN_DATA_ROOT` 환경변수 → `%LOCALAPPDATA%\HaehanAI\Orchestrator`
  - `config_root()`, `install_root()`, `data_dir(*parts)`, `db_path(name)`, `logs_dir()`, `cache_dir()`, `sessions_dir()`, `browser_profile_dir()`, `secrets_dir()`
  - `known_folder(name)` — Downloads·Documents·Desktop 등(Windows 는 `SHGetKnownFolderPath`, 그 외 `~` 기준)
  - `app_dir(app, sub="")` — 기존 `get_app_dir` 대체(앱 키 → 폴더)
- 우선순위: ① `HAEHAN_DATA_ROOT` ② 윈도우 표준(`LOCALAPPDATA`) ③ 비윈도우 폴백. **저장소 상대 경로 폴백은 두지 않는다.**
- `%LOCALAPPDATA%` 가 없으면(비정상 환경) 명확한 오류를 낸다(조용히 다른 곳에 쓰지 않는다).

## 5. 이전(마이그레이션) 설계
- 엔진: `scripts/app_paths_migrate.py`(표준 라이브러리만). **복사만 하고 원본은 지우지 않는다**(검증 후 사용자가 정리).
- 대상 매핑(기존 → 신규):
  | 기존 | 신규 |
  |---|---|
  | `<repo>/data/*.db`, `<repo>/data/**` | `data\`, `db\` |
  | `<repo>/data/cdp_profile/ai_chrome` | `browser_profile\ai_chrome` |
  | `<repo>/data/sessions` | `sessions\` |
  | `<repo>/ai_orchestrator/storage/*.db` | `db\` |
  | `<repo>/ai_orchestrator/storage/secrets` | `secrets\` |
  | `C:\AI 에이전트\{앱폴더}` | `data\{앱키}` |
  | `%APPDATA%\Haehan AI\{config.json,.env,logs}` | 그대로 두되 경로를 신규 `config_root()` 와 정렬(구현 단계에서 확정) |
- 동작: 새 위치의 이전 기록(`migration\migration.json`)이 없으면 실행. 파일 단위로 **크기·수정시각·SHA-256** 검증 후 완료 표시, 중간에 끊겨도 이어서(멱등). sqlite 는 실행 중 복사하지 않고 `sqlite3.Connection.backup()` 으로 일관된 스냅샷을 만든다.
- **드라이런 필수**: `--dry-run` 이 무엇을 얼마나 복사할지(파일 수·용량·충돌)만 보고하고 아무것도 쓰지 않는다. 사용자 승인 전에는 실제 복사를 하지 않는다.
- 로그인 세션·브라우저 프로필은 실행 중인 브라우저가 파일을 잡고 있을 수 있어 **CDP 브라우저가 꺼져 있을 때만** 이전한다(켜져 있으면 안내 후 중단).

## 6. 설치 프로그램
- electron-builder 설정에 사용자별 설치(`nsis.perMachine=false`, `oneClick`/`allowToChangeInstallationDirectory` 정책 확정)와 `%LOCALAPPDATA%\Programs\HaehanAI` 기본 경로를 명시한다. 설치 중 **데이터 루트 폴더와 하위 구조를 생성**하고 사용자 전용 ACL 을 적용한다(`secrets\`).
- 첫 실행 때 이전 엔진을 호출한다(설치 후 기존 PC 의 데이터가 있으면 복사 제안).
- 제거(uninstall) 시 **데이터 폴더는 기본 보존**, "데이터도 삭제" 체크 시에만 삭제.
- 설치 프로그램 정의가 저장소에 없다(`admin-web/package.json` 에 electron-builder 설정 없음): **현재 빌드 방식을 먼저 확인**하고(별도 빌드 스크립트·CI 여부) 설정을 신설한다.

## 7. 하드코딩 제거 범위 (사용자 지시: "모두")
- 저장소 상대 경로: `ROOT / "data"`·`Path(__file__).parents[N] / "data"|"storage"` → `app_paths` 호출.
- 절대경로 74줄/45개 파일: OS 표준 위치(Chrome·폰트)는 탐색 함수로, 사용자 폴더는 Known Folder, 계정·`C:\work` 는 설정/환경변수/`app_paths` 로. 서버 경로(`/home/ubuntu/...`)는 서버 배포 설정으로 분리.
- 사이트·캠페인 코드(hanafax, mk_catalog, eum, 블로그, instagram/video)도 **경로 하드코딩에 한해** 포함한다(사이트 동작 보강이 아니라 경로 치환만. 사이트 연결·보강 보류 방침과 충돌하지 않게 로직은 건드리지 않는다).
- 완료 후 `HARDCODED_USER_PATH` 알려진 부채를 0 으로 만들고, 저장소 상대 `data/`·`storage/` 조립 금지 게이트(`REPO_RELATIVE_DATA_PATH`)를 추가한다.

## 8. 단계 (각 단계는 독립 검증 후 반영, 이전·전환은 사용자 승인 후)
| 단계 | 내용 | 위험 |
|---|---|---|
| P1 | `app_paths` 해석기 + 테스트 + 이전 엔진(드라이런만) + 현재 데이터 드라이런 보고 | 낮음(호출부 변경 없음) |
| P2 | **사용자 승인** 후 실제 이전 실행(복사) + 검증 | 중간(데이터 복사, 원본 보존) |
| P3 | 호출부 전환 — 영역별(서버 ai_orchestrator → scripts 공통 → local_agent → apps → 사이트·캠페인) 서브에이전트 + 독립 리뷰 | 높음(데이터 위치 변경) — 영역마다 서버 재시작 필요 여부 확인 |
| P4 | 설치 프로그램(electron-builder) 사용자별 설치·폴더 생성·제거 정책 | 중간 |
| P5 | 하드코딩 부채 0, 게이트 추가, 옛 해석기(`LOCAL_DATA_DIR`·`AI_DATA_ROOT`·`C:\AI 에이전트` 매핑) 삭제 | 낮음 |

## 9. 위험·대응
- **실행 중인 서버·브라우저가 옛 위치를 계속 쓴다**: 전환 시점에 FastAPI(8401)·CDP 브라우저를 재시작해야 한다. 전환(P3)은 영역별로 하고, 전환 직후 옛 위치에 새 파일이 생기는지 감시한다.
- **로그인 세션 유실**: 세션·프로필 복사는 브라우저 종료 상태에서만, 복사 후 재로그인 없이 세션 유지 확인(session_probe 읽기 전용).
- **비밀 파일 노출**: `secrets\` 는 사용자 전용 ACL, 이전 기록(`migration.json`)에 비밀 값·경로의 사용자명을 남기지 않는다.
- **롤백**: 원본을 보존하므로 해석기 전환을 되돌리면 옛 위치로 돌아간다. 이전 후 일정 기간(예: 2주) 원본 삭제 금지.
- **다른 세션과의 충돌**: 호출부 453개 파일을 건드리므로 영역별 착수 전에 동시 세션과 파일 겹침을 확인한다.
