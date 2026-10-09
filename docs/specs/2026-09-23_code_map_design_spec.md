# 코드맵 설계서 — haehan-ai-orchestrator (2026-09-23, 승인 대기)

선행: 골격 점검 1단계(A~G 7축 실측, 2026-09-23). 1차 목적 = **죽은 코드 삭제 근거 확보**.
2차 목적 = 골격 결함(경로·스키마·조용한 실패·계약) 을 숫자로 재측정하고 커밋 게이트로 막기.

## 0. 원칙

1. **커버리지를 먼저 보고한다** — "미도달 N개"보다 "해석 못 한 import/호출 M%(사각지대)"가 먼저.
2. **"도달함"은 약한 근거, "미도달"만 강한 근거** — 단, 진입점 목록이 완전할 때만. 진입점 누락이 곧 오삭제.
3. **자사 코드 전 디렉터리를 스캔 루트에 넣는다** — 루트 파일 39개, `apps/`·`backend/`(패키지 아님) 포함.
4. **추출기 오탐률은 표본 검수로 측정** 후 채택. 삭제 후보는 표본 20건 수작업 확인 전 공개하지 않는다.
5. **노드 ID 에 줄번호 금지** — `경로::함수` / `경로::클래스.메서드`.
6. **삭제는 자동 판정하지 않는다** — 코드맵은 후보·근거를 낸다, 삭제는 사람 승인(단계별 커밋).
7. 서브에이전트 부정 결론은 메인이 원문 재확인 후 채택.

## 1. 코드맵이 답할 질문

| # | 질문 | 사용처 |
|---|---|---|
| Q1 | 이 파일/함수를 지우면 무엇이 깨지나 (역참조 전체) | 삭제 판단 |
| Q2 | 어떤 진입점에서도 닿지 않는 파일/함수는 무엇인가 | 죽은 코드 목록 |
| Q3 | 테스트에서만 닿는 코드는 무엇인가 | 테스트 전용 분류(삭제 시 테스트도 같이) |
| Q4 | 프론트가 부르는데 백엔드에 없는 경로 / 백엔드에만 있는 경로 | 404·죽은 라우트 |
| Q5 | 이 테이블·JSON 파일을 누가 쓰고 누가 읽나 | 스키마 정본화, 0행 테이블 |
| Q6 | 같은 역할 함수가 몇 벌이고 구현이 어떻게 갈렸나 | 중복 정리 |
| Q7 | 금지 방향 import(하위→상위, 도메인 간)는 어디인가 | 계층 게이트 |
| Q8 | 예외 삼킴이 데이터 로딩·발송 경로에 있는 곳은 | 조용한 실패 우선순위 |

## 2. 실측 전제 (2026-09-23 조사)

| 항목 | 값 | 설계 반영 |
|---|---|---|
| 추적 .py | 2,651 (파싱 실패 1: BOM) | `ast` 표준 라이브러리만 사용, 외부 의존성 추가 없음 |
| 추적 ts/tsx/js | 413 (admin-web 395) | 3단계에서 정규식 추출(L6 한정), TS 파서 도입 안 함 |
| `sys.path` 조작 | 436곳 / 407파일 | 파일별 추가 검색 루트를 정적 평가(`Path(__file__).parents[N]` 패턴) |
| 동적 import (`importlib`/`__import__`) | 271곳 | 문자열 리터럴이면 해석, 아니면 **사각지대**로 집계 |
| 라우트 데코레이터 | 361 (ai_orchestrator 합성 루트 `router.py` prefix `/api/v1` 1개) | 정적 prefix 합성으로 전체 경로 해석(추정 95%+) |
| `__main__` 파일 | 594 | 전부 진입점 시드(=CLI 로 살아 있을 수 있음) → 별도 "CLI 전용" 분류 |
| subprocess 호출 | 349 | `-m 모듈` / `*.py` 리터럴 추출해 시드 |
| 외부 진입(훅 13·MCP 2·스킬 9·스케줄러 3·시작프로그램·Electron spawn) | — | `configs/code_map/entrypoints_manual.json` 에 수기 목록(추적) |
| 다른 저장소의 호출 | 사실상 0 (06: 보고서 JSON 1, 32: 1) | 스캔 범위 = 이 저장소 |
| 런타임 증거 | 서버 접근로그 거의 없음(7월 1세션), `ops_log` 6,327행(오늘까지), 로그 3종 활성 | 라우트 "사용 중" 증명 불가 → §6 선택안 |
| 정적분석 도구 | ruff 만 설치 | 신규 구현(재사용: `codebase_layer_audit` 파일 순회·레이어 분류, `duplicate_code_check` 해시) |

## 3. 계층

