# Local File Search (LOCAL-FS-1)

Claude Code가 프로젝트 루트 기준으로 로컬 파일을 직접 조회·검색·요약한다.
대표님에게 파일을 직접 찾아 붙여넣거나 경로를 알려달라고 요구하지 않는다.

## 사용법

```bash
# 키워드 검색
python scripts/search_local_files.py --query "kakao" --preview --json

# 파일 타입 필터
python scripts/search_local_files.py --query "storage_state" --file-type py,md --json

# glob 패턴
python scripts/search_local_files.py --glob "*.md" --query "자동화" --preview --json

# runs/ 포함
python scripts/search_local_files.py --include-runs --query "render_worker" --json

# 전체 index 요약 (query 없음)
python scripts/search_local_files.py --json
```

## 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--root` | `.` | 검색 루트 디렉터리 |
| `--query` | 없음 | 검색어 (없으면 index 요약) |
| `--glob` | 없음 | 파일 glob 패턴 |
| `--file-type` | 없음 | 파일 확장자 필터 (py,md,json) |
| `--max-results` | 50 | 최대 결과 수 |
| `--preview` | false | 매칭 파일 내용 preview 포함 |
| `--max-preview-chars` | 8000 | preview 최대 글자수 |
| `--json` | false | JSON 요약 출력 |
| `--out-dir` | runs/local_files | 결과 저장 디렉터리 |
| `--include-runs` | false | runs/ 디렉터리 포함 |
| `--allow-sensitive-paths` | false | 민감 경로 스캔 허용 (redaction은 항상 적용) |

## 결과 파일

- `runs/local_files/local_file_search_YYYYMMDD_HHMMSS.json`
- `runs/local_files/local_file_search_YYYYMMDD_HHMMSS.md`

## 검색 대상 경로

```
docs/
scripts/
ai_orchestrator/
local_agent/
agent/
samples/
runs/          ← --include-runs 사용 시만
data/
config/
mcp_server/
```

## 기본 제외

| 제외 항목 | 이유 |
|-----------|------|
| `secrets/` | 세션·자격증명 민감정보 |
| `.env` / `.env.*` | 환경변수 |
| `*.pem` / `*.key` / `*.p12` / `*.pfx` | 개인키·인증서 |
| `*.sqlite` / `*.db` | 데이터베이스 |
| `__pycache__/` / `.git/` / `node_modules/` | 빌드·시스템 |
| 바이너리 파일 | null byte 감지 |
| 2 MB 초과 파일 | 대용량 |

## 민감정보 Redaction

preview 및 matched_lines에서 다음 패턴을 자동 마스킹한다:

- `password=xxx` → `password=***`
- `Authorization: Bearer xxx` → `Authorization: Bearer ***`
- `api_key=xxx` → `api_key=***`
- `client_secret=xxx` → `client_secret=***`
- 32자 이상 hex 문자열 → `abcdef...7890`
- 40자 이상 base64류 → `abcdef...7890`
- `-----BEGIN ... KEY-----` 블록 → `[PRIVATE KEY REDACTED]`

`--allow-sensitive-paths` 사용 시에도 redaction은 항상 적용된다.

## 작업 전 사용 루틴 (LOCAL-FS-2)

**새 작업 시작 전 관련 파일을 자동 검색한다.**
대표님에게 파일 경로/내용을 요청하지 않는다.

### 공통 지시 문구

모든 작업 시작 전:
```
작업 시작 전 scripts/search_local_files.py로 관련 파일과 최신 runs 결과를 먼저 검색한다.
대표님에게 파일 경로/내용을 요청하지 않는다.
```

### 주요 키워드별 검색 패턴

#### 개발자 콘솔 작업 (Kakao/Naver/Google)
```bash
python scripts/search_local_files.py --query "kakao" --preview --include-runs --json

python scripts/search_local_files.py --query "naver" --preview --include-runs --json

python scripts/search_local_files.py --query "console" --preview --include-runs --json

python scripts/search_local_files.py --query "storage_state" --file-type py,md --json
```

#### 영상 작업 (ffmpeg, 렌더링, 녹화)
```bash
python scripts/search_local_files.py --query "ffmpeg" --preview --include-runs --json

python scripts/search_local_files.py --query "render" --preview --include-runs --json

python scripts/search_local_files.py --query "recording" --preview --include-runs --json

python scripts/search_local_files.py --query "subtitle" --preview --include-runs --json
```

#### 세션·로그인 작업
```bash
python scripts/search_local_files.py --query "session" --file-type py,md --json

python scripts/search_local_files.py --query "login" --file-type py,md --json

python scripts/search_local_files.py --query "browser_state" --preview --json
```

