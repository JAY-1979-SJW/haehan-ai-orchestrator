# FILE-MAP-CLEANUP-PREFLIGHT-ENDPOINT-INTEGRATION-1

**작업 완료 일시**: 2026-05-04  
**작업 단계**: Preflight Endpoint 추가 & 통합  
**최종 기준선**: e742caa (feat: add cleanup preflight executor endpoint)

---

## 작업 개요

### 작업명
FILE-MAP-CLEANUP-PREFLIGHT-ENDPOINT-INTEGRATION-1

### 목표
- file-map-executor에 /cleanup/preflight endpoint 최소 추가
- admin-web cleanup-preflight API를 executor 호출 방식으로 통합
- cleanup-execute와 동일한 패턴 재사용
- read-only preflight 검증 구현

### 최종 판정
**✅ PASS**

---

## 기준선

**기준 HEAD**:
```
29c959f: Revert "docs(phase3y): preflight audit 1..."
origin/master: 29c959f (동기화)
working tree: clean
```

**최종 HEAD**:
```
e742caa: feat(file-map): add cleanup preflight executor endpoint
origin/master: e742caa (push 완료)
working tree: clean
```

---

## 수정 파일 (6개)

### 1. services/file_map_executor/schemas.py
**변경 사항**: PreflightRequest, PreflightResponse, PreflightItem 스키마 추가
```
- PreflightItem: source, target, status, reason
- PreflightRequest: base_target_dir, plans, include_sensitive
- PreflightResponse: ok, preflight_id, dry_run, total, ok_count, conflict_count, skipped_count, items, error
```

### 2. services/file_map_executor/service.py
**변경 사항**: FileMapExecutorService.preflight() 메서드 추가
```
- read-only preflight 검증
- plans 검증 (파일 존재 확인)
- preflight_id 생성
- 실제 파일 삭제/생성/이동 없음
```

### 3. services/file_map_executor/app.py
**변경 사항**: /cleanup/preflight endpoint 추가
```
- @app.post("/cleanup/preflight") 핸들러 추가
- PreflightRequest/Response import 추가
- validate_target_path() 재사용
- request.dict() → request.model_dump() 변경 (Pydantic v2)
```

### 4. tests/test_file_map_executor_service.py
**변경 사항**: TestCleanupPreflightEndpoint 테스트 클래스 추가
```
- test_preflight_valid_path_empty_plans: empty plans 검증
- test_preflight_valid_path_with_plans: plans 검증
- test_preflight_non_tmp_path_rejected: /tmp 경로 강제
- test_preflight_missing_base_target_dir: 필수 필드 검증
- test_preflight_is_read_only_no_file_ops: read-only 보장
```

### 5. admin-web/src/lib/file-map/pythonExecutor.ts
**변경 사항**: callPythonExecutorPreflight() 함수 추가
```
- FILE_MAP_EXECUTOR_URL 사용
- POST /cleanup/preflight 호출
- 30초 timeout
- error handling cleanup-execute와 동일
- adaptPreflightResponse() 응답 변환 함수 추가
```

### 6. admin-web/src/app/api/file-map/cleanup-preflight/route.ts
**변경 사항**: TODO 제거, executor 호출로 교체
```
- TODO: Python cleanup_preflight 모듈 호출 제거
- callPythonExecutorPreflight() 호출 추가
- fs.access() 로컬 검증 제거 (executor가 처리)
- executor 응답 변환 추가
- 기존 response shape 보존
```

---

## 구현 내용

### /cleanup/preflight endpoint 설계

**Request**:
```typescript
{
  base_target_dir: "/tmp/...",
  plans: [
    { source: string, target: string, confirmed: boolean }
  ],
  include_sensitive?: boolean
}
```

**Response**:
```typescript
{
  ok: boolean,
  preflight_id: string,
  dry_run: true,  // 항상 true
  total: number,
  ok_count: number,
  conflict_count: number,
  skipped_count: number,
  items: [
    {
      source: string,
      target: string,
      status: "ok" | "source_missing" | "invalid_path",
      reason: string
    }
  ],
  error?: string
}
```

### read-only 보장 방식

1. **preflight() 메서드**:
   - Path.exists() 호출만 (stat 정보 확인)
   - 파일 생성, 삭제, 이동 함수 호출 안 함
   - 실제 cleanup 실행 함수 호출 안 함

2. **보안 정책**:
   - /tmp 경로 강제 (validate_target_path 재사용)
   - read-only 문자 정의 (dry_run=true)
   - executor 레벨에서 실제 변경 방지

3. **테스트 검증**:
   - test_preflight_is_read_only_no_file_ops 테스트로 확인
   - 파일 시스템 변경 없음 보장

### cleanup-execute와의 패턴 동일성

| 항목 | execute | preflight | 비고 |
|------|---------|-----------|------|
| HTTP 메서드 | POST | POST | 동일 |
| 경로 | /cleanup/execute | /cleanup/preflight | 분리됨 |
| URL 기반 | FILE_MAP_EXECUTOR_URL | FILE_MAP_EXECUTOR_URL | 동일 |
| timeout | 30s | 30s | 동일 |
| /tmp 강제 | ✓ | ✓ | 동일 |
| error handling | cleanup-execute 패턴 | cleanup-execute 패턴 | 동일 |
| response adapt | adaptExecutorResponse() | adaptPreflightResponse() | 분리됨 |

---

## 테스트 결과

### file-map-executor 테스트

