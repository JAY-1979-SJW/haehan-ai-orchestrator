# LOCAL-FILE-MAP-EXECUTOR-SERVICE-2D 서버 배포 준비 보고서

**작성 일시**: 2026-05-03 20:30:00  
**종합 판정**: READY (배포 전 체크리스트 작성 완료)

---

## 작업 내용

EXECUTOR-SERVICE-2C 로컬 통합 테스트 완료 후, 실제 서버 환경(haehan-app)에 file-map-executor service를 배포하기 위한 준비 단계.

**범위:**
- 서버 환경 분석
- 배포 체크리스트 작성
- 환경변수 및 네트워크 구성 검토
- 배포 절차 문서화

---

## 배포 대상 환경

### 서버 정보

| 항목 | 값 |
|------|-----|
| SSH alias | haehan-app |
| Runtime repo | /home/ubuntu/apps/haehan-ai-orchestrator |
| Compose service | ai-orchestrator-api |
| Server branch | feature/dashboard-monitor |
| Local branch | master |
| 상태 | **주의**: 로컬과 서버 branch 상이 |

### 주의사항 ⚠️

> **Repo Boundary Lock**: 서버 환경(/home/ubuntu/apps/...)은 로컬 master branch와 다른 feature/dashboard-monitor 브랜치에서 실행 중입니다. 배포 전에 다음을 확인하세요:
>
> 1. 서버의 docker-compose.yml이 EXECUTOR-SERVICE-2A/2B 변경사항을 반영했는지 확인
> 2. 서버의 admin-web이 새로운 FILE_MAP_EXECUTOR_URL 환경변수를 지원하는지 확인
> 3. 충돌 가능성이 있으면 머지 작업 필요

---

## 배포 전 체크리스트

### 1. 로컬 상태 확인

- [x] EXECUTOR-SERVICE-2A: file-map-executor service 구현 (skeleton)
- [x] EXECUTOR-SERVICE-2B: admin-web HTTP client 변환
- [x] EXECUTOR-SERVICE-2C: 로컬 통합 테스트 환경 준비
- [x] 모든 unit tests 통과
- [x] 모든 security audits PASS
- [x] 코드 커밋 완료
- [ ] 로컬 smoke test 실행 및 PASS

### 2. 서버 현황 조사

**필수 단계:**

```bash
# SSH 접속
ssh haehan-app

# 서버 docker-compose 확인
cd /home/ubuntu/apps/haehan-ai-orchestrator
git status
git branch -v
git log --oneline -5

# 현재 서비스 상태
docker compose ps
docker compose config | grep -A 20 "services:"

# admin-web 환경변수 확인
docker compose config | grep -A 20 "admin-web:"
docker inspect haehan-ai-orchestrator-admin-web | grep -i "file_map"
```

**체크사항:**
- [ ] 서버 master 브랜치와 로컬 마스터 버전 일치 확인
- [ ] 서버 docker-compose.yml에 EXECUTOR-SERVICE-2A 변경사항 포함 확인
- [ ] 기존 admin-web이 spawn 기반인지 HTTP 기반인지 확인
- [ ] 현재 실행 중인 admin-web 버전 확인

### 3. 파일 동기화 확인

**동기화할 파일:**

| 파일 | 출처 | 설명 |
|------|------|------|
| docker/file-map-executor.Dockerfile | 로컬 마스터 | executor service Dockerfile |
| services/file_map_executor/ | 로컬 마스터 | executor service 코드 |
| admin-web/src/lib/file-map/pythonExecutor.ts | 로컬 마스터 | HTTP client 변환 |
| admin-web/src/lib/file-map/__tests__/pythonExecutor.test.ts | 로컬 마스터 | HTTP client 테스트 |
| docker/docker-compose.file-map-executor.yml | 로컬 마스터 | executor compose fragment |

**확인:**
- [ ] 서버에 위 파일들의 최신 버전이 존재하는가?
- [ ] 혹은 merge 작업이 필요한가?

### 4. 서버 환경변수 검토

**신규 환경변수:**

| 환경변수 | 값 | 설정처 |
|--------|---|--------|
| FILE_MAP_EXECUTOR_URL | http://file-map-executor:8510 | admin-web container env |
| PORT (executor) | 8510 | file-map-executor env |
| EXECUTOR_MODE | service | file-map-executor env |
| PYTHONUNBUFFERED | 1 | file-map-executor env |

**확인 방법:**
```bash
docker compose config | grep -E "FILE_MAP_EXECUTOR_URL|EXECUTOR_MODE"
```