#### 자동화·스케줄링 작업
```bash
python scripts/search_local_files.py --query "automation" --preview --include-runs --json

python scripts/search_local_files.py --query "cron" --preview --json

python scripts/search_local_files.py --query "schedule" --preview --json
```

#### 파일 타입별 검색
```bash
# Python 코드만 검색
python scripts/search_local_files.py --query "kakao" --file-type py --preview --json

# 문서만 검색
python scripts/search_local_files.py --query "kakao" --file-type md --preview --json

# 설정/데이터 파일만
python scripts/search_local_files.py --query "kakao" --file-type json,yaml,yml --json
```

#### 최신 실행 결과 조회
```bash
# 최근 실행 결과 검색 (runs/ 포함)
python scripts/search_local_files.py --include-runs --query "kakao_app_details" --json

python scripts/search_local_files.py --include-runs --query "session_health" --json

python scripts/search_local_files.py --include-runs --query "error\|failed\|warn" --json
```

#### 파일 인덱스만 조회 (전체 구조 파악)
```bash
# query 없음 = 파일 인덱스 요약
python scripts/search_local_files.py --json

python scripts/search_local_files.py --include-runs --json
```

### 검색 결과 해석

| 결과 | 의미 |
|------|------|
| `total_matches: 0` | 관련 파일 없음 — 신규 작업 또는 이전 결과 없음 |
| `total_matches: 1-10` | 매우 구체적 — 직접 관련 파일 소수 |
| `total_matches: 11-50` | 적당함 — 관련 도메인 파일 중간 규모 |
| `total_matches: 50+` | 포괄적 — 광범위한 관련성 |

### 주의사항

- `--preview` 없으면 파일명/경로만 반환 (빠름)
- `--preview` 사용하면 내용까지 포함 (느림, 인사이트 높음)
- `--include-runs` 사용하면 이전 실행 결과 JSON/MD도 검색 가능
- 민감정보(password/key/token)는 자동 마스킹됨 — 안전하게 공유 가능

---

## LOCAL-FS-3 — 최근 runs 결과 자동 요약

Claude Code가 작업 시작 전 runs/ 하위 최신 결과를 작업군별로 자동 요약한다.
PASS/WARN/FAIL 상태 및 next_actions를 한눈에 파악할 수 있다.

### 사용법

```bash
# 전체 작업군 요약
python scripts/summarize_recent_runs.py --json

# 특정 그룹만
python scripts/summarize_recent_runs.py --group developer_console --json

# 여러 그룹
python scripts/summarize_recent_runs.py --group render,video --json
```

### 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--root` | `.` | 프로젝트 루트 |
| `--group` | 전체 | 요약할 작업군 (쉼표 구분) |
| `--json` | false | JSON 요약 stdout 출력 |
| `--out-dir` | `runs/local_files` | 결과 저장 디렉터리 |
| `--max-files` | 3 | 그룹당 최대 파일 수 |

### 작업군 목록

| 작업군 | runs/ 경로 |
|--------|------------|
| `developer_console` | `runs/developer_console/**` |
| `video` | `runs/video/*.json`, `runs/video/**` |
| `render` | `runs/video/render/**` |
| `local_files` | `runs/local_files/*.json` |
| `local_agent` | `runs/local_agent/**` |
| `naver` | `runs/naver/**` |
| `youtube` | `runs/youtube/**` |
| `content` | `runs/content/**` |

### 상태 분류 규칙

| 상태 | 조건 |
|------|------|
| `FAIL` | status=BLOCKED/failed, security.* 위반 |
| `WARN` | status=NEEDS_REAUTH/UNKNOWN, warnings[] 있음, ffmpeg_available=false, mode=dry_run |
| `PASS` | 위 조건 없음 |

- `NEEDS_REAUTH`는 FAIL이 아니라 WARN — 장애가 아닌 다음 조치 필요 상태
- `action_required=true`이면 next_actions 목록 확인 필요

### 결과 파일

- `runs/local_files/recent_runs_summary_YYYYMMDD_HHMMSS.json`
- `runs/local_files/recent_runs_summary_YYYYMMDD_HHMMSS.md`

### 보안

- `.env`, `secrets/`, `browser_state` 경로는 절대 읽지 않음
- `next_actions` 등 모든 문자열에 `redact_sensitive_text()` 적용
- API key / token / password 원문 출력 없음

### 작업 전 사용 루틴 (LOCAL-FS-3)

```bash
# 작업 시작 전 전체 상태 파악
python scripts/summarize_recent_runs.py --json

# 개발자 콘솔 관련 작업 전
python scripts/summarize_recent_runs.py --group developer_console --json

# 영상/렌더링 관련 작업 전
python scripts/summarize_recent_runs.py --group render,video --json
```
