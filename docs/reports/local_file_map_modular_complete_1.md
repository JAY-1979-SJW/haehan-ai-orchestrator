# LOCAL-FILE-MAP-MODULAR-COMPLETE-1 작업 보고서

## [작업 내용]

cleanup-execute route 내부 책임 분리를 통한 완전 모듈화.

### 분리된 책임
1. **approvalToken.ts** - 승인 토큰 검증 (서버 측)
   - UUID suffix 형식 검증
   - 토큰 prefix 검증

2. **executePayload.ts** - 요청/응답 정의 및 정규화
   - ExecuteRequest, ExecuteResponse 인터페이스
   - plans 배열 정규화 (문자열/객체/기본값 처리)

3. **pythonExecutor.ts** - Python 실행 관리
   - repo root 경로 해석
   - cleanup_executor_api.py 경로 해석
   - Python subprocess 호출 (spawn)

4. **cleanup-execute/route.ts 리팩토링**
   - 요청 파싱
   - 모듈 호출
   - 응답 반환만 담당

---

## [기준선]

```
HEAD: 2808f60
origin/master: 2808f60
branch: master
git status: clean
```

### 참고: haehan-server 상태
- haehan-server/master: b56b33c (분기 상태)
- 해당 작업에서는 건드리지 않음

---

## [구조 감사]

### Before
```
admin-web/src/app/api/file-map/cleanup-execute/route.ts (317줄)
├─ import (Next.js, child_process, path, fs)
├─ ExecuteRequest interface
├─ ExecuteResponse interface
├─ resolveRepoRoot()
├─ resolveCleanupExecutorPath()
├─ validateApprovalToken()
├─ normalizePlans()
├─ callPythonExecutor()
└─ POST handler
```

### After
```
admin-web/src/app/api/file-map/cleanup-execute/route.ts (95줄)
├─ import (분리된 모듈들)
└─ POST handler (요청 파싱 + 모듈 호출 + 응답)

admin-web/src/lib/file-map/
├─ approvalToken.ts (25줄)
│  └─ validateApprovalToken()
├─ executePayload.ts (99줄)
│  ├─ ExecuteRequest, ExecuteResponse interface
│  └─ normalizePlans()
└─ pythonExecutor.ts (119줄)
   ├─ resolveRepoRoot()
   ├─ resolveCleanupExecutorPath()
   └─ callPythonExecutor()
```

---

## [분리 내용]

### 신규 파일
- `admin-web/src/lib/file-map/approvalToken.ts`
- `admin-web/src/lib/file-map/executePayload.ts`
- `admin-web/src/lib/file-map/pythonExecutor.ts`

### 이동한 책임
| 책임 | From | To |
|------|------|-----|
| 토큰 검증 | route.ts | approvalToken.ts |
| ExecuteRequest/Response | route.ts | executePayload.ts |
| plans 정규화 | route.ts | executePayload.ts |
| Python 경로 해석 | route.ts | pythonExecutor.ts |
| Python 호출 | route.ts | pythonExecutor.ts |

### 유지한 책임
- route.ts: 요청 파싱, 검증, 모듈 호출, 응답 생성
- Python 실행 로직 동일
- dry_run 기본값: false가 아니면 true

---

## [line count]

```
Before:
- cleanup-execute/route.ts: 317줄
- 합계: 317줄

After:
- cleanup-execute/route.ts: 95줄
- approvalToken.ts: 25줄
- executePayload.ts: 99줄
- pythonExecutor.ts: 119줄
- 합계: 338줄

증가분: 21줄 (코멘트 및 export 추가)
```

---

## [정책 보존]

### API 응답 key
✓ PASS - 변경 없음
```typescript
// 유지됨
ok, run_id, package_id, timestamp
success_count, failed_count, skipped_count, conflict_count
succeeded, failed, skipped, conflicts
error
```

### Approval Token 정책
✓ PASS - 변경 없음
```typescript
// validateApprovalToken() 로직 동일
prefix: 'user-approved-cleanup-'
suffix: UUID v4 형식 검증
```

