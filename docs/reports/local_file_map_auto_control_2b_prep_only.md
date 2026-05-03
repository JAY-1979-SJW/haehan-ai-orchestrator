# LOCAL-FILE-MAP-AUTO-CONTROL-2B-PREP_ONLY 준비 완료 보고서

**생성 일시**: 2026-05-03 16:25:00
**판정**: PREP PASS (스크립트 준비 완료, API 호출 검증 미수행)

---

## 작업 내용

### 목표
실제 배포된 admin-web API를 통해 cleanup-execute dry_run=true 실행을 검증하기 위한 스크립트 및 도구를 준비한다.

다만, 현재 세션에서 실제 배포 서버(haehan-app) 접근이 불가능하므로 **스크립트 준비만 완료**하고, 실제 API 호출 검증은 미수행한다.

### 핵심 제약
- ✗ 실제 배포 admin-web URL 미확정
- ✗ 운영 서버(haehan-app) SSH 접속 불가
- ✗ 따라서 실제 API 호출 및 검증 불가

### 완료 항목
- ✅ smoke_cleanup_execute_api_dry_run.py 작성
- ✅ verify_audit_rollback.py 옵션 보강
- ✅ generate_file_map_ops_report.py PREP 모드 지원
- ✅ TypeScript 타입 체크 (PASS)
- ✅ 빌드 진행 중

---

## 기준선 확인

**기준선**: d290326 (master)
- Branch: master
- HEAD == origin/master: ✓
- Git status: clean (자동 생성 파일 제외)

---

## 기존 자동 감사 재확인 (AUTO-CONTROL-2A 기준)

| 항목 | 상태 |
|------|------|
| 모듈화 | PASS (0 exceeds) |
| 보안 | PASS (0 issues) |
| Component | PASS (0 exceeds) |

---

## 스크립트 준비 상태

### 1. smoke_cleanup_execute_api_dry_run.py

**목적**: 실제 admin-web API를 통해 cleanup-execute dry_run=true 실행 검증

**주요 기능**:
- FILE_MAP_BASE_URL 환경변수 필수 (미설정 시 FAIL)
- base_target_dir가 /tmp로 시작하는지 검증
- dry_run=true 고정 (false 차단)
- /tmp 임시 경로에 fixture 생성
- API 호출 및 run_id 추출
- 파일 무결성 확인 (source 유지, target 미생성)

**실행 방식**:
```bash
export FILE_MAP_BASE_URL="https://haehan-ai.kr"  # 또는 실제 URL
python3 scripts/file-map/smoke_cleanup_execute_api_dry_run.py
```

**현재 상태**: FILE_MAP_BASE_URL 미설정이므로 FAIL 반환 (정상 동작)

### 2. verify_audit_rollback.py (보강)

**추가 옵션**:
- `--run-id <run_id>`: 특정 run_id 기반 audit 검증
- `--latest`: 최신 audit 기록 검증
- `--audit-dir <path>`: audit 디렉터리 경로
- `--mode {PREP,RUN}`: 준비 모드 / 실행 모드

**dry_run 정책 명확화**:
- dry_run=true에서 rollback manifest 미생성은 정상 (WARN이 아닌 설계 의도)
- PREP 모드에서 명시적으로 기록

**실행 예**:
```bash
python3 scripts/file-map/verify_audit_rollback.py --mode PREP --latest
```

### 3. generate_file_map_ops_report.py (보강)

**추가 옵션**:
- `--mode {PREP,RUN}`: 준비 모드 / 실행 모드
- `--report-name <name>`: 리포트 파일명

**PREP 모드**:
- fixture 기반 smoke test만 실행
- 실제 API 호출 없음
- 리포트 상태: PREP_PASS (PASS 대신)
- 생성 파일: local_file_map_auto_control_2b_prep.json/md

**RUN 모드**:
- 실제 API dry_run smoke test 실행
- API 호출 및 검증
- 생성 파일: local_file_map_auto_control_2b.json/md

**실행 예**:
```bash
# PREP 모드 (현재 환경)
python3 scripts/file-map/generate_file_map_ops_report.py --mode PREP

# RUN 모드 (서버 세션, 실제 URL 설정 필수)
export FILE_MAP_BASE_URL="https://haehan-ai.kr"
python3 scripts/file-map/generate_file_map_ops_report.py --mode RUN
```

---

## 검증 결과

### 스크립트 검증

| 항목 | 결과 |
|------|------|
| smoke_cleanup_execute_api_dry_run.py 문법 | ✅ OK (FILE_MAP_BASE_URL 미설정 시 정상 FAIL) |
| verify_audit_rollback.py --help | ✅ OK |
| generate_file_map_ops_report.py --help | ✅ OK |
| TypeScript tsc --noEmit | ✅ PASS (0 errors) |
| npm run build | ⏳ 진행 중 |

### 코드 안전성

| 항목 | 확인 |
|------|------|
| dry_run=false 차단 | ✅ 하드코딩 (smoke_cleanup_execute_api_dry_run.py L72) |
| /tmp 경로 강제 | ✅ 검증 (validate_target_path 함수) |
| tests/fixtures 사용 금지 | ✅ fixture는 /tmp만 사용 |
| token/path/payload 로그 | ✅ 완전 마스킹 (환경변수만 출력) |
| 실제 파일 삭제 | ✅ dry_run=true만 호출 |
| local_file_map.json 수정 | ✅ 읽기만, 쓰기 금지 |

