# LOCAL-FILE-MAP-SERVER-BASELINE-DIAG-1 — 서버 기준선 불일치 진단

**진단 일시**: 2026-05-03  
**진단자**: Claude Code  
**진단 환경**: read-only (git pull/push 금지)

## 작업 내용

3B 서버 read-only 조사 중 감지된 서버 repo dirty 상태 및 HEAD 불일치를 진단.
로컬과 서버의 커밋 관계, modified 파일 내용을 분석하여 원인 분류.

## 로컬 기준선

```
branch: master
HEAD: 3d95cc1
origin/master: 3d95cc1
status: clean ✓

마지막 commit:
  3d95cc1 docs(file-map): refresh auto-generated reports before server discovery
```

**평가**: 로컬 정상, origin/master와 동기화

## 서버 기준선

```
branch: master
HEAD: e44b3b6
origin/master: e44b3b6
status: DIRTY

마지막 commit:
  e44b3b6 (HEAD -> master, origin/master, origin/HEAD)
           fix(smoke): add preflight_id and correct approval_token format for API validation
```

**평가**: 서버 HEAD는 origin과 동기화, 그러나 working directory dirty

## 서버 Modified 파일 분석

### 파일 목록
- `docs/reports/local_file_map_auto_control_1.json`
- `docs/reports/local_file_map_auto_control_1.md`

### Diff 요약

#### JSON (local_file_map_auto_control_1.json)
- **변경 범위**: 71줄 중 2줄 (timestamp)
- **변경 내용**:
  - timestamp 필드: `2026-05-03T15:27:03.098670` → `2026-05-03T16:42:09.364196`
  - 파일 경로 포맷: `\` (backslash) → `/` (forward slash)
  - 예: `admin-web\src\app\api\...` → `admin-web/src/app/api/...`
- **구조 변화**: 없음
- **판정 변화**: PASS → PASS (동일)

#### Markdown (local_file_map_auto_control_1.md)
- **변경 범위**: 96줄 중 3줄 (timestamp + 경로 포맷)
- **변경 내용**:
  - "생성 일시": `2026-05-03 15:27:03` → `2026-05-03 16:42:09`
  - 파일 경로 포맷: `\` → `/`
  - 예: `admin-web\src\components\...` → `admin-web/src/components/...`
- **구조 변화**: 없음
- **판정 변화**: PASS → PASS (동일)

### 민감정보 검증
- token / password / secret: **없음** ✓
- 절대 경로 / hostname: **없음** ✓
- API key / credential: **없음** ✓

## 커밋 관계 분석

### 로컬

```
merge-base analysis:
  3d95cc1 (local HEAD) is ancestor of origin/master: YES
  → local가 origin에 포함됨 (동기화 뒤처짐)
```

**해석**: 로컬 HEAD (3d95cc1)은 현재 origin의 ancestor 상태. origin이 더 최신.

### 서버

```
merge-base analysis:
  e44b3b6 (server HEAD) is ancestor of origin/master: YES
  e44b3b6 (server HEAD) == origin/master: YES
  → server HEAD == origin/master (동기화)
```

**해석**: 서버 HEAD (e44b3b6)은 origin/master와 정확히 일치.

### origin/master 버전 차이

```
로컬이 본 origin/master: 3d95cc1
서버가 본 origin/master: e44b3b6

차이: 3개 commits
  e44b3b6 fix(smoke): add preflight_id and correct approval_token format for API validation
  b58c459 chore(file-map): prepare api dry-run audit verification scripts (PREP mode)
  d290326 docs(local-file-map): AUTO-CONTROL-2A 최종 기준선 잠금 보고서
  ...
  3d95cc1 docs(file-map): refresh auto-generated reports before server discovery
```

## 원인 분류

**Case A: 서버 modified 파일이 단순 자동 보고서 timestamp 갱신**

### 판단 근거
1. Modified 파일이 `docs/reports/` 자동 생성물뿐
2. PASS/WARN/FAIL 판정 변화 없음 (PASS → PASS)
3. 파일 구조 변화 없음 (timestamp와 경로 포맷만 변경)
4. 민감정보 없음
5. 자동 생성 도구가 재실행되어 timestamp 갱신된 것으로 판단

### 평가
- **위험도**: 낮음 (자동 생성 보고서)
- **기능 영향**: 없음 (판정 동일)
- **보안**: 안전함 (민감정보 없음)

### 원인 추정
서버에서 자동 제어 audit 스크립트가 재실행되어 보고서가 재생성됨.
경로 포맷 변경은 리눅스 환경에서 실행되어 나타난 결과 (Windows 경로 제거).

## 추가 발견: 로컬 Sync 필요

### 문제 상황
- 로컬 `origin/master`: 3d95cc1 (캐시)
- 실제 GitHub `origin/master`: e44b3b6 (최신)
- 로컬이 3 commits 뒤처짐

### 원인
- 로컬에서 `git fetch` 미실행
- 로컬 `origin/*` 레퍼런스가 old cache 상태

## 권장 다음 단계

### 우선순위 1: 로컬 Sync (필수)
```bash
git fetch origin
git log --oneline --decorate -12
```
이후 로컬 `origin/master`가 e44b3b6으로 갱신되는지 확인.

### 우선순위 2: 서버 Modified 처리 (별도 승인)
서버의 2개 modified 파일에 대해:
- **Option A**: 커밋 후 푸시 (새 commit 추가)
- **Option B**: 변경 폐기 (git restore)
- **Option C**: 그대로 유지 (향후 처리)

현재 단계에서는 실행하지 않음. 별도 승인 필요.

## 최종 판정

| 항목 | 상태 |
|------|------|
| 로컬 기준선 | PASS (clean) |
| 서버 기준선 | WARN (dirty, 자동 보고서) |
| Dirty 원인 | 안전 (자동 생성물, 판정 변화 없음) |
| 커밋 관계 | WARN (로컬 3 commits 뒤처짐) |
| 전체 판정 | **WARN** |

### 판정 근거
- 서버 repo는 dirty하지만 원인이 명백함 (자동 보고서 timestamp)
- 기능/보안 영향 없음
- 로컬이 최신 커밋을 동기화하지 않은 상태 (git fetch 필요)
- 복구 가능한 상태 (임의 복구 금지 규칙 적용 안 함)

## 생성 보고서

- `docs/reports/local_file_map_server_baseline_diag_1.md` (본 파일)

## 최종 권장사항

1. **즉시**: `git fetch origin` 실행 (로컬 origin/master 동기화)
2. **확인**: 로컬 `git log --decorate` 확인 (origin/master가 e44b3b6으로 변경되는지)
3. **별도**: 서버 modified 파일 처리 결정 (승인 필요)
4. **재개**: 위 단계 완료 후 3B Docker smoke 조사 재시작

