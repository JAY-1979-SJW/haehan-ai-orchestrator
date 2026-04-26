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
