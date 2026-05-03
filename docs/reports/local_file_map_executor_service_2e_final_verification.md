# LOCAL-FILE-MAP-EXECUTOR-SERVICE-2E 최종 검증 보고서

**작성 일시**: 2026-05-03 20:45:00  
**종합 판정**: TEMPLATE (배포 후 사용자가 실행하여 작성해야 함)

---

## 작업 개요

EXECUTOR-SERVICE-2D에서 서버 배포를 완료한 후, 실제 운영 환경(haehan-app)에서 최종 검증을 수행하는 단계.

**목표:**
- 서버에서 admin-web + file-map-executor HTTP 통신 검증
- 실제 환경에서 cleanup-execute API 동작 확인
- audit 기록 생성 및 파일 무결성 확인
- 모니터링 및 로그 정상 확인

---

## 배포 전제조건

배포 후 이 검증을 수행하기 전에 다음이 완료되어야 합니다:

- [x] EXECUTOR-SERVICE-2A: file-map-executor service 구현
- [x] EXECUTOR-SERVICE-2B: admin-web HTTP client 변환
- [x] EXECUTOR-SERVICE-2C: 로컬 통합 테스트 환경 준비
- [x] EXECUTOR-SERVICE-2D: 서버 배포 준비 및 체크리스트 작성
- [ ] EXECUTOR-SERVICE-2D 배포 실행 (사용자)
- [ ] 서버 docker-compose 파일 동기화 완료
- [ ] 환경변수 설정 완료
- [ ] Docker build 및 서비스 시작 완료

---

## 최종 검증 절차

### 단계 1: 기본 서비스 상태 확인

**실행 위치**: 서버 (haehan-app)

```bash
ssh haehan-app
cd /home/ubuntu/apps/haehan-ai-orchestrator

# 1.1 docker compose 상태
docker compose ps

# 기대 결과:
# NAME                                    STATUS
# haehan-ai-orchestrator-admin-web        Up (healthy)
# haehan-ai-orchestrator-file-map-executor  Up (healthy)
# ...
```

**체크리스트:**
- [ ] admin-web이 Up 상태인가? (STATUS에서 "healthy" 확인)
- [ ] file-map-executor가 Up 상태인가? (STATUS에서 "healthy" 확인)
- [ ] 다른 서비스는 영향을 받지 않았는가?

**문제 발생 시:**
```bash
# 로그 확인
docker compose logs file-map-executor
docker compose logs admin-web

# 서비스 재시작
docker compose restart file-map-executor
sleep 10
docker compose ps
```

### 단계 2: HTTP 통신 검증

**실행 위치**: 서버 (컨테이너 내부)

```bash
# admin-web에서 file-map-executor 접근 가능한지 확인
docker compose exec admin-web bash -c \
  'curl -s http://file-map-executor:8510/health | python3 -m json.tool'

# 기대 응답:
# {
#   "status": "healthy",
#   "service": "file-map-executor",
#   "version": "1.0"
# }
```

**체크리스트:**
- [ ] HTTP 200 응답을 받았는가?
- [ ] status="healthy"인가?
- [ ] service="file-map-executor"인가?

**문제 발생 시:**
```bash
# DNS 해석 확인
docker compose exec admin-web nslookup file-map-executor
docker compose exec admin-web ping file-map-executor

# 포트 확인
docker compose exec admin-web bash -c 'netstat -tlnp | grep -i listen'

# 네트워크 확인
docker network inspect app_web | python3 -m json.tool
```

### 단계 3: API 엔드포인트 검증

**실행 위치**: 서버 또는 로컬

#### 3.1 Health check endpoint

```bash
# 서버 또는 로컬에서 실행
curl -X GET http://localhost:3000/api/file-map/health 2>/dev/null || \
curl -X GET http://<server-ip>:3000/api/file-map/health

# 기대: 404 또는 서비스 상태 (정확한 endpoint는 admin-web에 정의되어 있음)
```

