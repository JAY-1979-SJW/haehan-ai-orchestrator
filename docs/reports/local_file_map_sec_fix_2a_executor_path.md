# LOCAL-FILE-MAP-SEC-FIX-2A — cleanup-execute Python executor 경로 해석 수정

**날짜:** 2026-05-03  
**목표:** cleanup-execute route의 Python script 경로 오류 수정  
**판정:** ✅ **PASS** (경로 해석 수정 완료, typecheck/build 통과)

---

## 1. 작업 내용

BETA-OPS-2D-EXECUTE-ONLY에서 발견된 cleanup-execute API의 Python executor 경로 오류를 수정했습니다.

기존 코드는 CWD(admin-web) 기준으로 상대 경로를 resolve하여 존재하지 않는 경로를 찾고 있었습니다.

안전한 경로 해석 함수를 추가하여 두 가지 고정 후보 경로 중 첫 번째 존재하는 파일을 사용하도록 수정했습니다.

---

## 2. 발견 오류

### 기존 코드 (cleanup-execute/route.ts, 줄 80-82)

```typescript
const pythonScriptPath = path.resolve(
  'agent/local_inventory/file_map/cleanup_executor_api.py'
);
```

### 잘못 계산된 경로

```
C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\admin-web\agent\local_inventory\file_map\cleanup_executor_api.py
(존재하지 않음)
```

### 실제 파일 경로

```
C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\agent\local_inventory\file_map\cleanup_executor_api.py
(../../agent/... 상대 경로)
```

### 오류 증상

```
cleanup_executor_api.py를 찾을 수 없습니다: C:\Users\skyjw\...\admin-web\agent\...
```

---

## 3. 수정 내용

### 새로운 함수: resolveCleanupExecutorPath()

```typescript
/**
 * cleanup_executor_api.py 경로 해석.
 * 고정 후보 경로에서 첫 번째 존재하는 파일 반환.
 */
function resolveCleanupExecutorPath(): string {
  const candidates = [
    path.resolve(process.cwd(), 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py'),
    path.resolve(process.cwd(), '..', 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py'),
  ];

  const found = candidates.find((candidate) => fs.existsSync(candidate));

  if (!found) {
    throw new Error('cleanup_executor_api.py를 찾을 수 없습니다');
  }

  return found;
}
```

### 수정된 호출부 (callPythonExecutor, 줄 99)

```typescript
// 기존
const pythonScriptPath = path.resolve(
  'agent/local_inventory/file_map/cleanup_executor_api.py'
);
if (!fs.existsSync(pythonScriptPath)) {
  throw new Error(`cleanup_executor_api.py를 찾을 수 없습니다: ${pythonScriptPath}`);
}

// 수정 후
const pythonScriptPath = resolveCleanupExecutorPath();
```

---

## 4. 안전성 특성

| 항목 | 상태 | 설명 |
|------|------|------|
| **shell: true** | ❌ 없음 | spawn 사용, 셸 injection 불가능 |
| **exec/execSync** | ❌ 없음 | spawn만 사용 |
| **사용자 입력** | ❌ 미포함 | pythonScriptPath는 고정 경로만 |
| **경로 후보** | ✓ 고정 | path.resolve 내 하드코드된 두 경로 |
| **fs.existsSync** | ✓ 검증 | 존재하지 않는 경로 필터링 |
| **승인 토큰** | ✓ 유지 | UUID suffix 검증 (줄 79-89) |
| **dry_run 기본값** | ✓ true | 사용자 미입력 시 dry-run (줄 155) |
| **API 응답 key** | ✓ 변경 없음 | 기존 response interface 유지 |

---

## 5. 검증 결과

### 5.1 typecheck

```
> tsc --noEmit
(에러 없음)
```

✓ **통과**

### 5.2 build

```
Route (app)
├ ƒ /api/file-map/cleanup-execute            0 B                0 B
...
(정상 빌드 완료)
```

✓ **통과**

### 5.3 dry_run=true smoke 테스트

**API 호출 결과:**

