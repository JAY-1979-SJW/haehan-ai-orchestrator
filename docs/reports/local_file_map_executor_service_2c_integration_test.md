# LOCAL-FILE-MAP-EXECUTOR-SERVICE-2C 통합 테스트 보고서

**작성 일시**: 2026-05-03 20:15:00  
**종합 판정**: READY (통합 테스트 준비 완료)

---

## 작업 내용

EXECUTOR-SERVICE-2B에서 구현한 admin-web HTTP client와 EXECUTOR-SERVICE-2A의 file-map-executor service 간 통합 테스트 준비.

**목표:**
- admin-web → file-map-executor 간 HTTP 통신 검증
- API 응답 구조 검증
- 파일 무결성 확인 (dry_run 동작)
- audit 기록 생성 확인

---

## 기준선

| 항목 | 값 |
|------|-----|
| HEAD | c6c5c05 (EXECUTOR-SERVICE-2B 커밋) |
| branch | master |
| git status | clean |

---

## 테스트 구조

### 통합 흐름

```
클라이언트 (smoke test)
    ↓
POST /api/file-map/cleanup-execute (admin-web)
    ↓
callPythonExecutor() [HTTP client]
    ↓
POST /cleanup/execute (file-map-executor:8510)
    ↓
ExecutorService.execute()
    ↓
응답 adapter
    ↓
응답 반환
```

### 핵심 검증 포인트

| 포인트 | 검증 내용 |
|--------|---------|
| Service discovery | admin-web → file-map-executor DNS 해석 (docker network) |
| HTTP 통신 | POST /cleanup/execute 요청/응답 성공 |
| 응답 구조 | executor 응답 → admin-web 형식 adapter 검증 |
| Timeout | 30초 timeout 설정 및 동작 |
| Error handling | HTTP 오류 및 네트워크 오류 처리 |
| File integrity | dry_run=true로 파일 미변경 확인 |

---

## 테스트 환경 설정

### Docker Compose 구성

**파일**: docker/docker-compose.dev.yml

**서비스:**
```yaml
services:
  admin-web:
    build: admin-web/Dockerfile
    port: 3000
    env: FILE_MAP_EXECUTOR_URL=http://file-map-executor:8510
    network: app_web

  file-map-executor:
    build: docker/file-map-executor.Dockerfile
    port: 8510
    network: app_web
```

**특징:**
- ✅ app_web 네트워크로 내부 통신
- ✅ admin-web이 file-map-executor:8510으로 DNS 접근 가능
- ✅ 호스트는 localhost:3000으로 admin-web 접근
- ✅ Health checks 포함

---

## Smoke Test 스크립트

**파일**: scripts/file-map/smoke_cleanup_execute_api_dry_run.py

**단계별 검증:**

1. **환경 확인** (check_environment)
   - FILE_MAP_BASE_URL 확인 (필수)
   - 예: http://localhost:3000 또는 http://172.18.0.12:3000

2. **Fixture 생성** (create_fixtures)
   - 임시 디렉터리 생성 (/tmp/file_map_api_smoke_*)
   - source 디렉터리: document-a.txt, document-b.txt, 신분증.pdf
   - target 디렉터리: existing.txt
   - 목표: dry_run 동작 검증

3. **경로 검증** (validate_target_path)
   - base_target_dir이 /tmp로 시작하는지 확인
   - executor service의 /tmp 강제 정책과 일치

4. **Request 작성** (prepare_request_payload)
   ```json
   {
     "dry_run": true,
     "preflight_id": "uuid",
     "package_id": "uuid",
     "approval_token": "user-approved-cleanup-{uuid}",
     "user_confirmed_execution": true,
     "base_target_dir": "/tmp/...",
     "plans": [
       { "source": "/tmp/.../document-a.txt", "target": "/tmp/.../document-a.txt", "confirmed": true },
       { "source": "/tmp/.../document-b.txt", "target": "/tmp/.../document-b.txt", "confirmed": true }
     ]
   }
   ```

5. **API 호출** (call_api)
   - POST http://localhost:3000/api/file-map/cleanup-execute
   - 기대 응답 (200):
     ```json
     {
       "ok": true,
       "run_id": "uuid",
       "package_id": "uuid",
       "timestamp": "ISO8601",
       "success_count": 2,
       "failed_count": 0,
       "skipped_count": 0,
       "conflict_count": 0,
       "succeeded": ["/tmp/.../document-a.txt", "/tmp/.../document-b.txt"],
       "failed": [],
       "skipped": [],
       "conflicts": []
     }
     ```

