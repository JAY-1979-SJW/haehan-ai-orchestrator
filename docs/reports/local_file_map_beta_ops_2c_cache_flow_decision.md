# LOCAL-FILE-MAP-BETA-OPS-2C — cleanup-plan 캐시 구조 감사 및 fixture 검증 경로 확정

**날짜:** 2026-05-03  
**목표:** cleanup-plan API의 local_file_map.json 캐시 사용 문제를 감사하고, fixture 기반 real-run 검증을 안전하게 계속할 수 있는 방식을 확정  
**판정:** ✅ **PASS** (Option A 기반 BETA-OPS-2D-EXECUTE-ONLY 실행 경로 확정)

---

## 1. 작업 내용

BETA-OPS-2B-API-RUN에서 발견된 cleanup-plan API의 local_file_map.json 캐시 사용 문제를 감사하고, 다음 검증 단계(BETA-OPS-2D)의 안전한 방식을 결정했습니다.

**실행 범위:**
- 코드 수정 없음 (감사만)
- 기존 파일 변경 없음
- 캐시 구조 및 의존성 분석
- Option A/B 가능 여부 판단
- 최종 검증 경로 결정

---

## 2. cleanup-plan 캐시 구조 감사

### 2.1 cleanup-plan API (GET /api/file-map/cleanup-plan)

**코드 분석:** `admin-web/src/app/api/file-map/cleanup-plan/route.ts`

| 항목 | 내용 |
|------|------|
| **파라미터** | mode only (mask_always / reveal_after_auth / reveal_on_trusted_device / reveal_for_export_with_warning) |
| **source 파라미터** | ❌ **미지원** |
| **cache 파일** | `getStoragePath()` → %USERPROFILE%/AppData/Local/HaehanAI/inventory/local_file_map.json |
| **cache path 격리** | ❌ **불가능** (하드코드됨, 환경변수 재정의 불가) |
| **cache 읽기** | ✓ 읽기 전용 (파일 변경 안 함) |
| **응답 source** | "local_cleanup_plan" (고정) |

### 2.2 cleanup-preflight API (POST /api/file-map/cleanup-preflight)

**코드 분석:** `admin-web/src/app/api/file-map/cleanup-preflight/route.ts`

| 항목 | 내용 |
|------|------|
| **plans 직접 입력** | ✓ **가능** (cleanup-plan 결과에 의존하지 않음) |
| **base_target_dir** | ✓ **필수 입력** |
| **source 파라미터** | ❌ 미사용 |

### 2.3 cleanup-execute API (POST /api/file-map/cleanup-execute)

**코드 분석:** `admin-web/src/app/api/file-map/cleanup-execute/route.ts`

| 항목 | 내용 |
|------|------|
| **plans 직접 입력** | ✓ **가능** (선택사항, 기본값 []) |
| **base_target_dir** | ✓ **가능** (선택사항) |
| **dry_run 파라미터** | ✓ **지원** (기본값 true) |
| **approval_token** | ✓ **필수**, UUID suffix 검증 적용됨 |
| **user_confirmed_execution** | ✓ **필수** |
| **Python 호출** | spawn('python', [...cleanup_executor_api.py]) |

---

## 3. local_file_map.json 파일 분석

### 3.1 파일 위치 및 메타데이터

```
경로: C:\Users\skyjw\AppData\Local\HaehanAI\inventory\local_file_map.json
크기: 1.7 MB (1710762 바이트)
수정: 2026-05-02 10:40:16
```

### 3.2 파일 구조

| 최상위 키 | 포함 여부 | 설명 |
|-----------|---------|------|
| scan_timestamp | ✓ | "2026-05-02T10:40:16.109819" |
| scanned_directory | ✓ | "C:\Users\skyjw\OneDrive\01. PROJECT_FILE" (실제 사용자 경로) |
| total_files | ✓ | 5000 |
| total_size_bytes | ✓ | 33258616714 (약 31GB) |
| files_by_category | ✓ | document, spreadsheet, cad, image, archive, unknown 등 |
| large_files | ✓ | [파일 배열] |
| old_files | ✓ | [파일 배열] |
| suspicious_duplicates | ✓ | [파일 배열] |
| suspicious_temp | ✓ | [파일 배열] |
| recommendations | ✓ | [추천 배열] |
| **root** | ❌ | 없음 |
| **source** | ❌ | 없음 |

### 3.3 파일 내용 특성

- ✓ 실제 사용자 파일 경로 포함 (민감)
- ✓ 파일명, 크기, 수정 시간 포함
- ✓ 중복 파일 정보 포함
- ✓ 임시 파일 정보 포함
- ❌ fixture 구분 필드 없음

---

## 4. Option B 판단: 격리 storage path 기반 검증

### 조건 분석

**Option B 가능 요건:**
1. ✓ 별도 storage path 지정 가능
2. ❌ **storage path 격리 불가능** - getStoragePath() 하드코드됨
3. ❌ **환경변수 재정의 불가능** - 코드에 경로 하드코드
4. ❌ fixture 전용 local_file_map.json 격리 불가능
5. ❌ 기존 운영 캐시 보호 불가능

### 판정

**❌ Option B 불가능**

**근거:**
- `getStoragePath()` → `path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory')` (하드코드)
- 환경변수로 storage path 재정의 불가능
- admin-web 재시작 또는 코드 수정 없이는 격리 불가능
- fixture 전용 local_file_map.json을 별도 경로에 만들어도 cleanup-plan이 사용 불가능

**위험:**
- cleanup-plan이 항상 운영 경로의 local_file_map.json을 로드
- fixture 검증 시 cleanup-plan 응답이 실제 사용자 파일 정보 포함 가능
- cleanup-plan → cleanup-preflight → cleanup-execute 전체 E2E 불가능