#### 3.2 Cleanup-execute API endpoint

```bash
# Request 준비
curl -X POST http://localhost:3000/api/file-map/cleanup-execute \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "preflight_id": "test-'"$(date +%s)"'",
    "package_id": "test-'"$(date +%s)"'",
    "approval_token": "user-approved-cleanup-e2e-test",
    "user_confirmed_execution": true,
    "base_target_dir": "/tmp/file-map-e2e-test",
    "plans": [
      {
        "source": "/tmp/file-map-e2e-test/source/test-a.txt",
        "target": "/tmp/file-map-e2e-test/target/test-a.txt",
        "confirmed": true
      }
    ]
  }' | python3 -m json.tool

# 기대 응답:
# {
#   "ok": true,
#   "run_id": "...",
#   "package_id": "...",
#   "timestamp": "2026-05-03T...",
#   "success_count": 1,
#   "failed_count": 0,
#   "skipped_count": 0,
#   "conflict_count": 0,
#   "succeeded": ["/tmp/..."],
#   "failed": [],
#   "skipped": [],
#   "conflicts": []
# }
```

**체크리스트:**
- [ ] HTTP 200 응답을 받았는가?
- [ ] ok=true인가?
- [ ] run_id가 생성되었는가? (UUID 형식)
- [ ] success_count=1인가?
- [ ] failed_count=0인가?
- [ ] timestamp가 현재 시간인가?
- [ ] 응답 구조가 admin-web 형식인가?

### 단계 4: 파일 시스템 검증 (dry_run 동작)

**실행 위치**: 서버

```bash
# 단계 3의 API 호출에서 run_id를 얻습니다
RUN_ID="<run_id from step 3>"

# 소스 파일이 여전히 존재하는지 확인 (dry_run이므로 복사되지 않아야 함)
ls -la /tmp/file-map-e2e-test/source/
# test-a.txt가 존재해야 함

# 타겟 디렉터리에 파일이 없는지 확인 (dry_run이므로 복사되면 안 됨)
ls -la /tmp/file-map-e2e-test/target/
# test-a.txt가 없어야 함 (또는 existing.txt 같은 기존 파일만 있어야 함)
```

**체크리스트:**
- [ ] 소스 파일이 여전히 존재하는가?
- [ ] 타겟에 파일이 복사되지 않았는가?
- [ ] dry_run 정책이 제대로 작동하는가?

### 단계 5: Audit 기록 확인

**실행 위치**: 서버

```bash
# file-map-executor의 audit 데이터 확인
docker compose exec file-map-executor bash -c \
  'find /app/audit -name "*.jsonl" -o -name "*.json" 2>/dev/null | head -10'

# 또는 로그에서 audit 기록 확인
docker compose logs file-map-executor | grep -i "audit\|run_id"
```

**체크리스트:**
- [ ] audit 파일이 생성되었는가?
- [ ] 로그에 run_id 기록이 있는가?
- [ ] timestamp와 metadata가 정상인가?

### 단계 6: 로깅 및 모니터링

**실행 위치**: 서버

```bash
# 6.1 file-map-executor 로그
docker compose logs --tail 50 file-map-executor

# 6.2 admin-web 로그
docker compose logs --tail 50 admin-web

# 6.3 전체 로그 (선택사항)
docker compose logs --tail 100 | tee /tmp/compose_logs_e2e.txt

# 로그 패턴 확인:
# - ERROR 또는 CRITICAL 레벨 메시지 없는가?
# - HTTP 500 에러가 없는가?
# - Timeout 오류가 없는가?
# - Connection refused 오류가 없는가?
```

**체크리스트:**
- [ ] ERROR 레벨 로그가 없는가?
- [ ] HTTP 500 에러가 없는가?
- [ ] 정상적인 요청/응답 로그가 있는가?
- [ ] timeout 오류가 없는가?

