# LOCAL-FILE-MAP-SEC-FIX-2B — cleanup-execute Python module import 경로 보정

**날짜:** 2026-05-03  
**목표:** cleanup-execute spawn Python 실행 시 agent 모듈 import 가능하도록 cwd/PYTHONPATH 보정  
**판정:** ✅ **PASS** (코드 수정 완료, typecheck/build 통과, Python 환경 설정 구현)

---

## 1. 작업 내용

SEC-FIX-2A에서 Python executor script 경로 오류는 해결되었으나, spawn으로 Python을 실행할 때 agent 모듈을 import하지 못하는 문제를 해결했습니다.

cleanup-execute route에 resolveRepoRoot() 함수를 추가하고, spawn 호출 시 cwd와 PYTHONPATH를 repo root로 설정하여 Python이 agent 모듈을 정상적으로 import할 수 있도록 보정했습니다.

---

## 2. 발견 오류

### 문제

```
ModuleNotFoundError: No module named 'agent'
```

### 원인

spawn('python', [pythonScriptPath])에서:
- cwd: process.cwd() (admin-web 또는 repo root 불명확)
- PYTHONPATH: 설정하지 않음
- cleanup_executor_api.py가 `from agent.local_inventory...` import 시도

### 결과

Python이 agent 모듈을 찾을 수 없음. sys.path에 repo root가 포함되지 않음.

---

## 3. 수정 내용

### 3.1 새로운 함수: resolveRepoRoot()

```typescript
/**
 * repo root 디렉터리 해석.
 * agent 모듈과 admin-web이 모두 존재하는 경로 반환.
 */
function resolveRepoRoot(): string {
  const candidates = [
    process.cwd(),
    path.resolve(process.cwd(), '..'),
  ];

  const found = candidates.find((candidate) =>
    fs.existsSync(path.join(candidate, 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py')) &&
    fs.existsSync(path.join(candidate, 'admin-web'))
  );

  if (!found) {
    throw new Error('repo root not found in expected paths');
  }

  return found;
}
```

**특성:**
- 고정 후보 경로 2가지만 확인
- agent 모듈과 admin-web 디렉터리로 repo root 판정
- 사용자 입력 미포함

### 3.2 수정된 callPythonExecutor

**기존:**
```typescript
const child = spawn('python', [pythonScriptPath], {
  stdio: ['pipe', 'pipe', 'pipe'],
});
```

**수정 후:**
```typescript
const pythonScriptPath = resolveCleanupExecutorPath();
const repoRoot = resolveRepoRoot();

const child = spawn('python', [pythonScriptPath], {
  cwd: repoRoot,
  env: {
    ...process.env,
    PYTHONPATH: [
      repoRoot,
      process.env.PYTHONPATH || '',
    ].filter(Boolean).join(path.delimiter),
  },
  stdio: ['pipe', 'pipe', 'pipe'],
});
```

**변경사항:**
- cwd: repoRoot 지정 (Python 실행 디렉터리 고정)
- env: PYTHONPATH에 repo root 추가
- 기존 process.env 유지 (secret 노출 금지)
- shell: true 없음 (spawn 기본값 유지)

---

## 4. 안전성 특성

| 항목 | 상태 | 설명 |
|------|------|------|
| **shell: true** | ❌ 없음 | spawn 기본값, shell injection 불가능 |
| **exec/execSync** | ❌ 없음 | spawn만 사용 |
| **사용자 입력** | ❌ 미포함 | pythonScriptPath, repoRoot 고정 경로 |
| **PYTHONPATH** | ✓ 고정 | repo root만 추가, 사용자 입력 미포함 |
| **cwd** | ✓ 고정 | repo root로 명시 설정 |
| **승인 토큰** | ✓ 유지 | UUID suffix 검증 (줄 101-112) |
| **dry_run 기본값** | ✓ true | 사용자 미입력 시 dry-run (줄 165) |
| **API 응답 key** | ✓ 변경 없음 | 기존 response interface 유지 |
| **cleanup executor** | ✓ 미수정 | Python 로직 변경 없음 |
| **stdin JSON 구조** | ✓ 유지 | spawn stdin 사용 유지 |

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

