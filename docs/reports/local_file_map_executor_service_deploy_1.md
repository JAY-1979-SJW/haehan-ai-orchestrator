# LOCAL-FILE-MAP-EXECUTOR-SERVICE-DEPLOY-1 — file-map-executor 서버 배포

**작업 일시**: 2026-05-03  
**작업 단계**: 배포 승인형  
**기준선**: cf05c9f (로컬/서버 완전 동기화)

## 작업 내용

docker-compose.yml에 file-map-executor service를 추가하고, admin-web에 FILE_MAP_EXECUTOR_URL 환경변수를 설정하여 서버 배포를 준비하는 단계.

## 기준선

**로컬**:
```
branch: master
HEAD: cf05c9f
origin/master: cf05c9f
status: clean ✓
```

**서버**:
```
branch: master
HEAD: cf05c9f
origin/master: cf05c9f
status: clean ✓
```

**평가**: 로컬/서버 완전 동기화 ✓

## compose 변경 내용

### 수정 파일
- `docker-compose.yml`

### 변경 사항

#### 1. admin-web environment 추가
```yaml
environment:
  NODE_ENV: production
  FILE_MAP_EXECUTOR_URL: "http://file-map-executor:8510"
```

#### 2. admin-web depends_on 추가
```yaml
depends_on:
  ai-orchestrator-api:
    condition: service_healthy
  file-map-executor:
    condition: service_healthy
```

#### 3. file-map-executor service 신규 추가
```yaml
file-map-executor:
  build:
    context: .
    dockerfile: docker/file-map-executor.Dockerfile
  image: haehan-ai-orchestrator-file-map-executor:local
  container_name: haehan-ai-orchestrator-file-map-executor
  working_dir: /app
  expose:
    - "8510"
  environment:
    PYTHONUNBUFFERED: "1"
    PORT: "8510"
    EXECUTOR_MODE: "service"
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8510/health',timeout=3).status==200 else 1)"]
    interval: 30s
    timeout: 3s
    retries: 3
    start_period: 5s
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
  networks:
    - default
    - app_web
```

### 설계 원칙
- ✓ host port publish 없음 (expose 8510만)
- ✓ app_web network 연결
- ✓ restart: unless-stopped (기존 기준)
- ✓ healthcheck 정의
- ✗ dry_run=false 허용 설정 없음
- ✗ 실제 사용자 경로 mount 없음

## YAML 검증

```
✓ YAML 구문: PASS
✓ file-map-executor 서비스: 포함
✓ admin-web FILE_MAP_EXECUTOR_URL: [SET]
✓ host port 8510 publish: 없음
✓ app_web network external: True
```

## 최종 판정 (Step 6 완료)

**상태: 승인 대기 중**

compose 설정 준비 완료. Step 7에서 사용자 승인 확인 후 Step 8부터 실제 서버 배포 진행 예정.

