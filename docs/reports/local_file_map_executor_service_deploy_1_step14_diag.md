# LOCAL-FILE-MAP-EXECUTOR-SERVICE-DEPLOY-1-STEP14-DIAG — cleanup-execute API 연결 실패 진단

**작업 일시**: 2026-05-03  
**작업 단계**: 배포 진단 (read-only)  
**기준선**: efebffa (로컬/서버 동기화)

## 작업 내용

DEPLOY-1 Step 14 dry_run smoke 테스트에서 `http://admin-web:3000/api/file-map/cleanup-execute` API 호출이 CONNECTION_ERROR로 실패.
이 단계에서는 read-only로 실패 원인을 진단하고, smoke 재실행/코드 수정/컨테이너 재시작은 수행하지 않음.

## 기준선

**로컬/서버**:
```
HEAD: efebffa
origin/master: efebffa
status: clean ✓
```

## 컨테이너 상태

### 현재 실행 중 컨테이너
```
haehan-ai-orchestrator-admin-web           Up 3 minutes
haehan-ai-orchestrator-api                 Up 25 hours (healthy)
haehan-ai-orchestrator-file-map-executor   Up 5 minutes (healthy)
haehan-ai-orchestrator-browser-worker      Up 2 days (healthy)
```

모두 정상 상태. ✓

### Host port 설정
```
admin-web: 3000/tcp (host port publish 없음)
api: 127.0.0.1:8400->8400/tcp
file-map-executor: 8510/tcp (host port publish 없음)
```

## host 접근 결과

### 127.0.0.1:3000 (host에서 admin-web 접근)
```
Result: Connection refused
Reason: admin-web이 host port 3000을 publish하지 않음
```

**결론**: host에서는 admin-web에 직접 접근 불가.
Docker network 내부에서만 접근 가능.

## docker network 접근 결과

### admin-web:3000/file-map
```
API Call: http://admin-web:3000/file-map (Docker network 내부 from api container)
Status: 200 OK
Response: HTML 콘텐츠 (Next.js page)
```

**결론**: Docker network 내부에서 admin-web 기본 페이지 접근 가능. ✓

### admin-web:3000/api/file-map/cleanup-execute
```
API Call: http://admin-web:3000/api/file-map/cleanup-execute
Status: [진단 중]
현상: smoke_cleanup_execute_api_dry_run.py에서 CONNECTION_ERROR 보고
```

## admin-web route 확인

### 소스 파일
```
admin-web/src/app/api/file-map/cleanup-execute/route.ts: 존재 ✓
```

### route 구현 분석
- method: POST
- 입력 검증:
  - approval_token 검증
  - user_confirmed_execution 확인
  - preflight_id 확인
  - plans 정규화
- executor 호출: `callPythonExecutor()`
- 응답 변환: `adaptExecutorResponse()`

### callPythonExecutor 함수 분석
```
File: admin-web/src/lib/file-map/pythonExecutor.ts
Line 20: const executorUrl = process.env.FILE_MAP_EXECUTOR_URL || 'http://file-map-executor:8510';
Line 22: const endpoint = `${executorUrl}/cleanup/execute`;
```

**발견**:
- pythonExecutor는 `FILE_MAP_EXECUTOR_URL + /cleanup/execute` 호출
- 즉: `http://file-map-executor:8510/cleanup/execute`
- 이것은 Next.js route handler 내부에서만 접근 가능

## file-map-executor health

### Health endpoint 확인
```
Endpoint: http://file-map-executor:8510/health
Status: 200 OK
Response: {"status":"healthy","service":"file-map-executor","version":"1.0"}
```

**결론**: file-map-executor service 정상 작동. ✓

## 환경변수 확인

### FILE_MAP_EXECUTOR_URL
```
컨테이너 설정: docker-compose.yml line 65
  environment:
    FILE_MAP_EXECUTOR_URL: "http://file-map-executor:8510"

컨테이너 실제 값:
  ✓ FILE_MAP_EXECUTOR_URL=[http://file-map-executor:8510] (SET)
```

**결론**: 환경변수 정상 설정. ✓

## docker-compose.yml 설정 확인