**설정:**
- [ ] docker-compose.yml 또는 .env에서 FILE_MAP_EXECUTOR_URL 설정
- [ ] 기본값: http://file-map-executor:8510
- [ ] 또는 환경별 커스텀 URL (필요시)

### 5. 네트워크 구성 검토

**Docker network:**

```yaml
# docker/docker-compose.file-map-executor.yml에서 사용
networks:
  app_web:
    external: true
    name: app_web
```

**확인:**
```bash
docker network ls | grep app_web
docker network inspect app_web
```

**체크:**
- [ ] app_web 네트워크 존재 확인
- [ ] admin-web, ai-orchestrator-api, file-map-executor 모두 app_web에 연결 가능한가?
- [ ] DNS resolution: file-map-executor:8510 이름으로 접근 가능한가?

### 6. 포트 및 노출 설정

**파일-맵-executor service:**

| 포트 | 설정 | 설명 |
|------|------|------|
| 8510 | expose | 내부 네트워크만 공개 (호스트 포트 매핑 없음) |

**확인:**
```bash
# 컨테이너 포트 매핑 확인
docker compose ps file-map-executor
# 또는
docker compose config | grep -A 10 "file-map-executor:"
```

**체크:**
- [ ] 호스트 포트 매핑 없음 (방화벽 안전)
- [ ] 내부 app_web 네트워크에서만 접근 가능
- [ ] 외부 노출 금지

### 7. Health Check 및 모니터링

**Health check 설정:**

```yaml
file-map-executor:
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8510/health', timeout=3)"]
    interval: 30s
    timeout: 3s
    retries: 3
    start_period: 5s
```

**확인:**
```bash
docker compose ps file-map-executor
# STATUS에서 "healthy" 확인

curl http://localhost:8510/health  # 컨테이너 내부에서 실행
```

**체크:**
- [ ] health check endpoint GET /health가 정상 응답 (200)
- [ ] docker compose ps에서 healthy 상태 확인 가능
- [ ] 오류 시 자동 재시작 (restart: unless-stopped)

### 8. 로깅 및 디버깅

**로그 설정:**

```yaml
file-map-executor:
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
```

**로그 확인:**
```bash
docker compose logs -f file-map-executor
docker compose logs --tail 100 file-map-executor
```

