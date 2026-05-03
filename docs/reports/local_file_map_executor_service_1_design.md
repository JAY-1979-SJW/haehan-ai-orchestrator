# LOCAL-FILE-MAP-EXECUTOR-SERVICE-1 설계 감사 보고서

**작성 일시**: 2026-05-03 16:50:00  
**종합 판정**: PASS (설계 수립 완료)

---

## 작업 내용

AUTO-CONTROL-2B-RUN에서 발생한 HTTP 500 오류를 근본적으로 해결하기 위해, file-map 실행기를 별도 Python service로 분리하는 아키텍처 설계를 수행했다.

---

## 기준선

| 항목 | 로컬 | 서버 |
|------|------|------|
| HEAD | e44b3b6 | e44b3b6 |
| branch | master | master |
| git status | clean | M docs/reports/* |

---

## AUTO-CONTROL-2B-RUN FAIL 원인

### HTTP 500 발생 경로

```
POST /api/file-map/cleanup-execute
↓
admin-web route.ts → callPythonExecutor()
↓
child_process.spawn('python', [cleanup_executor_api.py])
↓
❌ cleanup_executor_api.py를 찾을 수 없음
↓
spawn 오류 → HTTP 500 반환
```

### 근본 원인

| 구성 | 현황 | 문제 |
|------|------|------|
| admin-web build context | ./admin-web | agent/ 폴더 미포함 |
| admin-web runtime | Node.js 20-alpine | Python 런타임 없음 |
| docker-compose volumes | 없음 | agent 접근 불가 |
| cleanup_executor_api.py 위치 | /app 상대경로 | container에 존재하지 않음 |

---

## 현재 Docker 구조

### 기존 3개 service

```yaml
ai-orchestrator-api:
  build context: . (전체 repo)
  runtime: Python 3.11
  agent 접근: ✅ 가능

admin-web:
  build context: ./admin-web (제한됨)
  runtime: Node.js 20
  agent 접근: ❌ 불가능 ← 문제점
  Python runtime: ❌ 없음 ← 문제점

browser-worker:
  build context: . (전체 repo)
  runtime: Python
  agent 접근: ✅ 가능
```

### admin-web Dockerfile 분석

```dockerfile
# Stage 3: runtime
FROM node:20-alpine

# .next/standalone만 복사 (최소화)
COPY --from=builder /app/.next/standalone ./

# Python 없음
# agent 폴더 없음
```

---

## 대안 비교

### Option A: admin-web에 Python/agent 포함

**변경:**
```dockerfile
FROM node:20-alpine
RUN apk add --no-cache python3
COPY agent ./agent
```

**장점:**
- 구현 빠름
- 추가 service 불필요

**단점:**
- ❌ admin-web 책임 과다 (Node.js + Python 혼합)
- ❌ 이미지 크기 200MB → 500MB+
- ❌ 보안 경계 약화
- ❌ 문제 격리 어려움
- ❌ 운영 복잡도 증가

**평가**: 단기 해결책이지만 장기 운영성 낮음

---

### Option B: file-map-executor 별도 Python service 신설

**신규 service:**
```yaml
file-map-executor:
  image: python:3.11-slim
  port: 8510 (docker network only)
  networks: [default, app_web]
```

**admin-web 변경:**
```typescript
// spawn 제거 → HTTP POST로 변경
const response = await fetch('http://file-map-executor:8510/cleanup/execute', {
  method: 'POST',
  body: JSON.stringify(payload)
});
```

**장점:**
- ✅ 역할 분리 명확
- ✅ Python runtime 독립적
- ✅ admin-web은 HTTP client만 담당
- ✅ 확장/감시/로그 분리 용이
- ✅ 보안 경계 명확
- ✅ 이미지 크기 최적화 (admin-web: 200MB 유지)
- ✅ 향후 executor 독립 배포/스케일링 가능

**단점:**
- compose service 추가 필요
- 내부 API 계약 필요

**평가**: 최고의 아키텍처 설계

---

### Option C: ai-orchestrator-api에 executor endpoint 추가

**추가 endpoint:**
```python
@app.post("/api/v1/file-map/cleanup/execute")
async def execute_cleanup(request):
    return cleanup_executor_api.execute(request)
```

**장점:**
- 기존 Python API 서비스 활용 가능

**단점:**
- ❌ ai-orchestrator-api 책임 증가
- ❌ 역할 경계가 흐려짐
- ❌ admin-web이 ai-orchestrator-api에 의존
- ❌ network 계층 추가

**평가**: 단순하지만 장기 확장성 낮음

---

## 권장안: Option B

**선택 이유:**

1. **역할 분리 명확**
   - admin-web: UI + cleanup 요청 조율 (HTTP client)
   - file-map-executor: 파일 정리 로직 실행 (Python)
   - 각 service는 단일 책임 원칙 준수

2. **보안 경계 강화**
   - admin-web: Node.js only (보안 footprint 작음)
   - file-map-executor: Python only (specialized)
   - 언어 혼합으로 인한 보안 위험 회피

3. **운영 효율성**
   - admin-web 이미지: 200MB (변화 없음)
   - file-map-executor: 400MB (독립 image)
   - 문제 격리 (executor 문제 ≠ admin-web 문제)

4. **확장성**
   - executor 독립 배포/스케일링 가능
   - multi-region 배포 시 재사용 가능
   - 향후 다른 언어(Go, Rust) 이식 용이

---

## file-map-executor 설계

### Service 사양

| 항목 | 값 |
|------|-----|
| service name | file-map-executor |
| base image | python:3.11-slim |
| working directory | /app |
| internal port | 8510 |
| host port mapping | ❌ 없음 (docker network only) |
| docker networks | default, app_web |
| dependencies | ❌ 없음 (독립 service) |
| healthcheck | GET /health → { status: "healthy" } |
| restart policy | unless-stopped |

### endpoints

```http
GET /health
→ Status: 200
→ Body: { "status": "healthy", "version": "1.0" }

POST /cleanup/execute
→ Request: { dry_run: true, plans: [...], base_target_dir: "/tmp/..." }
→ Status: 200 (success) / 400 (validation) / 422 (execution error)
→ Body: { "run_id": "uuid", "success_count": 2, "succeeded": [...], ... }

GET /cleanup/audit?run_id=<run_id>
→ Status: 200
→ Body: { "audit_lines": [...], "masked_paths": [...], ... }

GET /cleanup/rollback?run_id=<run_id>
→ Status: 200
→ Body: { "manifest": {...}, "rollback_status": "pending" }
```

### 핵심 정책

```
- dry_run 기본값: true (변경 불가능, 모든 요청에서 강제)
- /tmp fixture만 허용 (smoke mode에서 실제 경로 차단)
- source 파일 유지 (이동 금지)
- target 파일 미생성 (dry_run=true일 때)
- run_id 자동 생성 (UUID v4)
- audit JSONL 생성 (/app/audit/{run_id}.jsonl)
- rollback manifest 생성 (dry_run=true여도)

보안 정책:
- token/path/payload 원문 로그 금지
- 민감정보 마스킹 필수
- HTTP 500 반환 금지 (모든 오류는 4xx + error field)
- stderr 캡처 금지 (stdout only)
```

### Dockerfile 스케치

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy file-map executor modules
COPY agent/local_inventory/file_map ./agent/local_inventory/file_map

# Install dependencies
RUN pip install --no-cache-dir \
    flask==3.0.0 \
    requests==2.31.0 \
    pydantic==2.0.0

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8510
ENV EXECUTOR_MODE=server

EXPOSE 8510

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8510/health', timeout=3)"

CMD ["python", "-m", "flask", "--app=agent.local_inventory.file_map.executor_service", "run", "--host=0.0.0.0", "--port=8510"]
```

---

## admin-web 변경 범위

### 대상 파일

```
admin-web/src/lib/file-map/pythonExecutor.ts
```

### 변경 방향

**제거 대상:**
- `spawn('child_process')` 전체 제거
- `resolveRepoRoot()` 함수 제거
- `resolveCleanupExecutorPath()` 함수 제거
- PYTHONPATH 환경변수 설정 제거

**추가 대상:**
```typescript
const EXECUTOR_URL = process.env.FILE_MAP_EXECUTOR_URL || 'http://file-map-executor:8510';

export async function callPythonExecutor(
  inputData: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const response = await fetch(`${EXECUTOR_URL}/cleanup/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(inputData),
    timeout: 30000
  });

  if (!response.ok) {
    throw new Error(
      `Executor service error: HTTP ${response.status}`
    );
  }

  return response.json();
}
```

### 유지 사항

✅ approval token 검증 (route.ts에서)  
✅ API 응답 key 구조 (run_id, success_count, succeeded, failed_count 등)  
✅ dry_run 기본값 (true)  
✅ 기존 route.ts 로직 변경 없음  
✅ 기존 fixture policy 유지  

---

## 테스트 계획

### 로컬 개발 환경 (docker-compose)

```bash
Step 1. file-map-executor 빌드 & run
  docker-compose up -d file-map-executor

Step 2. admin-web 빌드 & run
  docker-compose up -d admin-web

Step 3. file-map-executor health 확인
  curl http://172.18.0.X:8510/health
  → { "status": "healthy" } ✓

Step 4. admin-web cleanup-execute 호출
  POST /api/file-map/cleanup-execute
  Content-Type: application/json
  {
    "dry_run": true,
    "preflight_id": "uuid",
    "package_id": "uuid",
    "approval_token": "user-approved-cleanup-uuid",
    "user_confirmed_execution": true,
    "base_target_dir": "/tmp/file_map_test_...",
    "plans": [...]
  }

Step 5. 응답 검증
  Status: 200 ✓
  Body: { "run_id": "uuid", "success_count": 2, "succeeded": [...] } ✓
```

### 필수 검증 checklist

- [ ] file-map-executor GET /health → 200 OK
- [ ] admin-web POST /api/file-map/cleanup-execute → 200 OK (dry_run=true)
- [ ] run_id 형식 확인 (UUID v4)
- [ ] success_count >= 0 (정수)
- [ ] succeeded array 형식 확인 (배열)
- [ ] failed_count = 0
- [ ] source/document-a.txt 유지 ✓
- [ ] source/document-b.txt 유지 ✓
- [ ] source/신분증.pdf 유지 ✓
- [ ] target/document-a.txt 없음 ✓
- [ ] target/document-b.txt 없음 ✓
- [ ] target/existing.txt 유지 ✓
- [ ] audit JSONL 생성 ✓ (/app/audit/{run_id}.jsonl)
- [ ] rollback manifest 생성 ✓
- [ ] dry_run=true 정책상 rollback 미실행 ✓
- [ ] HTTP 500 없음 ✓
- [ ] Python spawn error 없음 ✓
- [ ] stderr 로그 없음 ✓
- [ ] token/path/payload 원문 로그 없음 ✓
- [ ] docker-compose down 후 artifact cleanup ✓

---

## 배포 단계 분리안

### EXECUTOR-SERVICE-2A: service skeleton 추가

```
목표: file-map-executor service 초기 구성
파일:
  - docker/file-map-executor.Dockerfile (신규)
  - docker/file-map-executor.entrypoint.py (신규)
  - docker-compose.yml (수정 허용 단계에서만)
검증:
  - docker-compose up file-map-executor 성공
  - GET /health → 200
```

### EXECUTOR-SERVICE-2B: admin-web client 전환

```
목표: spawn → HTTP 호출로 변경
파일:
  - admin-web/src/lib/file-map/pythonExecutor.ts (수정)
검증:
  - npm run typecheck PASS
  - npm run build PASS
  - spawn 호출 0건
  - HTTP fetch 호출만 남음
```

### EXECUTOR-SERVICE-2C: 로컬 smoke 테스트

```
목표: 로컬 환경에서 API dry_run 검증
실행:
  - docker-compose up (전체)
  - smoke_cleanup_execute_api_dry_run.py 실행
검증:
  - 모든 필수 checklist PASS
  - fixture cleanup 성공
```

### EXECUTOR-SERVICE-2D: 서버 배포 사전 준비

```
목표: 배포 전 설정 및 검증
단계:
  1. 서버 docker-compose.yml pull
  2. file-map-executor service section 추가
  3. admin-web service depends_on 추가
  4. docker-compose config 검증
  5. 기존 container 정리 계획 (admin-web 기존 instance 제거)
```

### EXECUTOR-SERVICE-2E: 서버 배포 & AUTO-CONTROL-2B-RUN 재실행

```
목표: 배포 환경에서 API dry_run 검증
단계:
  1. 서버 docker-compose pull origin/master
  2. docker-compose up -d file-map-executor
  3. docker-compose up -d admin-web (기존 container 종료 후)
  4. healthcheck 확인
  5. AUTO-CONTROL-2B-RUN Step 6 재실행
검증:
  - HTTP 500 해결 ✓
  - 모든 필수 검증 PASS
```

---

## 커밋/푸시

**현재 파일 상태:**
```
M docs/reports/local_file_map_auto_control_1.json (auto-audit)
M docs/reports/local_file_map_auto_control_1.md (auto-audit)
A docs/reports/local_file_map_executor_service_1_design.md (설계 보고서)
```

**커밋 계획:**
```bash
git add docs/reports/local_file_map_executor_service_1_design.md
git commit -m "docs(file-map): design dedicated executor service"
git push origin master
```

---

## 최종 판정

**✅ PASS (설계 수립 완료)**

| 항목 | 결과 |
|------|------|
| 기준선 확인 | PASS ✓ |
| FAIL 원인 분석 | PASS ✓ |
| Docker 구조 감사 | PASS ✓ |
| 대안 비교 | PASS ✓ |
| service 설계 | PASS ✓ |
| 변경 범위 결정 | PASS ✓ |
| 테스트 계획 | PASS ✓ |
| 배포 단계 분리 | PASS ✓ |

---

## 다음 단계

### 즉시 실행 가능

1. **EXECUTOR-SERVICE-2A** (docker/file-map-executor.Dockerfile 생성)
2. **EXECUTOR-SERVICE-2B** (admin-web pythonExecutor.ts 수정)
3. **EXECUTOR-SERVICE-2C** (로컬 smoke 테스트)

### 승인 대기

4. **EXECUTOR-SERVICE-2D** (서버 docker-compose 수정)
5. **EXECUTOR-SERVICE-2E** (서버 배포 & AUTO-CONTROL-2B-RUN 재실행)

---

**작성자**: Claude Haiku 4.5  
**최종 수정**: 2026-05-03 16:50:00
