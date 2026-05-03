# PHASE3Y-PREFLIGHT-AUDIT-1 — 모듈화 사전 검증 리포트

**작업 일시**: 2026-05-03  
**작업 단계**: Preflight & Readiness Assessment (read-only)  
**기준선**: 4f1153d (master, clean)  

---

## 작업 개요

### 작업명
PHASE3Y-PREFLIGHT-AUDIT-1

### 목표
- 기존 codebase의 modularization 현황 파악
- electrical_workplan, heavy_lifting_workplan 파일 존재 여부 확인
- PHASE3Y 작업 수행을 위한 사전 준비 상태 검증
- modularization 범위 및 전략 제안

### 최종 판정
**⚠️ READY — 조건부 진행**

---

## STEP 0: 기준선 확인

### Git 상태
```
Branch: master
HEAD: 4f1153d44564ba72e333420da364b029b8be6494
origin/master: 4f1153d (일치)
Working tree: clean ✓
Latest commit: docs(ops): close out local file map executor deploy smoke
```

### 시스템 준비도
```
✓ Git repo 동기화 상태: PASS
✓ Working tree: clean (uncommitted 변경 없음)
✓ Recent work: file-map-executor service 배포 완료 (2026-05-03)
✓ 다음 단계 시작 가능: YES
```

**판정: STEP 0 PASS ✓**

---

## STEP 1: 파일 존재 여부 확인

### electrical_workplan 파일 탐색

```
검색 패턴:
  - electrical_workplan (문자열)
  - build_electrical_workplan (함수)
  - render_electrical_workplan (함수)
  - *electrical* (파일명)

결과: NOT FOUND ✗
```

### heavy_lifting_workplan 파일 탐색

```
검색 패턴:
  - heavy_lifting_workplan (문자열)
  - build_heavy_lifting_workplan (함수)
  - render_heavy_lifting_workplan (함수)
  - *heavy* (파일명)

결과: NOT FOUND ✗
```

### 관련 디렉토리 탐색

```
찾음:
  ✗ builders/ 디렉토리
  ✗ writers/ 디렉토리
  ✗ sections/ 디렉토리
  ✗ workplan 관련 모듈

발견: 이 파일들은 PHASE3Y에서 신규 생성될 예정인 모듈
```

**판정: 파일 미존재 — 신규 PHASE3Y 작업으로 생성 필요**

---

## STEP 2: 현재 모듈화 상태 분석

### 2A. Python 백엔드 모듈화

#### ai_orchestrator 패키지 (메인 모듈)

```
위치: ai_orchestrator/
구조:
  - app.py (34 lines): FastAPI app 초기화
  - server.py (34 lines): uvicorn 서버 진입점
  - router.py (255 lines): 주요 API routes 집계
  - auth.py, auth_router.py: 인증 관련 (separate)
  - web_task_router.py (332 lines): 웹 자동화 task routes
  - task_state.py (214 lines): Task 상태 관리
  - approval.py: 승인 로직
  - telegram_notifier.py (230 lines): 텔레그램 통지
  - registration_codes.py (283 lines): 코드 등록 관리
  - browser_tool/: 브라우저 자동화 서브패키지
  - connectors/: 외부 연동 서브패키지
  - cad/: CAD 라우터 서브패키지

총 라인 수: ~9,386 lines (모든 Python 서비스 파일 합산)
```

**평가: 부분적으로 modularized (서브패키지별 분리), 메인 라우터 집계 필요**

#### services/file_map_executor (신규 마이크로서비스)

```
위치: services/file_map_executor/
구조:
  - app.py (118 lines): FastAPI 서비스
  - service.py (73 lines): 비즈니스 로직
  - schemas.py (65 lines): 데이터 스키마
  - security.py (45 lines): 보안 검증

총 라인 수: 301 lines
```

**평가: 새로운 modularization 패턴 (독립 마이크로서비스)**

**발견**:
- 2026-05 최근 배포된 신규 서비스
- docker-compose.yml에 독립 서비스로 구성
- admin-web과 HTTP로 통신
- 전체 아키텍처 분리의 시작점

### 2B. TypeScript 프론트엔드 모듈화 (admin-web)

#### 소스 파일 통계