6. **File integrity 검증** (verify_fixtures_untouched)
   - source 파일 존재 확인 (dry_run이므로 유지)
   - target에 document 파일이 없음 확인 (복사되지 않음)
   - target의 existing.txt 유지 확인

---

## 예상 테스트 결과

### Success Path (expected)

**Status:** PASS

**검증:**
- ✅ admin-web healthy (3000 포트)
- ✅ file-map-executor healthy (8510 포트)
- ✅ HTTP 통신 성공 (200)
- ✅ run_id 반환
- ✅ success_count=2
- ✅ response adapter: 모든 필드 존재
- ✅ 파일 무결성: source 파일 유지, target 미변경

**증거:**
```json
{
  "status": "PASS",
  "api_call_status": {
    "status": "SUCCESS",
    "http_status": 200,
    "run_id": "...",
    "success_count": 2,
    "succeeded": 2
  },
  "file_integrity": {
    "source_files_exist": true,
    "target_unmoved": true
  }
}
```

### Potential Issues

| 이슈 | 원인 | 해결 |
|-----|------|------|
| Connection refused | file-map-executor 미실행 | docker service 재시작 |
| 503 Service unavailable | admin-web → executor 통신 오류 | 네트워크/DNS 확인 |
| timeout | executor 응답 지연 | 30초 timeout 로그 확인 |
| run_id 미반환 | executor 응답 구조 오류 | response adapter 검증 |
| 파일 변경됨 | dry_run=false 실행 됨 | route.ts에서 dry_run 강제 확인 |

---

## 테스트 실행 방법

### Option 1: Linux/Mac

```bash
# 1. 컨테이너 시작
cd /path/to/haehan-ai-orchestrator
docker compose -f docker/docker-compose.dev.yml up -d

# 2. 서비스 대기 (30초)
sleep 30

# 3. Smoke test 실행
export FILE_MAP_BASE_URL="http://localhost:3000"
python3 scripts/file-map/smoke_cleanup_execute_api_dry_run.py | python3 -m json.tool

# 4. 결과 확인
# status="PASS" 또는 "WARN" 확인

# 5. Cleanup
docker compose -f docker/docker-compose.dev.yml down
```

### Option 2: Windows (PowerShell)

```powershell
# 1. 컨테이너 시작
cd C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator
docker compose -f docker/docker-compose.dev.yml up -d

# 2. 서비스 대기 (30초)
Start-Sleep -Seconds 30

# 3. Smoke test 실행
$env:FILE_MAP_BASE_URL = "http://localhost:3000"
python scripts/file-map/smoke_cleanup_execute_api_dry_run.py | python -m json.tool

# 4. Cleanup
docker compose -f docker/docker-compose.dev.yml down
```

### Option 3: Using shell script (Linux/Mac)

```bash
bash scripts/file-map/run_executor_service_2c_smoke_test.sh

# 환경변수로 컨테이너 유지
KEEP_CONTAINERS=1 bash scripts/file-map/run_executor_service_2c_smoke_test.sh
```

---

## 테스트 체크리스트

- [ ] Docker Desktop 실행 중 (또는 Docker 서비스 활성)
- [ ] python3 또는 python 설치됨
- [ ] requests 라이브러리 설치: `pip install requests`
- [ ] 기존 컨테이너 정리: `docker compose -f docker/docker-compose.dev.yml down`
- [ ] docker-compose.dev.yml 확인
- [ ] file-map-executor.Dockerfile 확인
- [ ] admin-web/Dockerfile 확인
- [ ] smoke test 스크립트 실행 권한
- [ ] /tmp 경로 접근 가능 (Linux/Mac) 또는 Docker volume 매핑 (Windows)

---

## 예상 문제와 해결

### Issue 1: "CONNECTION_ERROR: API 접속 실패"

**원인**: admin-web이 실행되지 않거나 응답하지 않음

**검증:**
```bash
docker compose -f docker/docker-compose.dev.yml ps
# admin-web이 "healthy" 상태인지 확인

curl http://localhost:3000
# 200 OK 응답 확인
```

**해결:**
```bash
docker compose -f docker/docker-compose.dev.yml logs admin-web
# 로그 확인
docker compose -f docker/docker-compose.dev.yml restart admin-web
```