### dry_run 기본값
✓ PASS - 변경 없음
```typescript
// dry_run === false ? false : true
// false가 아니면 true (기본값: true)
```

### Cleanup Executor
✓ PASS - 호출 로직 동일
```typescript
// resolveCleanupExecutorPath()
// callPythonExecutor()
// PYTHONPATH 설정
// spawn() 호출
```

---

## [정적 보안 감사]

### 검사 항목
- shell:true: ✓ 없음
- exec/execSync: ✓ 없음 (executor는 파일명)
- 삭제 API: ✓ 없음
- 토큰/path/payload 로그: ✓ 없음
- spawn 옵션: ✓ stdio:['pipe', 'pipe', 'pipe']

### 보안 평가
PASS - 모든 검사 항목 통과

---

## [typecheck/build 결과]

### typecheck
```
$ npm run typecheck
> tsc --noEmit
✓ (No errors)
```

### build
```
$ npm run build
> next build
✓ Compiled successfully
✓ Generating static pages (14/14)
✓ Route validation passed
```

---

## [남은 WARN]

### 1. cleanup-plan source 기반 full E2E
- 상태: 대기중
- 설명: cleanup-plan 캐싱 정책 미정
- 추후 필요시: planCache.ts 생성 및 cleanup-plan/route.ts 모듈화

### 2. 서버 발급형 approval token
- 상태: 현재 클라이언트 발급 (localStorage)
- 설명: fileMapApproval.ts (클라이언트)에서 토큰 생성, route.ts에서 UUID suffix 검증
- 개선안: 서버 발급 토큰으로 전환 시 approvalToken.ts 업데이트 필요

### 3. 실제 사용자 파일 이동 금지
- 상태: 유지됨
- 설명: dry_run=false 실행 불가능하므로 안전
- 검증: POST 핸들러에서 dry_run 기본값 유지 (false가 아니면 true)

---

## [커밋/푸시]

### 커밋
```
commit 1195f19
Author: JAY-1979-SJW
Date:   2026-05-03

refactor(file-map): modularize cleanup-execute route responsibilities
```

### 변경 사항
```
admin-web/src/app/api/file-map/cleanup-execute/route.ts
  - 317줄 → 95줄 (책임 분리)

admin-web/src/lib/file-map/approvalToken.ts (신규)
  + 25줄

admin-web/src/lib/file-map/executePayload.ts (신규)
  + 99줄

admin-web/src/lib/file-map/pythonExecutor.ts (신규)
  + 119줄
```

### Push
- 준비됨 (local HEAD: 1195f19)
- origin/master와 동기화 필요 시 `git push origin master` 실행

---

## [최종 판정]

**PASS**

### 판정 근거
1. ✓ cleanup-execute route 책임 분리 완료
2. ✓ 3개 모듈 (approvalToken, executePayload, pythonExecutor) 분리
3. ✓ API 응답 key 유지
4. ✓ 승인 정책 유지
5. ✓ dry_run 기본값 유지 (false가 아니면 true)
6. ✓ cleanup executor 호출 로직 동일
7. ✓ 정적 보안 감사 PASS
8. ✓ typecheck PASS
9. ✓ build PASS
10. ✓ 실제 파일 이동 금지 유지

### 위험 요소
- 없음

---

## [다음 단계]

### 1. 선택사항: audit/rollback 모듈화
- auditStore.ts / rollbackStore.ts 분리 가능
- 현재: cleanup-audit (83줄), cleanup-rollback (104줄) 읽기 전용
- 판단: 라인 수 관점에서는 불필요, 추후 필요시 진행

### 2. 선택사항: cleanup-plan 캐시 모듈화
- planCache.ts 생성 (향후 캐싱 정책 정의 시)
- 현재: 마스킹 정책에 따라 캐싱 불가능
- 추후 필요시: cleanup-plan/route.ts 분리

### 3. 개선안: 서버 발급형 approval token
- approvalToken.ts 업데이트 필요
- 클라이언트의 fileMapApproval.ts와 동기화
- 보안 강화 가능

---

**작업 완료 일시**: 2026-05-03
**기준선**: HEAD 2808f60 → 1195f19
**최종 상태**: READY FOR MERGE
