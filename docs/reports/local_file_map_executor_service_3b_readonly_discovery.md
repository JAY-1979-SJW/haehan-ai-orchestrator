# LOCAL-FILE-MAP-EXECUTOR-SERVICE-3B-READONLY-DISCOVERY — 서버 Docker smoke 실행 가능 여부 read-only 조사

**조사 일시**: 2026-05-03  
**조사 대상**: haehan-app 서버  
**조사 방식**: read-only (실행/build/수정 금지)  
**기준선**: 7f43206 (로컬/서버 완전 동기화)

## 작업 내용

haehan-app 서버에서 Docker smoke 실행 가능 여부를 read-only로 조사.
Docker daemon, compose, 기존 컨테이너, 신규 compose fragment, 운영 영향을 분석하여
smoke 실행 가능 판정.

## 기준선

**로컬**:
```
branch: master
HEAD: 7f43206
origin/master: 7f43206
status: clean ✓
```

**서버**:
```
branch: master
HEAD: 7f43206
origin/master: 7f43206
status: clean ✓
```

**평가**: 로컬/서버 완전 동기화 ✓

## Docker 상태

### docker version
```
Client: 28.2.2
Server: 28.2.2
containerd: 1.7.28
runc: 1.3.3

평가: Docker daemon 정상 작동 ✓
```

### docker compose version
```
Version: v5.1.0

평가: Docker compose 사용 가능 ✓
```

## 실행 중 컨테이너 요약

### 총 컨테이너 수
51개 (다양한 microservices 운영 중)

### haehan-ai-orchestrator 컨테이너
```
1. haehan-ai-orchestrator-admin-web
   Status: Up 23 hours
   Port: 3000/tcp

2. haehan-ai-orchestrator-api
   Status: Up 24 hours (healthy)
   Port: 127.0.0.1:8400->8400/tcp

3. haehan-ai-orchestrator-browser-worker
   Status: Up 2 days (healthy)
   Port: 8500/tcp

4. file-map-executor
   Status: NOT FOUND (아직 없음)
```

### 운영 현황
- nginx: Up 11 days (포트 80, 443 외부 공개)
- 다수의 microservices: 정상 운영
- 포트 충돌 위험: 없음

## Compose/Dockerfile 상태

### 존재 확인
```
✓ docker/docker-compose.dev.yml
✓ docker/docker-compose.file-map-executor.yml
✓ docker/file-map-executor.Dockerfile
✓ docker-compose.yml (root)
```

### file-map-executor Dockerfile
```
파일: docker/file-map-executor.Dockerfile

내용:
  - base: python:3.11-slim ✓
  - working_dir: /app ✓
  - ENV PORT=8510 ✓
  - EXPOSE 8510 ✓
  - HEALTHCHECK: /health endpoint ✓
  - CMD: uvicorn app 실행 ✓

평가: 완성도 높음 ✓
```

### file-map-executor Compose Fragment
```
파일: docker/docker-compose.file-map-executor.yml

내용:
  - service: file-map-executor ✓
  - build: context=.., dockerfile=docker/file-map-executor.Dockerfile ✓
  - image: haehan-ai-orchestrator-file-map-executor:local ✓
  - container_name: haehan-ai-orchestrator-file-map-executor ✓
  - expose: 8510 (host port mapping 없음) ✓
  - networks: default, app_web ✓
  - app_web: external=true (기존 network 참조) ✓
  - healthcheck: 30s interval, 3s timeout ✓
  - restart: unless-stopped ✓

설계:
  - 포트: 내부 통신만 (host 공개 없음)
  - 네트워크: 기존 app_web 네트워크 사용
  - 독립성: 기존 컨테이너와 완전 분리

평가: isolated smoke 설계 완벽 ✓
```

### dev compose
```
파일: docker/docker-compose.dev.yml

내용:
  - admin-web + file-map-executor 함께 실행
  - FILE_MAP_EXECUTOR_URL: http://file-map-executor:8510 설정 ✓
  - 로컬 개발/테스트용

평가: 통합 테스트 가능 ✓
```

## 네트워크 상태

### app_web network
```
NETWORK ID: 40f2032ab439
DRIVER: bridge
SCOPE: local

평가: 존재함 ✓
구성원: admin-web, browser-worker, 신규 file-map-executor 연결 가능
```

### Network 충돌
```
- app_web: 기존 network (admin-web, browser-worker 이미 사용 중)
- docker-compose.file-map-executor.yml: app_web을 external=true로 참조
- 충돌 위험: 없음 ✓
```

## file-map-executor 준비 상태

### 코드 준비
```
✓ services/file_map_executor/ directory 존재
✓ app.py, schemas.py, service.py 구현됨
✓ FastAPI 기반 RESTful API
✓ healthcheck endpoint 구현
```

### Image 준비
```
상태: 빌드 필요
사유: docker ps에 file-map-executor 컨테이너 없음
      docker images에 file-map-executor image 없음
      
처음 사용 시: docker compose ... --build 필요
```

### 환경 설정
```
admin-web:
  - FILE_MAP_EXECUTOR_URL: http://file-map-executor:8510
  - docker/docker-compose.dev.yml에 정의됨
  - docker/docker-compose.file-map-executor.yml에서 서비스 제공

설정 방식:
  - admin-web Dockerfile에 ENV로 정의 또는
  - 운영 compose에서 environment로 주입

현재: dev compose에만 설정, 운영 compose 반영 필요
```