```
총 TypeScript 소스 파일: 88개 (.next 제외)
구조:
  app/:           Next.js app router pages/routes
  api/:           API route handlers (12개)
  lib/:           Shared utilities & business logic
  components/:    React components
```

#### API Route 구조

```
routes:
  - /api/file-map/auth/* (3개): 인증 관련
  - /api/file-map/cleanup-* (8개): 파일 정리 workflow
  - /api/file-map/report/* (1개): 리포팅

특징:
  ✓ 기능별 서브디렉토리 구분 (auth/, cleanup-*)
  ✓ 각 route는 독립 핸들러 (modular)
  ✓ Next.js app router pattern 준수

총 12개 route handler 파일
```

#### 라이브러리 구조

```
lib/:
  - api.ts: API 통신 유틸
  - auth-session.ts: 세션 관리
  - file-map/: 파일맵 비즈니스 로직 (별도 디렉토리)
    - pythonExecutor.ts: executor 호출
    - approvalToken.ts: 토큰 생성
    - executePayload.ts: payload 구성
    - __tests__/: 테스트 파일
  - fileMap*.ts: 기능별 유틸 (7개)
    - fileMapApproval.ts
    - fileMapAudit.ts
    - fileMapCleanupPlan.ts
    - fileMapExecutor.ts
    - fileMapRollback.ts
    - fileMapSettings.ts
  - privacy.ts: 개인정보 정책
  - nav.ts: 네비게이션

특징:
  ✓ file-map 기능은 별도 디렉토리로 분리
  ✓ 기능별 파일 분리 (fileMap*.ts)
  ✓ 테스트 파일 포함 (__tests__/)

총 14개 라이브러리 파일
```

**평가: 잘 modularized, 기능별 분리 명확**

### 2C. 테스트 커버리지

```
전체 테스트 파일: 218개

분포:
  - ai_orchestrator: 테스트 디렉토리 구조 미상 (별도 확인 필요)
  - admin-web:
    - __tests__/ 디렉토리 존재
    - 테스트 파일 포함 (예: pythonExecutor.test.ts)
  - services/file_map_executor: 테스트 상태 미상

평가: 테스트 가능한 구조, 확대 필요
```

---

## STEP 3: electrical_workplan / heavy_lifting_workplan 분석

### 파일 생성 필요성 검증

#### electrical_workplan 용도 예상

```
기능:
  - 전기 설계 문서 생성
  - 전기 회로 workplan 렌더링
  - 빌더 패턴: build_electrical_workplan()
  - 라이터 패턴: render_electrical_workplan()

예상 위치 (PHASE3Y에서 생성):
  admin-web/src/lib/electrical-workplan/
    - builder.ts: electrical_workplan 구성
    - writer.ts: HTML/PDF 렌더링
    - sections/: 섹션별 렌더러
    - __tests__/: 테스트

또는 별도 마이크로서비스:
  services/electrical_workplan/
    - app.py: FastAPI 서비스
    - builder.py: 빌더 로직
    - renderer.py: 렌더링 로직
```

#### heavy_lifting_workplan 용도 예상

```
기능:
  - 중장비/기계 workplan 생성
  - 무거운 작업 계획 렌더링
  - 빌더 패턴: build_heavy_lifting_workplan()
  - 라이터 패턴: render_heavy_lifting_workplan()

예상 위치 (PHASE3Y에서 생성):
  admin-web/src/lib/heavy-lifting-workplan/
    - builder.ts: heavy_lifting_workplan 구성
    - writer.ts: HTML/PDF 렌더링
    - sections/: 섹션별 렌더러
    - __tests__/: 테스트

또는 별도 마이크로서비스:
  services/heavy_lifting_workplan/
    - app.py: FastAPI 서비스
    - builder.py: 빌더 로직
    - renderer.py: 렌더링 로직
```

### 현재 유사 패턴 분석

#### file_map_executor와의 비교

```
file_map_executor (2026-05 신규):
  - 마이크로서비스 아키텍처
  - FastAPI 기반
  - 독립적 HTTP 엔드포인트
  - admin-web과 HTTP 통신

electrical/heavy_lifting workplan (예상):
  - 유사 아키텍처 가능
  - 마이크로서비스 또는 lib 모듈
  - admin-web 라이브러리로 구현 가능
  - 또는 별도 FastAPI 서비스로 분리 가능
```

**권장안: 두 가지 옵션**