### 단계 7: 로드 테스트 (선택사항)

**목표**: 서버에서 안정적으로 여러 요청을 처리할 수 있는지 확인

```bash
# 간단한 반복 테스트
for i in {1..5}; do
  echo "=== Test $i ==="
  curl -s -X POST http://localhost:3000/api/file-map/cleanup-execute \
    -H "Content-Type: application/json" \
    -d "{
      \"dry_run\": true,
      \"preflight_id\": \"load-test-$i\",
      \"package_id\": \"load-test-$i\",
      \"approval_token\": \"user-approved-cleanup-load-$i\",
      \"user_confirmed_execution\": true,
      \"base_target_dir\": \"/tmp/load-test-$i\",
      \"plans\": []
    }" | python3 -c "import sys, json; r=json.load(sys.stdin); print(f'ok={r.get(\"ok\")}, run_id={r.get(\"run_id\", \"MISSING\")}')"
  sleep 2
done

# 기대: 모든 요청이 ok=true를 반환해야 함
```

**체크리스트:**
- [ ] 5개 요청 모두 성공했는가?
- [ ] run_id가 모두 다른 값인가?
- [ ] 응답 시간이 일정한가?

---

## 최종 검증 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| 단계 1: 서비스 상태 | [ ] PASS | admin-web, file-map-executor healthy |
| 단계 2: HTTP 통신 | [ ] PASS | admin-web → file-map-executor 연결 |
| 단계 3: API 응답 | [ ] PASS | 200, ok=true, run_id 생성 |
| 단계 4: 파일 무결성 | [ ] PASS | dry_run 정책 동작 확인 |
| 단계 5: Audit 기록 | [ ] PASS | audit 파일/로그 생성 |
| 단계 6: 로깅 정상 | [ ] PASS | ERROR/500 없음 |
| 단계 7: 로드 테스트 | [ ] PASS | (선택사항) 5개 요청 성공 |

---

## 문제 해결

### Issue 1: admin-web이 file-map-executor에 접근 불가

**증상**: admin-web 로그에 "Connection refused" 또는 "404" 오류

**진단:**
```bash
# 1. file-map-executor 실행 상태 확인
docker compose ps file-map-executor
# STATUS가 "healthy"인지 확인

# 2. 네트워크 확인
docker network inspect app_web

# 3. DNS 확인
docker compose exec admin-web nslookup file-map-executor
docker compose exec admin-web ping file-map-executor

# 4. 직접 접근 테스트
docker compose exec admin-web curl -v http://file-map-executor:8510/health
```

**해결:**
```bash
# file-map-executor 재시작
docker compose restart file-map-executor
sleep 10

# 네트워크 재연결 (극단적인 경우)
docker compose down
docker compose up -d
```

### Issue 2: 응답 구조 오류 (missing fields)

**증상**: 응답에서 run_id, package_id, timestamp 등이 누락됨

**진단:**
```bash
# file-map-executor 로그 확인
docker compose logs file-map-executor | grep -A 5 "error\|failed"

# 응답 어댑터 코드 확인
# admin-web/src/lib/file-map/pythonExecutor.ts의 adaptExecutorResponse() 함수

# 실제 executor 응답 확인
docker compose exec file-map-executor bash -c \
  'curl -X POST http://localhost:8510/cleanup/execute ...'
```

**해결:**
- pythonExecutor.ts의 adaptExecutorResponse() 함수 검증
- response fields mapping 재확인
- executor service의 응답 형식 재확인

### Issue 3: 파일이 예상과 다르게 변경됨

**증상**: dry_run=true임에도 파일이 복사/이동됨

**진단:**
```bash
# 1. API 요청 확인 (dry_run 필드가 true인가?)
docker compose logs admin-web | grep -i "dry_run"

# 2. route.ts의 dry_run 강제 확인
# Line 56: dry_run: dry_run === false ? false : true

# 3. executor의 dry_run 검증 확인
# services/file_map_executor/security.py의 validate_dry_run()

# 4. executor 로그에서 dry_run 값 확인
docker compose logs file-map-executor | grep -i "dry"
```

