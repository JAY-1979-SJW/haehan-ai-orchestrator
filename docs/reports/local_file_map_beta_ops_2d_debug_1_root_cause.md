# LOCAL-FILE-MAP-BETA-OPS-2D-DEBUG-1 — cleanup-execute 승인 검증 실패 원인 분석

**날짜:** 2026-05-03  
**목표:** "승인 가능한 항목이 없습니다" 오류의 근본 원인 파악 및 해결  
**판정:** ✅ **PASS** (근본 원인 파악 및 수정 완료, 통합 테스트 성공)

---

## 1. 발견된 근본 원인

### 1.1 기술적 근본 원인 (3가지)

| 순서 | 원인 | 설명 | 영향 |
|------|------|------|------|
| **1순위** | 시스템 경로 필터링 | fixture가 AppData 디렉토리에 위치 → cleanup_policy.py의 SYSTEM_EXCLUDED_PREFIXES에 `\AppData\` 포함 → 모든 항목 거부 | preflight_report.ok_count = 0 |
| **2순위** | 카테고리 유효성 | 테스트가 category="document" (단수) 사용 → cleanup_policy.py의 ALLOWED_GROUPS = {"documents", ...} (복수) 필요 | 승인 불가능 항목으로 표시 |
| **3순위** | plans 구조 불확실성 | cleanup-execute API의 plans 입력 검증 부재 → 다양한 형식 가능 (문자열, 불완전 객체 등) | 잠재적 오류 가능성 |

### 1.2 설정 데이터 (cleanup_policy.py)

```python
# 시스템 경로 제외 목록 (line 22-33)
SYSTEM_EXCLUDED_PREFIXES = [
    ":\\Windows",
    ":\\Program Files",
    ":\\Program Files (x86)",
    "\\AppData\\",      # ← fixture 경로가 여기에 해당
    "\\.git",
    "\\node_modules",
    "\\venv",
    "\\.venv",
    "\\__pycache__",
    "\\.pytest_cache",
]

# 허용 카테고리 (line 6)
ALLOWED_GROUPS = {"documents", "spreadsheets", "cad", "images", "archive"}
# "document" (단수) 미포함
```

---

## 2. 디버그 과정

### 2.1 로그 기반 진단

```
[DEBUG] plans: [{'operation_id': 'op-001', 'path': '...\\AppData\\...', 'category': 'document', ...}]
[DEBUG] preflight_report.ok_count: 0
[DEBUG] preflight_report.items: [{'id': 'op-001', 'status': 'blocked', 'reason': "'document' 그룹은 허용되지 않습니다"}]
```

→ 카테고리 오류 식별

```
[DEBUG] preflight_report.items: [{'id': 'op-001', 'status': 'system_path', 'reason': '시스템 경로는 이동할 수 없습니다'}]
```

→ 시스템 경로 오류 식별

### 2.2 디버그 로깅 추가

cleanup_executor_api.py와 cleanup_executor.py에 `sys.stderr` 기반 로깅 추가:
- plans 수신 확인
- preflight_report 상태 확인
- validate_approval 호출 파라미터 확인

---

## 3. 수정 사항

### 3.1 cleanup-execute/route.ts: plans 정규화 함수 추가

**문제:** plans이 문자열, 불완전 객체, 또는 기본값 없는 구조일 수 있음

**해결책:** `normalizePlans()` 함수 추가 (line 115-158)

```typescript
function normalizePlans(plans: unknown[]): Record<string, unknown>[] {
  if (!Array.isArray(plans)) {
    return [];
  }

  return plans.map((plan, index) => {
    // 1. 문자열인 경우: path로 변환
    if (typeof plan === 'string') {
      return {
        operation_id: `plan-${index}-${Date.now()}`,
        path: plan,
        category: 'unknown',
        file_size_bytes: 0,
        file_name: plan.split(/[\\\/]/).pop() || 'unknown',
      };
    }

    // 2. 객체인 경우: 필수 필드 보정
    if (typeof plan === 'object' && plan !== null) {
      const obj = plan as Record<string, unknown>;
      return {
        operation_id: obj.operation_id || `plan-${index}-${Date.now()}`,
        path: obj.path || '',
        category: obj.category || 'unknown',
        file_size_bytes: obj.file_size_bytes || 0,
        file_name: obj.file_name || '',
      };
    }

    // 3. 기타: 기본값 적용
    return {
      operation_id: `plan-${index}-${Date.now()}`,
      path: '',
      category: 'unknown',
      file_size_bytes: 0,
      file_name: '',
    };
  });
}
```

**특성:**
- 문자열 입력 지원 (file_name 자동 추출)
- 불완전 객체 처리 (기본값 채우기)
- operation_id 자동 생성 (timestamp 기반)

### 3.2 cleanup-executor_api.py: 디버그 로깅 추가

```python
# 사전검사 실행 전/후 로깅
sys_debug.stderr.write(f"[DEBUG] plans: {plans}\n")
sys_debug.stderr.write(f"[DEBUG] base_target_dir: {base_target_dir}\n")
preflight_report = run_preflight(plans, base_target_dir, include_sensitive)
sys_debug.stderr.write(f"[DEBUG] preflight_report.ok_count: {preflight_report.ok_count}\n")
sys_debug.stderr.write(f"[DEBUG] preflight_report.items: ...\n")
```

### 3.3 cleanup_executor.py: 검증 로깅 추가

```python
def validate_approval(...):
    _debug_sys.stderr.write(f"[VALIDATE] approval_token={bool(approval_token)}, ...")
    if preflight_report:
        _debug_sys.stderr.write(f"[VALIDATE] preflight_report.ok_count={preflight_report.ok_count}\n")