### Issue 2: "HTTP_ERROR: status=503"

**원인**: admin-web이 file-map-executor에 접근하지 못함 (DNS/네트워크)

**검증:**
```bash
docker compose -f docker/docker-compose.dev.yml exec admin-web \
  curl http://file-map-executor:8510/health
# 200 응답 확인
```

**해결:**
- 네트워크 확인: `docker network ls | grep app_web`
- 서비스 재시작: `docker compose -f docker/docker-compose.dev.yml restart`

### Issue 3: "파일 무결성 검증 실패"

**원인**: 파일이 실제로 이동됨 (dry_run=false 실행)

**검증:**
- route.ts 확인: `dry_run: dry_run === false ? false : true` (line 56)
- executor 확인: security.py에서 dry_run=false 차단 (403)

### Issue 4: "run_id 미반환"

**원인**: response adapter 또는 executor 응답 구조 오류

**검증:**
```bash
docker compose -f docker/docker-compose.dev.yml logs file-map-executor
# executor 응답 확인

curl -X POST http://localhost:8510/cleanup/execute \
  -H "Content-Type: application/json" \
  -d '{"dry_run":true,"base_target_dir":"/tmp/test","plans":[]}'
# 직접 executor 호출
```

---

## 정책 보존 확인

| 정책 | 검증 |
|-----|------|
| dry_run=true 강제 | ✅ route.ts:56 적용 |
| /tmp 경로 강제 | ✅ executor service:security.py 적용 |
| approval_token 검증 | ✅ route.ts:24 적용 |
| user_confirmed_execution | ✅ route.ts:32 적용 |
| run_id 생성 | ✅ executor service:service.py 적용 |
| response adapter | ✅ pythonExecutor.ts 적용 |
| 30초 timeout | ✅ pythonExecutor.ts:32 적용 |

---

## 다음 단계

**EXECUTOR-SERVICE-2D: 서버 배포 준비**

1. docker-compose.yml과 docker-compose.file-map-executor.yml 동기화
2. 서버 환경에 맞게 포트/네트워크 재구성
3. 환경변수 설정 (FILE_MAP_EXECUTOR_URL 등)
4. SSL/TLS 구성 (필요 시)
5. 모니터링 및 로깅 구성

**현재 상태:**
- ✅ admin-web HTTP client 완성
- ✅ file-map-executor service 완성
- ✅ 로컬 통합 테스트 환경 준비
- ⏳ 실제 통합 테스트 실행 (사용자)
- ⏳ 서버 배포 준비 (Step 2D)
- ⏳ 최종 테스트 (Step 2E)

---

## 추가 자료

### 관련 파일

- admin-web/src/app/api/file-map/cleanup-execute/route.ts (API 엔드포인트)
- admin-web/src/lib/file-map/pythonExecutor.ts (HTTP client)
- services/file_map_executor/app.py (executor service)
- docker/docker-compose.dev.yml (로컬 compose)
- scripts/file-map/smoke_cleanup_execute_api_dry_run.py (테스트 스크립트)
- scripts/file-map/run_executor_service_2c_smoke_test.sh (테스트 실행기)

### 네트워크 다이어그램

```
┌─────────────────────────────────────────┐
│   docker network: app_web (bridge)      │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  admin-web (Node.js)             │  │
│  │  localhost:3000                  │  │
│  │  API: /api/file-map/cleanup-*    │  │
│  │  Client: callPythonExecutor()    │  │
│  └──────────────────────────────────┘  │
│           ↓                             │
│    HTTP POST /cleanup/execute           │
│    FILE_MAP_EXECUTOR_URL=               │
│    http://file-map-executor:8510        │
│           ↓                             │
│  ┌──────────────────────────────────┐  │
│  │  file-map-executor (FastAPI)     │  │
│  │  :8510                           │  │
│  │  Service: cleanupexecutor_api    │  │
│  │  Validation: dry_run, /tmp path  │  │
│  └──────────────────────────────────┘  │
│                                         │
└─────────────────────────────────────────┘
```

---

**최종 판정**: ✅ READY (통합 테스트 준비 완료)

모든 구성 요소 준비 완료. 사용자가 로컬 또는 테스트 환경에서 통합 테스트를 실행할 수 있습니다.

---

**작성자**: Claude Haiku 4.5  
**최종 수정**: 2026-05-03 20:15:00