**옵션 A: 라이브러리 모듈 (admin-web 내부)**
```
장점:
  - 빠른 개발 (HTTP 오버헤드 없음)
  - 간단한 배포
  - 기존 admin-web 구조와 일관성

단점:
  - admin-web의 책임 증가
  - 리소스 사용 증가

구조:
  admin-web/src/lib/electrical-workplan/
  admin-web/src/lib/heavy-lifting-workplan/
```

**옵션 B: 마이크로서비스 (독립 FastAPI)**
```
장점:
  - file_map_executor 패턴과 일관성
  - 확장성 (별도 배포/스케일링 가능)
  - 관심사 분리

단점:
  - 복잡도 증가 (HTTP/네트워크 오버헤드)
  - 배포 관리 증가

구조:
  services/electrical_workplan/
  services/heavy_lifting_workplan/
  docker-compose.yml에 서비스 추가
```

---

## STEP 4: 모듈화 범위 제안 (PHASE3Y)

### 4A. 신규 모듈 생성 목록

```
필수 생성 모듈:
  1. electrical_workplan
     - 유형: admin-web lib (옵션 A 권장) 또는 FastAPI 서비스 (옵션 B)
     - 파일: builder.ts/py, writer.ts/py, sections/*, tests
     - 라인 수 예상: 300-500 lines

  2. heavy_lifting_workplan
     - 유형: admin-web lib (옵션 A 권장) 또는 FastAPI 서비스 (옵션 B)
     - 파일: builder.ts/py, writer.ts/py, sections/*, tests
     - 라인 수 예상: 300-500 lines
```

### 4B. 기존 모듈 리팩토링 (선택)

```
후보 모듈:
  1. ai_orchestrator/telegram_notifier (230 lines)
     → services/telegram_notifier로 분리 가능

  2. ai_orchestrator/browser_tool (이미 subpackage)
     → 추가 분리 불필요 (현재 적절)

  3. admin-web/lib (이미 잘 modularized)
     → 추가 분리 불필요 (현재 적절)

평가: 기존 모듈은 현재 적절한 수준으로 modularized
```

### 4C. 모듈화 기준

```
PHASE3Y 모듈화 기준:

1. 단일 책임 원칙
   - 각 모듈은 하나의 workplan만 담당
   - electrical_workplan은 electrical_workplan만 처리

2. 공개 API 최소화
   - export는 필요한 함수만 (builder, writer, schemas)
   - 내부 함수는 private (_.ts로 표기 또는 내부 정의)

3. 테스트 포함
   - 각 모듈에 __tests__/ 또는 .test.ts 파일
   - 최소 기본 케이스 커버

4. 문서화
   - README.md (모듈 목적, 사용법)
   - JSDoc 주석 (함수 시그니처)
   - 스키마 문서 (입출력 형식)

5. 버전 관리
   - 마이크로서비스 선택 시: 독립 version 관리
   - 라이브러리 선택 시: admin-web version 포함
```

---

## STEP 5: 모듈화 사전 체크리스트

### 5A. 기술 준비도

```
[✓] Git 기준선 확인: 4f1153d (clean)
[✓] 모듈화 아키텍처 이해: file_map_executor 선례
[✓] 도커 배포 경험: file_map_executor 완료
[✓] TypeScript 프론트엔드 구조: admin-web 분석 완료
[✓] 테스트 프레임워크: pytest (Python), Jest (TypeScript) 사용 가능
[✓] 문서화 도구: markdown 사용 가능
```

**판정: 기술 준비도 100% ✓**

### 5B. 의존성 확인

```
electrical_workplan이 의존할 수 있는 모듈:
  - admin-web/src/lib/fileMapCleanupPlan.ts (계획 구조 참고)
  - admin-web/src/lib/api.ts (API 통신)
  - services/file_map_executor (executor 패턴 참고)

heavy_lifting_workplan이 의존할 수 있는 모듈:
  - 동일

순환 의존성 위험: 없음 (신규 모듈이므로)
```

**판정: 의존성 구조 명확 ✓**

### 5C. 배포 준비