```

---

## 4. 해결 방안

### 방안 1: fixture 경로 변경 (즉각적 해결) ✅ 선택

**상황:**
- 기존 fixture: `C:\Users\skyjw\AppData\Local\Temp\local-file-map-beta-ops-2d\`
- 문제: AppData는 시스템 경로로 분류됨

**해결:**
- 새 fixture: `C:\temp\cleanup-test-fixture\`
- 경로 구조:
  - `C:\temp\cleanup-test-fixture\source\` (document-a.txt, document-b.txt)
  - `C:\temp\cleanup-test-fixture\target\` (existing.txt)

**결과:** ✅ 테스트 통과

### 방안 2: 정책 변경 (장기 검토 필요) ❌ 미실시

**고려사항:**
- AppData 제외는 보안 정책 (사용자 민감 정보 보호)
- 변경 시 의도하지 않은 시스템 경로 이동 가능성
- 현재 정책 유지 권장

---

## 5. 수정된 파일

| 파일 | 변경 | 내용 |
|------|------|------|
| admin-web/src/app/api/file-map/cleanup-execute/route.ts | ✓ 수정 | normalizePlans() 함수 추가, plans 정규화 |
| agent/local_inventory/file_map/cleanup_executor_api.py | ✓ 수정 | 디버그 로깅 추가 |
| agent/local_inventory/file_map/cleanup_executor.py | ✓ 수정 | validate_approval 로깅 추가 |
| docs/reports/local_file_map_beta_ops_2d_debug_1_root_cause.md | ✓ 신규 | 이 보고서 |

---

## 6. 검증 결과

### 6.1 typecheck/build

```
✓ tsc --noEmit (통과)
✓ npm run build (통과)
```

### 6.2 통합 테스트

#### Test 1: dry_run=true (모의 실행)

**요청:**
```json
{
  "preflight_id": "test-preflight-id-7",
  "package_id": "test-package-7",
  "approval_token": "user-approved-cleanup-550e8400-e29b-41d4-a716-446655440000",
  "user_confirmed_execution": true,
  "dry_run": true,
  "plans": [
    {
      "operation_id": "op-001",
      "path": "C:\\temp\\cleanup-test-fixture\\source\\document-a.txt",
      "category": "documents",
      "file_size_bytes": 29,
      "file_name": "document-a.txt"
    }
  ],
  "base_target_dir": "C:\\temp\\cleanup-test-fixture\\target"
}
```

**응답:**
```json
{
  "ok": true,
  "run_id": "1be40769-cff8-49d5-848c-deb5e83841b8",
  "success_count": 1,
  "dry_run": true,
  "succeeded": [
    {
      "operation_id": "op-001",
      "source_path": "C:\\temp\\cleanup-test-fixture\\source\\document-a.txt",
      "target_path": "C:\\Temp\\cleanup-test-fixture\\target\\document-a.txt"
    }
  ]
}
```

**판정:** ✅ **PASS**
- ok: true
- success_count: 1
- 실제 파일 이동 없음 (dry_run=true 확인)

#### Test 2: dry_run=false (실제 실행)

**요청:** (dry_run=false, document-b.txt)

**응답:**
```json
{
  "ok": true,
  "run_id": "e34e35e5-32b5-484b-929a-3baba029da3e",
  "success_count": 1,
  "dry_run": false,
  "succeeded": [
    {
      "operation_id": "op-001",
      "source_path": "C:\\temp\\cleanup-test-fixture\\source\\document-b.txt",
      "target_path": "C:\\Temp\\cleanup-test-fixture\\target\\document-b.txt"
    }
  ]
}
```

**파일 상태 검증:**
```
Source directory:
  ✓ document-a.txt (29 bytes) - 유지됨 (dry_run 파일)
  
Target directory:
  ✓ document-b.txt (29 bytes) - 새로 이동됨 ✓
  ✓ existing.txt (28 bytes) - 유지됨
```

**판정:** ✅ **PASS**
- ok: true
- success_count: 1
- 파일 실제 이동 확인됨

---

## 7. 최종 판정

### ✅ **PASS** — cleanup-execute 비즈니스 로직 검증 완료

**성공 조건:**
1. ✓ Python 환경 설정 정상 (SEC-FIX-2A/2B)
2. ✓ plans 입력 정규화 추가
3. ✓ 카테고리/시스템 경로 검증 작동
4. ✓ dry_run=true 시뮬레이션 성공
5. ✓ dry_run=false 실제 이동 성공

**근본 원인:**
1. 시스템 경로 필터링 정상 작동 (AppData 경로 거부)
2. 카테고리 명명 오류 (document vs documents)
3. fixture 배치 위치 부적절 (AppData)

**해결 결과:**
1. plans 정규화 함수 추가 → 입력 구조 안정성 개선
2. fixture 경로 변경 → 테스트 성공

---

## 8. 다음 단계

1. **BETA-OPS-2D-FINAL:** 최종 통합 테스트 및 보고서 작성
2. **코드 정리:** 디버그 로깅 제거 또는 프로덕션 로그로 전환
3. **문서화:** API 입력 스키마 명확화 및 예제 제공

---

## 9. 결론

cleanup-execute API의 "승인 가능한 항목이 없습니다" 오류는:
- **환경 이슈** (시스템 경로) + **데이터 이슈** (카테고리 명명)의 조합
- Python 코드 자체는 정상 작동
- 입력 데이터 및 정책 이해 필요

**현재 상태:**
- ✅ API 정상 작동
- ✅ 파일 이동 성공 (dry_run, real)
- ✅ 승인 검증 정상
- ✅ 테스트 환경 구성 완료