## 운영 영향 가능성

### 기존 운영 환경
```
- nginx (포트 80, 443): 외부 공개, 11일간 안정
- admin-web (포트 3000): 23시간, healthy
- api (포트 8400): 24시간, healthy
- browser-worker (포트 8500): 2일, healthy
- 다수의 microservices: 정상
```

### 신규 추가 시 영향 분석

**포트 충돌**:
  - file-map-executor: 포트 8510 (expose only, no host mapping)
  - 기존 포트: 3000, 8400, 8500, 80, 443, 등
  - 충돌 위험: 없음 ✓

**네트워크 충돌**:
  - app_web: bridge network (기존, admin-web/browser-worker 사용 중)
  - file-map-executor: app_web에 연결 (external=true 참조)
  - 충돌 위험: 없음 ✓

**admin-web 영향**:
  - FILE_MAP_EXECUTOR_URL 환경변수 필요
  - admin-web Dockerfile 수정 필요 또는 환경변수 주입
  - admin-web rebuild 필요
  - admin-web restart 필요
  - 기능: FILE_MAP_EXECUTOR_URL 설정 후 내부 HTTP client로 통신 예정

**운영 compose 영향**:
  - 현재: docker-compose.yml에 admin-web, api, browser-worker만 정의
  - 필요: docker/docker-compose.file-map-executor.yml fragment 추가
  - 명령: docker compose -f docker-compose.yml -f docker/docker-compose.file-map-executor.yml up
  - 또는 docker-compose.yml에 file-map-executor service 직접 추가

**기존 컨테이너 영향**:
  - api, admin-web, browser-worker: 영향 없음
  - 신규 service는 isolated, 기존 service와 독립적

### 판정: 운영 영향 있음, 배포 승인 필요

**사유**:
1. admin-web rebuild/restart 필수
2. 운영 docker-compose.yml 반영 필수
3. FILE_MAP_EXECUTOR_URL 환경변수 설정 필수
4. 기존 운영 컨테이너는 영향 없지만, 배포 절차 필요

## smoke 실행 가능 판정

### 현황 요약
```
서버 repo 기준선: 7f43206 (clean) ✓
Docker daemon: 정상 ✓
docker compose: v5.1.0 ✓
Dockerfile: 완성 ✓
Compose fragment: 완성 ✓
Network: app_web 존재 ✓
이미지: 빌드 필요 (처음)
운영 설정: 배포 승인 필요
```

### 판정: **NEED_DEPLOY_APPROVAL**

**근거**:
- 기술적으로 smoke 가능한 수준 (READY)
- 그러나 운영 배포 단계에서 승인 필요
  - admin-web rebuild/restart
  - 운영 docker-compose.yml 반영
  - 환경변수 주입

### 판정 등급
```
기술 준비도: READY ✓
배포 준비도: NEEDS_APPROVAL (admin-web rebuild/restart 필요)
최종 판정: NEED_DEPLOY_APPROVAL
```

## 다음 단계 제안

### Option A: Docker smoke 즉시 테스트 (로컬)
```
장점: admin-web rebuild 없이 빠른 테스트 가능
방식: 로컬 docker compose dev.yml 사용
대상: local 개발 환경에서 smoke 실행
요구: 로컬 Docker (현재 없으므로 불가)
```

### Option B: 서버 배포 + Docker smoke (권장)
```
단계:
1. admin-web에 FILE_MAP_EXECUTOR_URL 환경변수 추가
2. 운영 docker-compose.yml에 file-map-executor service 추가
3. admin-web rebuild (docker compose build admin-web)
4. admin-web restart (docker compose restart admin-web)
5. file-map-executor up (docker compose ... up -d file-map-executor)
6. smoke 테스트
7. 모든 service down 또는 유지 여부 결정

요구: 배포 승인
위험도: 낮음 (isolated service, 기존 영향 없음)
```

### Option C: 운영 추가 후 나중에 smoke
```
단계:
1. admin-web/file-map-executor 운영 배포
2. 이후 원하는 시점에 smoke 테스트

요구: 배포 승인
```

## 생성 보고서

- `docs/reports/local_file_map_executor_service_3b_readonly_discovery.md` (본 파일)

## 최종 판정

| 항목 | 상태 |
|------|------|
| 서버 기준선 | PASS (7f43206, clean) |
| Docker 상태 | PASS (daemon, compose 정상) |
| Dockerfile | PASS (완성) |
| Compose fragment | PASS (완성) |
| Network | PASS (app_web 존재) |
| 기술 준비도 | PASS |
| 운영 영향 | WARN (rebuild/restart 필요) |
| **전체 판정** | **WARN** |

### 판정 근거
- 기술적으로 smoke 실행 가능한 상태
- 그러나 운영 배포 단계에서 admin-web rebuild/restart 필수
- 별도 배포 승인 필요

## 최종 보고

**조사 결과**: read-only 조사 완료, 운영 배포 승인 필요

**smoke 실행 가능 판정**: **NEED_DEPLOY_APPROVAL**

**다음 단계**:
1. EXECUTOR-SERVICE-DEPLOY-1: admin-web rebuild/restart + file-map-executor service 추가 (승인형)
2. EXECUTOR-SERVICE-3C-SMOKE-TEST: Docker smoke 실행 (3B 후속)