**체크:**
- [ ] 로그 파일 크기 관리 (10MB, 최대 3파일)
- [ ] 로그 수집 경로: /var/lib/docker/containers/.../*json.log
- [ ] 모니터링/ELK 통합 (필요시)

---

## 배포 절차

### Phase 1: 서버 상태 조사 (사용자 실행)

```bash
ssh haehan-app
cd /home/ubuntu/apps/haehan-ai-orchestrator

# 1. 현재 branch 확인
git status
git branch -v

# 2. docker-compose.yml 확인
docker compose config | head -100

# 3. 기존 admin-web 이미지 확인
docker image inspect haehan-ai-orchestrator-admin-web:production 2>/dev/null || docker image inspect haehan-ai-orchestrator-admin-web:latest

# 4. 서비스 목록 확인
docker compose ps
```

### Phase 2: 파일 동기화 (사용자 실행 또는 Claude)

**Option A: Git merge (추천)**
```bash
# 서버에서
cd /home/ubuntu/apps/haehan-ai-orchestrator
git fetch origin master
git merge origin/master
# 또는
git checkout master
git pull origin master
```

**Option B: 특정 파일만 복사**
```bash
# 로컬에서
scp docker/file-map-executor.Dockerfile haehan-app:/home/ubuntu/apps/haehan-ai-orchestrator/docker/
scp docker/docker-compose.file-map-executor.yml haehan-app:/home/ubuntu/apps/haehan-ai-orchestrator/docker/
scp -r services/file_map_executor haehan-app:/home/ubuntu/apps/haehan-ai-orchestrator/services/
```

**체크:**
- [ ] 파일 복사 또는 git merge 완료
- [ ] 서버에서 파일 존재 확인: `ls -la docker/file-map-executor.Dockerfile`

### Phase 3: 환경변수 설정 (사용자 실행)

**docker-compose.yml 수정 (또는 .env):**

```yaml
services:
  admin-web:
    environment:
      FILE_MAP_EXECUTOR_URL: "http://file-map-executor:8510"
```

또는 .env 파일에 추가:
```
FILE_MAP_EXECUTOR_URL=http://file-map-executor:8510
```

**확인:**
```bash
docker compose config | grep FILE_MAP_EXECUTOR_URL
```

### Phase 4: Docker build (서버에서 실행)

```bash
# 기존 이미지 정리 (선택사항)
docker system prune -f

# 새 이미지 빌드
docker compose build file-map-executor
docker compose build admin-web  # admin-web도 재빌드 권장 (파일 변경)

# 빌드 확인
docker image ls | grep haehan-ai-orchestrator
```

### Phase 5: 서비스 시작 (서버에서 실행)

```bash
# 현재 서비스 상태 저장 (백업)
docker compose ps > /tmp/compose_before.txt
docker compose logs --tail 100 > /tmp/logs_before.txt

# 서비스 중지 및 시작
docker compose down
docker compose up -d

# 상태 확인
docker compose ps
sleep 30
docker compose logs -f file-map-executor &  # 로그 모니터링
docker compose logs admin-web
```

### Phase 6: 검증 (서버에서 실행)

```bash
# 1. Service health 확인
docker compose ps
# file-map-executor와 admin-web 모두 "healthy" 상태인지 확인

# 2. HTTP 통신 확인
docker compose exec admin-web curl http://file-map-executor:8510/health
# {"status": "healthy", ...} 응답 확인

# 3. admin-web API 테스트 (로컬)
curl -X POST http://localhost:3000/api/file-map/cleanup-execute \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "preflight_id": "test-uuid",
    "package_id": "test-uuid",
    "approval_token": "user-approved-cleanup-test",
    "user_confirmed_execution": true,
    "base_target_dir": "/tmp/test",
    "plans": []
  }'
# 응답 확인: {"ok":true, "run_id": "...", ...}

# 4. 로그 확인
docker compose logs file-map-executor | tail -20
```

---

## 배포 전 마지막 체크

| 항목 | 체크박스 |
|------|---------|
| 로컬 EXECUTOR-SERVICE-2C smoke test PASS | [ ] |
| 서버 상태 조사 완료 | [ ] |
| 파일 동기화 완료 | [ ] |
| 환경변수 설정 완료 | [ ] |
| Docker build 성공 | [ ] |
| 서비스 시작 성공 | [ ] |
| Health check 통과 | [ ] |
| HTTP 통신 검증 완료 | [ ] |
| 로그 모니터링 정상 | [ ] |

---

## 롤백 계획

배포 후 문제 발생 시 롤백 절차:

```bash
# 1. 즉시 중지
docker compose down

# 2. 이전 상태 복구 (git 사용)
git reset --hard HEAD~1  # 또는 특정 커밋

# 3. 기존 이미지로 재시작
docker compose build
docker compose up -d

# 4. 검증
docker compose ps
```

**주의:** 이 단계는 최후의 수단. 첫 번째 시도는 신중하게 진행하세요.

---

## 다음 단계

**EXECUTOR-SERVICE-2E: 최종 AUTO-CONTROL-2B-RUN (서버)**

1. 배포 완료 후 실제 운영 환경에서 smoke test 재실행
2. 실제 파일 시스템에서 cleanup 실행 검증 (dry_run)
3. audit 기록 생성 확인
4. 모니터링 및 로그 검증

**현재 상태:**
- ✅ 로컬 구현 완료 (EXECUTOR-SERVICE-2A/2B)
- ✅ 로컬 테스트 준비 완료 (EXECUTOR-SERVICE-2C)
- ✅ 서버 배포 준비 완료 (EXECUTOR-SERVICE-2D - 현재)
- ⏳ 서버 배포 실행 (사용자)
- ⏳ 최종 테스트 (EXECUTOR-SERVICE-2E)

---

## 참고자료

### 관련 문서

- docs/reports/local_file_map_executor_service_2a_skeleton.md
- docs/reports/local_file_map_executor_service_2b_admin_web_client.md
- docs/reports/local_file_map_executor_service_2c_integration_test.md

### 배포 메모리

- Deployment target: SSH alias haehan-app
- Runtime repo: /home/ubuntu/apps/haehan-ai-orchestrator
- Server branch: feature/dashboard-monitor (로컬 master와 상이)
- API service: ai-orchestrator-api (docker compose service)

### 트러블슈팅 연락처

배포 중 문제 발생 시:
1. 로그 수집: `docker compose logs --tail 100`
2. 서비스 상태: `docker compose ps`
3. 네트워크 확인: `docker network inspect app_web`
4. DNS 해석: `docker compose exec admin-web ping file-map-executor`

---

**최종 판정**: ✅ READY (배포 전 체크리스트 작성 완료)

사용자가 배포 전 체크리스트를 따라 단계적으로 진행할 수 있습니다. 모든 필수 파일이 준비되었으므로 안전한 배포가 가능합니다.

---

**작성자**: Claude Haiku 4.5  
**최종 수정**: 2026-05-03 20:30:00