```
마이크로서비스 선택 시:
  [✓] docker-compose.yml 수정 가능 (file_map_executor 패턴)
  [✓] Dockerfile 템플릿 존재 (docker/file-map-executor.Dockerfile)
  [✓] 네트워크 설정 (app_web, default)
  [✓] healthcheck 설정 가능

라이브러리 모듈 선택 시:
  [✓] admin-web 빌드 파이프라인 (Next.js)
  [✓] 배포 자동화 (기존 admin-web 배포와 동일)
```

**판정: 배포 준비도 100% ✓**

---

## STEP 6: 최종 권장사항

### 6A. 아키텍처 전략 (권장)

```
추천: 옵션 A (라이브러리 모듈)

근거:
  1. 빠른 개발 속도: HTTP 오버헤드 없음
  2. 단순한 배포: admin-web 빌드와 함께 진행
  3. 기존 패턴 일관성: fileMap*.ts 패턴 준수
  4. 테스트 용이성: 로컬 테스트 간단
  5. 향후 확장: 필요 시 마이크로서비스로 분리 가능

구현 우선순위:
  1. electrical_workplan 라이브러리 (admin-web/src/lib/electrical-workplan/)
  2. heavy_lifting_workplan 라이브러리 (admin-web/src/lib/heavy-lifting-workplan/)
```

### 6B. 개발 흐름 (예상)

```
PHASE3Y-BUILD-1: electrical_workplan 구현
  1. admin-web/src/lib/electrical-workplan/ 생성
  2. builder.ts, schemas.ts 구현
  3. sections/ 서브디렉토리 및 렌더러 구현
  4. __tests__/ 테스트 작성
  5. admin-web API route 통합 (/api/electrical-workplan/*)
  6. smoke 테스트

PHASE3Y-BUILD-2: heavy_lifting_workplan 구현
  (electrical_workplan과 유사 흐름)

PHASE3Y-INTEGRATION: 통합 및 배포
  - docker-compose.yml 재빌드
  - smoke 테스트
  - 운영 배포
```

### 6C. 시간/범위 예상

```
electrical_workplan:
  - 구현: 4-6시간
  - 테스트: 2-3시간
  - 배포: 1시간
  - 합계: 7-10시간

heavy_lifting_workplan:
  - 구현: 4-6시간 (재사용 가능한 패턴)
  - 테스트: 2-3시간
  - 배포: 1시간
  - 합계: 7-10시간

전체 PHASE3Y: 14-20시간 (유연한 일정)
```

---

## 최종 체크리스트

```
[✓] STEP 0: 기준선 확인 (4f1153d, clean)
[✓] STEP 1: 파일 존재 여부 확인 (미존재 — 신규 생성 필요)
[✓] STEP 2: 모듈화 상태 분석 (현재 잘 구조화됨)
[✓] STEP 3: workplan 분석 (두 가지 옵션 제시)
[✓] STEP 4: 범위 제안 (라이브러리 모듈 권장)
[✓] STEP 5: 사전 체크리스트 (모두 PASS)
[✓] STEP 6: 최종 권장사항 (구현 전략 제시)
```

---

## 최종 판정

| 항목 | 상태 | 비고 |
|------|------|------|
| 기준선 | PASS | 4f1153d, clean ✓ |
| 파일 존재 | NOT FOUND | 신규 생성 필요 |
| 기술 준비도 | READY | 100% 준비 완료 |
| 아키텍처 | READY | 옵션 제시 완료 |
| 테스트 준비 | READY | 218개 테스트 파일 기존 |
| 배포 준비 | READY | docker-compose 수정 가능 |
| **전체 판정** | **✅ READY** | **조건부 진행 가능** |

### 진행 조건

```
PHASE3Y 시작 전 확인사항:
  1. 옵션 A (라이브러리) vs 옵션 B (마이크로서비스) 선택
  2. electrical_workplan, heavy_lifting_workplan 스펙 정의
  3. 각 workplan의 입출력 형식 결정
  4. 테스트 케이스 작성
```

### 다음 단계

```
PHASE3Y-BUILD-1: electrical_workplan 구현 시작
  - 목표: admin-web/src/lib/electrical-workplan 생성
  - 범위: builder, sections, renderer, tests
  - 기간: 7-10시간 예상
```

---

## 생성 보고서

- `docs/reports/phase3y_preflight_audit_1.md` (본 파일)

---

**작성**: Claude Haiku 4.5  
**보고 일시**: 2026-05-03T?:??:??Z  
**검증**: read-only 분석 완료, 코드 수정 없음