---

## 실제 API 호출 검증 미수행 사유

### 제약 조건
1. **실제 배포 admin-web URL 미확정**
   - SSH haehan-app 접속 불가 (현재 환경)
   - docker-compose.yml에서 admin-web은 container 내부 3000 포트만 노출
   - 외부 접근 경로: https://haehan-ai.kr/file-map (추측, 확정 안함)

2. **운영 서버 /tmp fixture 생성 불가**
   - /tmp는 서버 내부 경로이므로 로컬에서 생성 불가
   - SSH 접속 필요 (불가능)

3. **따라서**
   - 로컬 /tmp에 fixture 생성 가능 (로컬 API 대상)
   - 실제 서버 /tmp는 접근 불가

### 해결 방법
실제 운영 서버가 있는 세션에서 다음을 실행:

```bash
# 1. 서버 /tmp fixture 생성
mkdir -p /tmp/local-file-map-api-smoke/{source,target}
echo "content A" > /tmp/local-file-map-api-smoke/source/document-a.txt
echo "content B" > /tmp/local-file-map-api-smoke/source/document-b.txt
echo "sensitive" > /tmp/local-file-map-api-smoke/source/신분증.pdf
echo "existing" > /tmp/local-file-map-api-smoke/target/existing.txt

# 2. API 호출
export FILE_MAP_BASE_URL="https://haehan-ai.kr"  # 실제 URL로 변경
python3 scripts/file-map/smoke_cleanup_execute_api_dry_run.py

# 3. 리포트 생성 (RUN 모드)
python3 scripts/file-map/generate_file_map_ops_report.py --mode RUN
```

---

## 다음 단계 (AUTO-CONTROL-2B-RUN)

### 필수 조건
1. 실제 배포 admin-web URL 확정
   - 예: https://haehan-ai.kr
   - 또는: haehan-app 서버 내부 docker network

2. 운영 서버 접속 가능한 세션
   - SSH haehan-app 또는 컨테이너 내부 실행

3. 서버 /tmp fixture 생성 권한

### 실행 순서

**Step 1**: 서버 /tmp에 fixture 생성
```bash
ssh haehan-app
mkdir -p /tmp/local-file-map-api-smoke/{source,target}
# 파일 생성...
```

**Step 2**: API dry_run smoke 실행
```bash
export FILE_MAP_BASE_URL="<실제-admin-web-url>"
python3 scripts/file-map/smoke_cleanup_execute_api_dry_run.py
```

**Step 3**: audit JSONL 확인
```bash
python3 scripts/file-map/verify_audit_rollback.py --mode RUN --latest
```

**Step 4**: ops 리포트 생성 (RUN 모드)
```bash
python3 scripts/file-map/generate_file_map_ops_report.py --mode RUN
```

**Step 5**: 커밋 및 푸시
```bash
git add docs/reports/local_file_map_auto_control_2b.json
git add docs/reports/local_file_map_auto_control_2b.md
git commit -m "chore(file-map): verify deployed api dry-run audit flow"
git push origin master
```

---

## 생성 파일

### 스크립트 (신규/보강)
- ✅ `scripts/file-map/smoke_cleanup_execute_api_dry_run.py` (신규)
- ✅ `scripts/file-map/verify_audit_rollback.py` (옵션 추가)
- ✅ `scripts/file-map/generate_file_map_ops_report.py` (PREP 모드 추가)

### 보고서
- ✅ `docs/reports/local_file_map_auto_control_2b_prep_only.md` (현재)
- ⏳ `docs/reports/local_file_map_auto_control_2b_prep.json` (생성 예정, --mode PREP 실행 시)
- ⏳ `docs/reports/local_file_map_auto_control_2b.json/md` (실행 예정, --mode RUN 실행 시)

---

## 판정

### 현재 단계 (PREP)

| 항목 | 상태 |
|------|------|
| 스크립트 작성 | ✅ PASS |
| 문법 검증 | ✅ PASS |
| 옵션 지원 | ✅ PASS |
| dry_run=true 강제 | ✅ PASS |
| /tmp 경로 강제 | ✅ PASS |
| TypeScript | ✅ PASS |
| Build | ⏳ 진행 중 |

**현재 판정**: **PREP PASS**

### 최종 판정 (RUN 필요)

실제 API 호출 검증은 미수행 → 최종 판정은 불가

**다음 판정**: RUN 모드에서 실제 API 호출 후 결정
- PASS: API dry_run 정상, audit JSONL 기록, rollback 정책 준수
- WARN: API 호출은 되었으나 일부 검증 미충족
- FAIL: API 호출 실패 또는 dry_run=false 감지

---

**보고 완료**: 2026-05-03T16:25:00
**담당**: Claude Haiku 4.5
**상태**: 준비 완료, 실제 검증 대기

다음 단계: **AUTO-CONTROL-2B-RUN** (실제 배포 서버 세션에서 실행)