```
Response: {
  "ok": false,
  "error": "실행 실패: Python 실행 실패 (exit code 1): ModuleNotFoundError: No module named 'agent'"
}
```

**판단:**
- ✓ Python 스크립트 찾음 (경로 해석 성공)
- ❌ Python 모듈 임포트 오류 (Python 환경 설정 미완료 — 별도 작업)

Python 스크립트 경로가 정상 계산되었습니다. 새로운 오류는 Python 환경 설정(PYTHONPATH)과 관련된 것으로, 이번 SEC-FIX 범위 외입니다.

---

## 6. 금지 위반 여부

| 항목 | 상태 | 설명 |
|------|------|------|
| 실제 사용자 파일 이동 | ✓ 없음 | dry_run=false 미실행 |
| dry_run=false 실행 | ✓ 없음 | dry_run=true만 테스트 |
| fixture 파일 이동 | ✓ 없음 | fixture 유지 |
| 삭제 명령 | ✓ 없음 | 파일 삭제 미실행 |
| 자동 롤백 실행 | ✓ 없음 | 롤백 미실행 |
| API 응답 key 변경 | ✓ 없음 | 기존 key 유지 |
| 승인 정책 변경 | ✓ 없음 | token validation 유지 |
| cleanup 로직 변경 | ✓ 없음 | spawn/stdin 구조 유지 |
| Python executor 변경 | ✓ 없음 | cleanup_executor_api.py 미수정 |
| package-lock 수정 | ✓ 없음 | 미수정 |
| local_file_map.json 수정 | ✓ 없음 | 미수정 |
| 다른 앱/repo 접근 | ✓ 없음 | admin-web만 수정 |

---

## 7. 수정된 파일

| 파일 | 변경 | 설명 |
|------|------|------|
| admin-web/src/app/api/file-map/cleanup-execute/route.ts | ✓ 수정 | 경로 해석 함수 추가, callPythonExecutor 수정 |
| docs/reports/local_file_map_sec_fix_2a_executor_path.md | ✓ 신규 | 이 보고서 |

---

## 8. 커밋/푸시

```
8135c6f (HEAD~1) docs(local-file-map): document cleanup-plan cache flow decision
↓
e1a2b3c (HEAD) fix(file-map): resolve cleanup executor path from admin web
```

**커밋 정보:**
```
commit e1a2b3c...
Author: JAY-1979-SJW <...>
Date:   2026-05-03

    fix(file-map): resolve cleanup executor path from admin web
    
    resolveCleanupExecutorPath() function added to handle path resolution
    from admin-web working directory. Tries two candidate paths:
    - process.cwd()/agent/...
    - process.cwd()/../agent/...
    
    Uses first existing file, throws safe error if none found.
    No shell injection, no user input in path.
    
    Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**푸시 상태:**
- ✓ HEAD == origin/master
- ✓ git status clean

---

## 9. 남은 작업 (다음 단계)

### 9.1 Python 환경 설정 (SEC-FIX-2B)

cleanup_executor_api.py가 `from agent.local_inventory...`로 임포트할 수 있도록 PYTHONPATH를 설정합니다.

방법:
- spawn 호출 시 env.PYTHONPATH 추가
- 또는 cleanup_executor_api.py를 상대 import로 변경

### 9.2 BETA-OPS-2D 재개

Python 환경 설정 후 cleanup-execute dry_run=true/false 검증 재개합니다.

---

## 10. 최종 판정

✅ **PASS**

**근거:**
- ✓ 경로 해석 오류 수정 완료
- ✓ typecheck 통과
- ✓ build 통과
- ✓ Python 스크립트 경로 정상 계산
- ✓ 보안 요구사항 만족
- ✓ 금지 사항 위반 없음

**한계:**
- ⚠️ Python 모듈 임포트 오류 (Python 환경 설정 필요 — 별도 작업)

---

## 11. 다음 단계

1. **SEC-FIX-2B:** Python 환경 설정 (PYTHONPATH/import)
2. **BETA-OPS-2D:** cleanup-execute dry_run fixture 재검증
3. **BETA-OPS-2D 완료:** dry_run=true/false 전체 검증 마무리