**해결:**
- route.ts의 dry_run 강제 정책 재확인
- executor service의 security validation 재확인
- admin-web의 HTTP request payload 검증

### Issue 4: Timeout 오류

**증상**: "timeout" 또는 "timeout exceeded" 오류

**진단:**
```bash
# 1. executor 응답 시간 확인
time curl -X POST http://file-map-executor:8510/cleanup/execute ...

# 2. 로그에서 처리 시간 확인
docker compose logs file-map-executor

# 3. 네트워크 지연 확인
docker network inspect app_web
docker stats file-map-executor admin-web  # CPU/메모리 사용량
```

**해결:**
- timeout 값 증가 (현재 30초)
- executor service 최적화
- 네트워크/호스트 리소스 확인

---

## 성공 기준

**최종 PASS 조건:**

✅ **모든 체크리스트 항목이 PASS인 경우:**

1. 서비스 health: admin-web과 file-map-executor 모두 healthy
2. HTTP 통신: admin-web이 file-map-executor에 정상 접근
3. API 응답: 200 OK, 정상 JSON 응답 (ok=true, run_id 포함)
4. 파일 무결성: dry_run 정책 준수 (파일 미변경)
5. 로깅: ERROR/500 없음
6. (선택) 로드 테스트: 5개 요청 모두 성공

**결론:**
```
EXECUTOR-SERVICE-2E: ✅ PASS (최종 검증 완료)

HTTP 마이크로서비스 아키텍처 전환 완료
- admin-web: spawn 기반 → HTTP client 기반
- file-map-executor: 독립 FastAPI service
- 통합 테스트: ✅ PASS
- 서버 배포: ✅ PASS
- 프로덕션 준비: ✅ READY
```

---

## 다음 단계

**배포 완료 후:**

1. **Monitoring 설정**
   - file-map-executor 메트릭 수집
   - admin-web → executor 응답 시간 모니터링
   - 오류율 추적

2. **Logging 수집**
   - ELK stack 또는 CloudWatch 통합
   - audit 로그 보관
   - 성능 로그 분석

3. **Documentation 업데이트**
   - deployment runbook 작성
   - troubleshooting guide 작성
   - API documentation 업데이트

4. **Rollout Plan (필요시)**
   - 카나리 배포 (일부 사용자만)
   - 블루-그린 배포 (이중 환경)
   - Feature flag로 단계적 활성화

---

## 참고자료

### 관련 코드

- admin-web/src/app/api/file-map/cleanup-execute/route.ts (API endpoint)
- admin-web/src/lib/file-map/pythonExecutor.ts (HTTP client)
- services/file_map_executor/app.py (executor service)
- services/file_map_executor/security.py (validation)

### 관련 보고서

- local_file_map_executor_service_2a_skeleton.md
- local_file_map_executor_service_2b_admin_web_client.md
- local_file_map_executor_service_2c_integration_test.md
- local_file_map_executor_service_2d_deployment_prep.md

### 서버 정보

- SSH: haehan-app
- Runtime: /home/ubuntu/apps/haehan-ai-orchestrator
- Branch: feature/dashboard-monitor
- Service: ai-orchestrator-api

---

**사용자 작성 예상**

이 보고서는 **사용자가 배포 후 실행하여 결과를 작성**해야 합니다.

```bash
# 검증 실행 후 결과를 이 보고서에 기록:
# 1. 각 단계의 체크리스트 완료 표시
# 2. 발생한 문제 기록
# 3. 최종 PASS/FAIL 판정
# 4. 타임스탬프 업데이트
```

---

**작성자**: Claude Haiku 4.5 (Template)  
**예상 완료**: 사용자가 배포 후 실행  
**최종 수정**: 2026-05-03 20:45:00