---

## 5. Option A 판단: cleanup-execute 직접 호출 기반 검증

### 조건 분석

**Option A 요건:**
1. ✓ cleanup-execute API가 plans 직접 입력 받을 수 있음
2. ✓ base_target_dir를 fixture target으로 지정 가능
3. ✓ approval_token UUID 검증 적용됨
4. ✓ user_confirmed_execution 필수
5. ✓ dry_run=true 선행 가능
6. ✓ dry_run=false는 fixture ready 파일 2개에만 제한 가능
7. ✓ 사전검사 우회 사실을 보고서에 기록 가능

### 판정

**✅ Option A 가능**

**근거:**
- cleanup-preflight: plans 직접 입력으로 독립 검증 가능
- cleanup-execute: plans 직접 입력 + base_target_dir + dry_run 파라미터 지원
- 승인 토큰 검증, 사용자 확인 필수 → 안전성 확보
- dry_run=true → dry_run=false 순차 실행으로 충분한 검증 가능

**한계:**
- ⚠️ cleanup-plan fixture E2E는 불가능 (source 파라미터 없음)
- ⚠️ cleanup-plan 응답은 운영 local_file_map.json 데이터 포함
- ⚠️ cleanup-plan → preflight 연쇄 호출 미지원

---

## 6. 최종 선택: BETA-OPS-2D-EXECUTE-ONLY

### 선택 경로

```
BETA-OPS-2D-EXECUTE-ONLY
├─ cleanup-plan API → 감시만 (운영 데이터 주의)
├─ cleanup-preflight → plans 직접 입력으로 검증 ✓
└─ cleanup-execute → dry_run=true → dry_run=false 순차 검증 ✓
```

### 실행 방식

| 단계 | 방식 | 입력 | 목표 |
|------|------|------|------|
| **Preflight** | POST /cleanup-preflight | plans 직접 구성 | 파일 존재 및 경로 검증 |
| **Execute (dry)** | POST /cleanup-execute | preflight_id + plans + dry_run=true | 이동 계획 수행 검증 (실제 이동 X) |
| **Execute (real)** | POST /cleanup-execute | preflight_id + plans + dry_run=false | fixture 파일 실제 이동 검증 (2개만) |

### 안전성 조치

- ✓ fixture 파일만 대상 (실제 사용자 파일 접근 안 함)
- ✓ dry_run=false는 fixture에만 제한
- ✓ approval_token UUID 검증 필수
- ✓ user_confirmed_execution 필수
- ✓ 모든 과정을 보고서에 기록

---

## 7. 남은 주의사항 (WARN)

| 번호 | 항목 | 내용 | 영향 |
|------|------|------|------|
| WARN-1 | cleanup-plan E2E 불가 | source 파라미터 미지원, cache path 고정 | fixture 기반 cleanup-plan 검증 불가능 |
| WARN-2 | 운영 cache 데이터 노출 | cleanup-plan API 응답에 실제 사용자 파일 정보 | fixture 테스트 시에도 운영 경로 정보 포함 가능 |
| WARN-3 | preflight 우회 | cleanup-plan 결과를 preflight 입력으로 사용하지 않음 | API 연쇄 흐름 미검증 (plans 구성으로 대체) |
| WARN-4 | Python executor 직접 호출 | cleanup-execute가 Python cleanup_executor_api.py 호출 | Python 스크립트 경로 및 동작 사전 확인 필수 |

---

## 8. 다음 단계 지시안 (BETA-OPS-2D)

### 준비 사항

1. **fixture ready 파일 2개 준비**
   - 경로: `/tmp/local-file-map-beta-ops-2d-fixture/` (또는 지정 경로)
   - 파일명: `test_file_1.txt`, `test_file_2.txt`
   - 파일 크기: 작음 (1KB 이상)

2. **target 디렉토리 준비**
   - 경로: `/tmp/local-file-map-beta-ops-2d-target/`
   - 빈 디렉토리 또는 기존 파일 확인

3. **approval_token 생성**
   - 형식: `user-approved-cleanup-<UUID>`
   - 예: `user-approved-cleanup-550e8400-e29b-41d4-a716-446655440000`

### 실행 순서

1. **Step 1:** cleanup-preflight API 호출 (plans 구성)
   - Input: plans 배열 (fixture 파일 2개)
   - Input: base_target_dir
   - Output: preflight_id, items 상태 확인

2. **Step 2:** cleanup-execute API 호출 (dry_run=true)
   - Input: preflight_id + approval_token + user_confirmed_execution=true + dry_run=true
   - Output: 이동 계획 결과 검증

3. **Step 3:** cleanup-execute API 호출 (dry_run=false, 최종)
   - Input: preflight_id + approval_token + user_confirmed_execution=true + dry_run=false
   - Output: 실제 이동 결과 검증

### 보고 방식

- 모든 API 호출 및 응답을 보고서에 기록
- 파일 이동 결과 검증 (target 디렉토리 파일 확인)
- 오류 및 예외 사항 즉시 기록
- WARN 항목 최종 검토

---

## 9. 결론

**cleanup-plan 캐시 구조:**
- source 파라미터 미지원
- storage path 격리 불가능
- fixture 기반 E2E 불가능

**선택 경로:**
- Option B (격리 storage) → ❌ 불가능
- Option A (직접 호출) → ✅ 가능

**최종 판정:**
- ✅ **PASS** — BETA-OPS-2D-EXECUTE-ONLY 기반으로 진행 가능
- ⚠️ **WARN** — WARN-1~4 주의사항 반드시 준수
- 📌 **다음:** BETA-OPS-2D 시작 (fixture 준비 → preflight → execute 검증)