| 층 | 내용 | 산출 | 측정 |
|---|---|---|---|
| L1 목록 | 파일·클래스·함수·시그니처·`__main__` 여부·데코레이터 | nodes | 파싱 실패 수 |
| L2 import | 절대·상대·`__init__` 재수출·별칭·`sys.path` 추가 루트·문자열 importlib | import 엣지 | **해석 실패율**(외부 라이브러리와 구분) |
| L3 호출 | 함수→함수(이름 해석: 로컬·import 심볼·`self.` 메서드), 신뢰도 고/저 | call 엣지 | 미해석 호출 비율 |
| L4 데이터 | sqlite 테이블 CREATE/INSERT/SELECT 문자열, `data/*.json` 경로 리터럴 읽기/쓰기 | 데이터 엣지 | 테이블명 추출 오탐률(표본) |
| L5 진입점·도달성 | 시드 7종(라우트·CLI·subprocess 대상·훅/MCP/스킬·스케줄러·Electron·테스트) → BFS | 파일/함수 분류 | 분류별 개수 |
| L6 프로세스 경계 | 프론트 호출 3종(`apiFetch`, `/api/proxy` 통과, 개별 BFF route.ts 32개) + Electron 직접 fetch ↔ 백엔드 라우트 | 계약 표 | 한쪽에만 있는 경로 수, 사각지대 추정 15~25% |
| L7 의미 | 인자 의미 레지스트리(`blog_id`/`account`, `product_no`/`originProductNo`, `bidNtceNo`/`bid_ntce_no` …) | `configs/code_map/param_semantics.json` | 의미 불일치 호출 수 |
| L8 선언 대조 | CLAUDE.md L1~L12 레이어 선언(`codebase_layer_audit` 분류 재사용) vs 실제 import | 층×층 행렬 | 역전 수 |

### L5 분류 (삭제 판단의 핵심)

| 분류 | 정의 | 처리 |
|---|---|---|
| LIVE | 비테스트 진입점에서 도달 | 유지 |
| CLI_ONLY | 자기 `__main__` 외에는 도달 없음 | 사용자에게 "아직 쓰는 스크립트인가" 목록 확인 |
| TEST_ONLY | 테스트에서만 도달 | 테스트와 함께 삭제 후보 |
| UNREACHED | 어디서도 도달 없음 | **삭제 후보(강한 근거)** |
| UNRESOLVED | 해석 못 한 동적 import·문자열 참조가 가리킬 수 있음 | 수동 확인 전 삭제 금지 |

삭제 후보 확정 조건(모두 충족): UNREACHED 또는 사용자가 확인한 CLI_ONLY + 저장소 전체 문자열 참조 0(`git grep` 모듈명·파일명) + 런타임 증거(ops_log·로그) 0 + 사람 승인.

## 4. 감사 목록

| 감사 | 질문 | 판정 | 기준선 |
|---|---|---|---|
| dead_code | Q2 | 신규 UNREACHED 파일 추가 = FAIL | `configs/code_map/baseline_dead.json` |
| import_resolution | 사각지대 증가 | 해석 실패율 기준선 초과 = WARN | 기준선 수치 |
| layer_inversion | Q7 | 신규 역전 = FAIL | 기존 역전 목록 |
| duplicate_impl | Q6 | 신규 동명·동역할 함수 = WARN | 기존 목록 |
| silent_failure | Q8 | 라우터·수집기·발송기 신규 `except: pass/return 기본값` = FAIL | 기존 1,341건 격리 |
| api_contract | Q4 | 프론트 신규 호출이 백엔드에 없음 = FAIL | 기존 불일치 목록 |
| freshness | 지도가 코드보다 낡음 | 파일 해시 불일치 = 재생성 강제 | — |

## 5. 저장 형식·위치

| 경로 | 내용 | git |
|---|---|---|
| `scripts/ops/code_map/` | 구축기(패키지: `build.py`, `imports.py`, `calls.py`, `entrypoints.py`, `reach.py`, `contract.py`, `audit.py`) | 추적 |
| `configs/code_map/` | `entrypoints_manual.json`, `param_semantics.json`, `baseline_*.json` | 추적 |
| `data/code_map/map.json` | 노드·엣지·메타(생성 시각·커밋 해시·스캔 루트·커버리지) | 미추적(재생성) |
| `data/code_map/summary.md` | 사람용 요약(커버리지 → 분류 개수 → 상위 후보) | 미추적 |
| `docs/defect_index.json` | 결함 목차(번호 고정, 코드맵 노드 id 링크) | 추적 |

위치 사유: 읽기 전용 운영 감사 도구 = 기존 `tools/repo_gates/codebase_layer_audit.py` 와 같은 자리. 원본 코드·DB 에 쓰지 않는다.

## 6. 단계 계획과 합격 기준