**신규 테스트 (preflight)**:
```
✓ test_preflight_valid_path_empty_plans (empty plans)
✓ test_preflight_valid_path_with_plans (plans validation)
✓ test_preflight_non_tmp_path_rejected (path validation)
✓ test_preflight_missing_base_target_dir (required field)
✓ test_preflight_is_read_only_no_file_ops (read-only check)
= 5개 모두 PASS
```

**기존 테스트 (회귀 검증)**:
```
✓ TestHealthEndpoint: 1개 PASS
✓ TestCleanupExecuteEndpoint: 4개 PASS
✓ TestCleanupAuditEndpoint: 2개 PASS
✓ TestCleanupRollbackEndpoint: 2개 PASS
✓ TestSecurityPolicies: 2개 PASS
= 11개 모두 PASS (회귀 없음)
```

**총계**: 16개 테스트 모두 PASS ✓

### 코드 품질 검증

- 파일 삭제/생성/이동 함수: 없음 ✓
- docker-compose.yml 변경: 없음 ✓
- DB/schema 변경: 없음 ✓
- PHASE3Y 파일: 없음 ✓

---

## smoke 실행 기준

### 로컬 Docker 환경

**실행 위치** (필수):
- Docker network 내부 (api 컨테이너 또는 동일 network 컨테이너)

**금지**:
- ❌ host OS에서 admin-web:3000 직접 호출
- ❌ localhost:3000 호출

**권장 실행 방식**:
```bash
# api 컨테이너 내부에서 실행
docker exec haehan-ai-orchestrator-api python3 -c "
import requests
response = requests.post(
  'http://admin-web:3000/api/file-map/cleanup-preflight',
  json={
    'base_target_dir': '/tmp/test',
    'plans': []
  }
)
print(response.json())
"
```

**예상 응답**:
```json
{
  "ok": true,
  "preflight_id": "...",
  "total": 0,
  "ok_count": 0,
  "conflict_count": 0,
  "skipped_count": 0,
  "blocked_count": 0,
  "items": []
}
```

### 서버 반영 상태

**현재**: 로컬 구현만 완료
**서버**: 반영 금지 (이번 단계)
**다음**: 승인 후 서버 배포 가능

---

## 금지 준수 확인

```
[✓] PHASE3Y 미작업: 관련 파일 없음
[✓] electrical_workplan 미작업: 관련 파일 없음
[✓] heavy_lifting_workplan 미작업: 관련 파일 없음
[✓] docker-compose.yml 변경 없음
[✓] DB/schema 변경 없음
[✓] 실제 cleanup 실행 없음
[✓] 파일 삭제/생성/이동 없음
[✓] admin-web host port publish 없음
[✓] 서버 배포 없음
[✓] secret/token 출력 없음
```

---

## 커밋

**커밋 해시**: e742caa  
**커밋 메시지**: feat(file-map): add cleanup preflight executor endpoint  
**Push 상태**: origin/master에 반영됨 ✓

```
e742caa feat(file-map): add cleanup preflight executor endpoint
29c959f Revert "docs(phase3y): preflight audit 1..."
```

---

## 변경 사항 요약

| 항목 | 상태 |
|------|------|
| file-map-executor 확장 | ✅ /cleanup/preflight endpoint 추가 |
| admin-web 통합 | ✅ callPythonExecutorPreflight() 추가 |
| cleanup-preflight route | ✅ TODO 제거, executor 호출 구현 |
| 테스트 | ✅ 16개 모두 PASS |
| cleanup-execute 회귀 | ✅ 없음 |
| read-only 보장 | ✅ Path.exists() 호출만 |
| /tmp 경로 강제 | ✅ validator 재사용 |
| 범위 제한 | ✅ 금지사항 모두 준수 |

---

## 다음 단계

### 1. 서버 반영 (승인 필요)
```
- docker-compose up -d --build admin-web file-map-executor
- api 컨테이너에서 smoke 테스트 실행
- 실제 cleanup 없음 (preflight는 read-only)
```

### 2. FILE-MAP-CLEANUP-E2E-SMOKE
```
- cleanup-preflight → cleanup-plan → cleanup-execute 통합 테스트
- 전체 cleanup workflow dry-run 검증
- Docker network 내부 실행
```

### 3. 운영 문서화
```
- cleanup-preflight 운영 기준 명시
- Docker network 내부 실행 기준 유지
- smoke 테스트 guide 업데이트
```

---

## 기술 메모

### read-only 구현 패턴

**preflight() 메서드**:
```python
def preflight(self, request_data):
    # read-only: 파일 존재 확인만
    for plan in plans:
        source_exists = Path(source).exists()  # ✓ stat 호출만
        # ✗ 파일 삭제, 생성, 이동 호출 없음
        # ✗ 실제 cleanup 실행 없음
```

**vs cleanup-execute()**:
```python
def execute(self, request_data):
    # dry_run=true에서도 실제 파일 작업 수행 가능
    # (현재는 skeleton이지만 향후 구분 필요)
```

### 스키마 분리 전략

- `ExecuteRequest/ExecuteResponse`: cleanup 실행용
- `PreflightRequest/PreflightResponse`: 사전검사 read-only용
- 공통: `ExecutePlan` (source, target, confirmed)
- 각자 adapter: `adaptExecutorResponse()`, `adaptPreflightResponse()`

---

## 최종 판정

**✅ PASS**

구현 완료, 테스트 통과, 금지사항 준수, 서버 반영 대기.

---

**작성**: Claude Haiku 4.5  
**보고 일시**: 2026-05-04T?:??:??Z  
**검증**: 코드 구현 + 테스트 + 범위 감사 완료