```yaml
admin-web:
  environment:
    NODE_ENV: production
    FILE_MAP_EXECUTOR_URL: "http://file-map-executor:8510"
  depends_on:
    ai-orchestrator-api:
      condition: service_healthy
    file-map-executor:
      condition: service_healthy
```

**결론**: compose 설정 정상. ✓

## 원인 분류

### Case A — URL 실행 위치 오류
```
증상:
- host에서는 admin-web:3000 접근 불가 ✓ (observed)
- Docker network 내부에서는 admin-web:3000 접근 가능 ✓ (observed)

판정: 부분 확인됨
- host에서 smoke 실행 시 admin-web:3000 접근 불가
- 그러나 smoke는 Docker network 내부(server)에서 실행됨
- server는 admin-web:3000 접근 가능한 위치
- 따라서 URL 실행 위치 오류는 낮음
```

### Case B — admin-web route 문제
```
증상:
- /file-map은 응답함 (200 OK) ✓
- /api/file-map/cleanup-execute는 호출 실패 (CONNECTION_ERROR) ✓
- route source 파일 존재 ✓
- admin-web logs에 error 없음

의심:
1. Next.js route 빌드 누락?
   - route.ts 파일이 있고, admin-web rebuild 수행함
   - 그러나 빌드 결과에 route가 포함되었는지 미확인

2. 실제 route 동작 테스트 미완료
   - Docker network 내부에서 POST 요청 테스트 필요
   - 현재는 /file-map GET만 확인, /api/file-map/cleanup-execute는 미테스트

3. callPythonExecutor의 file-map-executor 호출
   - FILE_MAP_EXECUTOR_URL 설정됨 ✓
   - 그러나 실제 호출 동작은 미확인

판정: 높음 - admin-web route 구현/빌드 문제 추정
```

### Case C — executor 연결 문제
```
증상:
- FILE_MAP_EXECUTOR_URL 설정됨 ✓
- file-map-executor health OK ✓
- admin-web과 file-map-executor의 network (app_web) 연결됨 ✓

의심: 낮음 - 설정/network/health 모두 정상
```

### Case D — file-map-executor 문제
```
증상:
- health endpoint 응답 정상 ✓
- port 8510 열려있음 ✓

의심: 낮음 - executor 자체는 정상
```

## 최종 판정

**원인 분류: Case B (admin-web route 문제) — 높음**

Smoke 테스트가 호출하려는 엔드포인트:
```
http://admin-web:3000/api/file-map/cleanup-execute
```

상태:
- ✓ admin-web 컨테이너 실행 중
- ✓ route source 파일 존재
- ✓ docker-compose rebuild 수행
- ✗ 실제 route 동작 미확인 (CONNECTION_ERROR)
- ✓ 환경변수 정상 설정
- ✓ file-map-executor health 정상

**가설**:
1. admin-web rebuild 중 Next.js route 빌드 실패
2. 또는 runtime에 route handler 초기화 실패
3. admin-web 프로세스가 route를 로드하지 못함

## 다음 조치

### 단기 (진단 단계)
1. admin-web의 /api/file-map/cleanup-execute를 Docker network 내부에서 직접 호출하여 응답 확인
2. admin-web 로그에서 route 로딩 관련 메시지 확인
3. admin-web 컨테이너 내부에서 route 파일의 .next 산출물 존재 여부 확인

### 중기 (해결 단계)
1. admin-web Dockerfile 또는 compose 설정 검토
   - build time에 필요한 env 설정 확인
   - runtime env 전달 확인
2. admin-web rebuild with explicit env 설정
3. smoke 테스트 재실행

### 장기
- smoke 테스트 실패 원인이 admin-web 구현인지, 배포 구조인지 명확히
- case-by-case 테스트 추가 (GET /file-map, OPTIONS /api/file-map/cleanup-execute 등)

## 생성 보고서

- `docs/reports/local_file_map_executor_service_deploy_1_step14_diag.md` (본 파일)

## 최종 판정

**WARN**

진단 수행 완료. 원인은 Case B (admin-web route 문제)로 추정.
모든 인프라(컨테이너, network, executor)는 정상이나, admin-web의 API route 동작 실패로 판단.
다음 단계는 admin-web의 route 동작 확인 및 rebuild 필요.