| 단계 | 범위 | 합격 기준 |
|---|---|---|
| **S1** | L1 + L2 + L5(파일 단위) → 파일 분류표 | 파싱 2,650/2,651 · import 해석 실패율 보고 · UNREACHED 표본 20건 수작업 검수 오탐 ≤10% · 2회 실행 결과 동일 |
| S2 | L3 호출 + 함수 단위 도달성 + 중복 | 미해석 호출 비율 보고 · 함수 UNREACHED 표본 20건 검수 |
| S3 | L4 데이터 + L6 계약 + 런타임 증거 결합(`ops_log`·로그) | 테이블명 오탐률 · 계약 표본 15건 검수 |
| S4 | L7 + L8 + 감사 게이트(pre-commit 의 `quality_gate` 에 편입) | 깨뜨리기 테스트: 위반 1줄 → FAIL, 제거 → PASS, 2회 동일 |

- **S1 끝나면 1차 삭제 가능**: 루트 39파일·`storage/`·`media/`·`backend/`·`services/`·`scripts/smartstore/`(작업트리 삭제 미커밋 3파일) 판정.
- 선택안 R(별도 승인): FastAPI 에 라우트 호출 카운터 미들웨어(경로·횟수만 `data/` 기록) — 라우트 "사용 중" 증명용. 코드 변경이라 S3 에서 기준서 별도.
- 선택안 C(별도 승인): `coverage` 설치 후 테스트 1회 실행으로 함수 단위 런타임 도달 보강.

## 6-1. S1 기준서 (2026-09-23 승인: "S1 진행해")

- **목적**: 파일 단위 분류표(LIVE / CLI / TEST_ONLY / MENTIONED / UNREACHED) → 1차 삭제 근거.
- **기존 코드 점검**: 호출 그래프 도구 없음(재확인 완료). `codebase_layer_audit` 는 레이어 분류용 → S4 에서 결합, S1 은 독립.
- **범위(신규만)**: `scripts/ops/code_map/{__init__,scan,reach,build}.py`, `configs/code_map/entrypoints_manual.json`. 기존 파일 수정 없음.
- **해석 규칙**
  - import 검색 루트 = 파일 폴더 → 상위 폴더 … → 저장소 루트(대부분의 `sys.path` 조작이 루트 추가 263건). 과잉 해석 쪽으로 치우침 = 삭제 판단엔 안전.
  - 모듈 import 는 상위 패키지 `__init__.py` 실행도 엣지로 추가.
  - 문자열 참조(파이썬 문자열 상수·`/` 경로 조합, 비파이썬 런처 파일의 경로·점표기 모듈명)는 **참조한 파일 → 대상** 엣지. 죽은 파일의 문자열이 대상을 살리지 않도록.
  - 루트(LIVE 시드) = 비파이썬 런처(json/js/ts/ps1/vbs/bat/yml/Dockerfile/spec/훅/.mcp.json/CLAUDE.md/.claude) 에서 참조된 파일 + `entrypoints_manual.json`(작업 스케줄러·시작프로그램) + 사용자 스킬(~/.claude/skills) 참조.
  - CLI = `__main__` 파일에서만 도달. TEST_ONLY = 테스트에서만 도달.
  - 미도달 중 파일명(stem)이 코드·설정(docs/·data/ 제외, 자기 자신 제외)에 단어로 등장 = MENTIONED(수동 확인), 아니면 UNREACHED.
- **드라이런 판단 기준**: 파싱 실패 ≤1 · import 해석 실패율 보고 · UNREACHED 표본 20건 수작업 검수 오탐 ≤10% · 2회 실행 결과(메타 제외) 동일.
- **검증 명령**: `python tools/code_map/build.py` → `data/code_map/map.json`, `summary.md`; `--determinism` 2회 비교.
- **롤백**: 신규 파일 삭제만으로 원복(원본·DB 쓰기 없음).

## 7. 한계(정적 분석이 못 보는 것)

- 비리터럴 `importlib`·`getattr` 디스패치(271곳 중 일부), `scripts/naver/services_catalog.py` 같은 문자열 레지스트리 → UNRESOLVED 로 격리.
- `sys.path` 조작이 실행 시점 값에 의존하는 경우.
- 문자열로 조립한 SQL, 런타임에만 정해지는 파일 경로.
- 저장소 밖 호출자: 서버 컨테이너 cron, 사용자 수동 실행 습관 → CLI_ONLY 는 반드시 사용자 확인.
- 개별 BFF route.ts 32개·Electron 직접 fetch 는 파일별 정규식 → 계약 사각지대 15~25%.

## 8. 영향

- 신규 파일만 추가(`scripts/ops/code_map/`, `configs/code_map/`). 기존 코드·API·DB·스키마 변경 없음.
- 보안: 비밀값 읽지 않음(`.env` 스캔 제외). 외부 호출·AI API 호출 없음.
- S4 게이트 편입 시에만 `.githooks`/`quality_gate` 수정 → 그 단계 기준서에서 별도 승인.