### 5.3 코드 검토

**SEC-FIX-2A resolveCleanupExecutorPath와 일관성:**
- resolveRepoRoot() 후보 경로 구조 유사
- fs.existsSync로 존재 여부 검증
- 고정 경로만 사용

**Python 환경 설정:**
- cwd: repo root (Python 실행 디렉터리)
- PYTHONPATH: repo root 포함
- 기존 PYTHONPATH 유지 (기존 설정 존중)

---

## 6. 남은 비즈니스 검증

**다음 단계에서 검증:**
- dry_run=true spawn 실행 및 Python 모듈 import 확인
- ModuleNotFoundError 해소 확인
- cleanup executor Python 로직 정상 실행 확인
- run_id 생성 및 response 정상 여부

현재 코드 수정은 완료. 비즈니스 검증은 admin-web server 정상 시작 후 진행.

---

## 7. 수정된 파일

| 파일 | 변경 | 설명 |
|------|------|------|
| admin-web/src/app/api/file-map/cleanup-execute/route.ts | ✓ 수정 | resolveRepoRoot() 추가, spawn cwd/env 설정 |
| docs/reports/local_file_map_sec_fix_2b_pythonpath.md | ✓ 신규 | 이 보고서 |

---

## 8. 금지 위반 여부

| 항목 | 상태 | 설명 |
|------|------|------|
| 실제 사용자 파일 이동 | ✓ 없음 | dry_run=false 미실행 |
| dry_run=false 실행 | ✓ 없음 | dry_run=true만 검증 계획 |
| fixture 파일 이동 | ✓ 없음 | 실제 파일 이동 미실행 |
| 삭제 명령 | ✓ 없음 | 파일 삭제 미실행 |
| 자동 롤백 실행 | ✓ 없음 | 롤백 미실행 |
| API 응답 key 변경 | ✓ 없음 | 기존 key 유지 |
| 승인 정책 변경 | ✓ 없음 | token validation 유지 |
| cleanup 로직 변경 | ✓ 없음 | spawn/stdin 구조 유지 |
| Python executor 변경 | ✓ 없음 | cleanup_executor_api.py 미수정 |
| package-lock 수정 | ✓ 없음 | 미수정 |
| local_file_map.json 수정 | ✓ 없음 | 미수정 |
| shell: true | ✓ 없음 | spawn 기본값 (shell 없음) |
| 사용자 입력 경로 | ✓ 없음 | 고정 경로만 사용 |
| 다른 앱/repo | ✓ 없음 | admin-web만 수정 |

---

## 9. 다음 단계 (BETA-OPS-2D 재개)

### 준비 완료:
- ✓ resolveRepoRoot() 함수 추가
- ✓ spawn cwd 설정
- ✓ PYTHONPATH 설정
- ✓ typecheck 통과
- ✓ build 통과

### 이제:
1. admin-web npm run dev 또는 npm run start 정상 시작
2. cleanup-preflight + cleanup-execute (dryrun=true) smoke 테스트
3. ModuleNotFoundError 해소 확인
4. Python 환경 설정 완료 판단

---

## 10. 최종 판정

✅ **PASS** — Python module import 경로 보정 완료

**근거:**
- ✓ resolveRepoRoot() 함수 구현 (고정 후보 경로, fs.existsSync 검증)
- ✓ spawn cwd 설정 (repoRoot 명시)
- ✓ PYTHONPATH 설정 (repoRoot 포함, 기존 경로 유지)
- ✓ typecheck 통과
- ✓ build 통과
- ✓ 보안 요구사항 만족 (shell 없음, 사용자 입력 미포함)
- ✓ 금지 사항 위반 없음

**다음:**
- BETA-OPS-2D: admin-web 정상 시작 후 dry_run fixture 재검증

---

## 11. 코드 변경 요약

**추가:**
- resolveRepoRoot(): repo root 계산 함수

**수정:**
- callPythonExecutor: spawn에 cwd/env 추가

**유지:**
- 기존 spawn stdin JSON 구조
- 기존 approval token 검증
- 기존 API response interface
- 기존 Python executor 로직
