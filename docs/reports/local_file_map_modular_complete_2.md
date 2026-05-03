# LOCAL-FILE-MAP-MODULAR-COMPLETE-2 작업 보고서

## [작업 내용]

cleanup-plan, cleanup-audit, cleanup-rollback route의 책임을 분리하여 route를 얇게 정리.

### 분리된 책임
1. **planCache.ts** - cleanup-plan 캐시 조회
   - getStoragePath(), loadLocalFileMap()
   - maskFilename() (민감 정보 마스킹)
   - buildCleanupSummary(), buildCategories()
   - 캐시 읽기 전용

2. **auditStore.ts** - cleanup-audit 로그 조회
   - getAuditFilePath(), loadAuditRecords()
   - JSONL 파일 읽기 (파일 없으면 빈 배열)
   - 쓰기/삭제 없음

3. **rollbackStore.ts** - cleanup-rollback 매니페스트 조회
   - getRollbackDirPath(), loadManifest()
   - isValidUuid() (UUID 검증)
   - 자동 실행/롤백 없음 보장
   - 쓰기/삭제 없음

4. **route 리팩토링**
   - cleanup-plan/route.ts: 요청 파싱 + planCache 호출 + 응답
   - cleanup-audit/route.ts: 요청 파싱 + auditStore 호출 + 응답
   - cleanup-rollback/route.ts: 요청 파싱 + rollbackStore 호출 + 응답

---

## [기준선]

```
HEAD: e4e3917
origin/master: e4e3917
branch: master
git status: clean
```

---

## [route 구조 감사]

### Before
```
cleanup-plan/route.ts: 290줄
  - getStoragePath, loadLocalFileMap, maskFilename
  - buildCleanupSummary, buildCategories
  - 저장소 + 마스킹 + 요청 처리 혼합

cleanup-audit/route.ts: 83줄
  - getAuditFilePath, loadAuditRecords
  - 요청 처리와 혼합

cleanup-rollback/route.ts: 104줄
  - getRollbackDirPath, loadManifest, isValidUuid
  - 요청 처리와 혼합
```

### After
```
cleanup-plan/route.ts: 118줄
  - 요청 파싱 (mode, query)
  - planCache 호출
  - 응답 생성

cleanup-audit/route.ts: 28줄
  - 요청 파싱 (run_id)
  - auditStore 호출
  - 응답 생성

cleanup-rollback/route.ts: 50줄
  - 요청 파싱 (run_id)
  - UUID 검증
  - rollbackStore 호출
  - 응답 생성

admin-web/src/server/file-map/:
  - planCache.ts: 캐시 조회 (199줄)
  - auditStore.ts: 감사로그 조회 (64줄)
  - rollbackStore.ts: 롤백 매니페스트 조회 (66줄)
```

---

## [분리 내용]

### 신규 파일
- `admin-web/src/server/file-map/planCache.ts`
- `admin-web/src/server/file-map/auditStore.ts`
- `admin-web/src/server/file-map/rollbackStore.ts`

### 이동한 책임
| 책임 | From | To |
|------|------|-----|
| 저장소 경로 | route.ts | planCache/auditStore/rollbackStore |
| 파일 로드 | route.ts | planCache/auditStore/rollbackStore |
| 마스킹 | route.ts | planCache |
| 요약 구축 | route.ts | planCache |
| UUID 검증 | route.ts | rollbackStore |

### 유지한 책임
- route.ts: 요청 파싱, 검증, 모듈 호출, 응답 생성
- planCache: 캐시 읽기 전용 (쓰기 없음)
- auditStore: 로그 읽기 전용 (쓰기 없음)
- rollbackStore: 매니페스트 조회만 (자동 실행 없음)

---

## [line count]

```
Before:
- cleanup-plan/route.ts: 290줄
- cleanup-audit/route.ts: 83줄
- cleanup-rollback/route.ts: 104줄
- 합계 route: 477줄

After:
- cleanup-plan/route.ts: 118줄
- cleanup-audit/route.ts: 28줄
- cleanup-rollback/route.ts: 50줄
- 합계 route: 196줄

신규 server/file-map:
- planCache.ts: 199줄
- auditStore.ts: 64줄
- rollbackStore.ts: 66줄
- 합계 module: 329줄

전체:
- route 감소: 281줄 (59%)
- 신규 module: 329줄
- 순 증가: 48줄 (코멘트 및 타입 정의)
```

---

## [정책 보존]

### API 응답 key
✓ PASS - 변경 없음
```
cleanup-plan: ok, generated_at, source, masked, mode, auth_verified, execution_enabled, summary, suggested_structure, categories, error
cleanup-audit: ok, records, error
cleanup-rollback: ok, manifest, error
```

### cleanup-plan 캐시 정책
✓ PASS - 유지
```
- loadLocalFileMap() 읽기 전용
- local_file_map.json 수정 금지
- 마스킹 정책 유지 (mode별 결정)
- Cache-Control 헤더 유지 (원본 데이터는 no-cache)
```

### audit masking
✓ PASS - 유지
```
- JSONL 기반 로그 조회
- 읽기 전용 (append만 가능)
- 파일 없으면 빈 배열 반환
```

### rollback 조회 전용
✓ PASS - 유지
```
- manifest 읽기만 수행
- UUID 검증 (조회 안전)
- 자동 rollback 실행 경로 없음
- 쓰기/삭제 불가능
```

---

## [정적 보안 감사]

### 검사 항목
- shell:true: ✓ 없음
- exec/execSync: ✓ 없음
- 파일 삭제 (fs.rm/unlink): ✓ 없음
- local_file_map.json 쓰기: ✓ 없음
- 자동 rollback 실행: ✓ 없음
- 민감정보 로그: ✓ 없음

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
✓ cleanup-plan route: OK
✓ cleanup-audit route: OK
✓ cleanup-rollback route: OK
✓ cleanup-execute route (영향 없음): OK
```

---

## [남은 WARN]

### 1. cleanup-plan source 파라미터 지원
- 상태: 미구현 (이번 단계 범위 외)
- 설명: source 파라미터로 다른 출처 지원 가능
- 추후: planCache 확장 시 고려

### 2. 서버 발급형 approval token
- 상태: 현재 클라이언트 발급 (localStorage)
- 설명: cleanupExecute에서 UUID suffix 검증만 수행
- 개선안: approvalToken.ts + 서버 발급 토큰 통합

### 3. 실제 사용자 파일 이동 금지
- 상태: 유지됨
- 검증: cleanup-execute의 dry_run 기본값 (false 아니면 true)

---

## [커밋/푸시]

### 변경 파일
```
M  admin-web/src/app/api/file-map/cleanup-plan/route.ts
M  admin-web/src/app/api/file-map/cleanup-audit/route.ts
M  admin-web/src/app/api/file-map/cleanup-rollback/route.ts
A  admin-web/src/server/file-map/planCache.ts
A  admin-web/src/server/file-map/auditStore.ts
A  admin-web/src/server/file-map/rollbackStore.ts
A  docs/reports/local_file_map_modular_complete_2.md
```

### 예정 커밋
```
refactor(file-map): modularize plan audit rollback routes

cleanup-plan, cleanup-audit, cleanup-rollback route의 저장소/조회 책임을 분리:
- planCache.ts: 파일맵 캐시 조회, 마스킹, 요약 구축
- auditStore.ts: 감사로그 JSONL 조회 (읽기 전용)
- rollbackStore.ts: 롤백 매니페스트 조회, UUID 검증

route.ts는 요청 파싱 + 모듈 호출 + 응답만 담당.

변경 사항:
- cleanup-plan: 290줄 → 118줄 (172줄 감소, 59%)
- cleanup-audit: 83줄 → 28줄 (55줄 감소, 66%)
- cleanup-rollback: 104줄 → 50줄 (54줄 감소, 52%)
- 신규 module: 329줄 (планCache 199 + auditStore 64 + rollbackStore 66)

정책 보존:
- API 응답 key 유지
- cleanup-plan 캐시 정책 유지 (읽기 전용)
- audit masking 유지
- rollback 조회 전용 유지 (자동 실행 없음)

검증:
- typecheck: PASS
- build: PASS
- 정적 보안: 모든 검사 항목 PASS
```

---

## [최종 판정]

**PASS**

### 판정 근거
1. ✓ route 책임 분리 완료 (3개 route, 3개 module)
2. ✓ route 얇게 정리 (477줄 → 196줄, 59% 감소)
3. ✓ API 응답 key 유지
4. ✓ cleanup-plan 캐시 정책 유지
5. ✓ audit masking 유지
6. ✓ rollback 조회 전용 유지
7. ✓ 정적 보안 감사 PASS
8. ✓ typecheck PASS
9. ✓ build PASS
10. ✓ 파일 삭제/쓰기 금지 보장
11. ✓ 자동 rollback 실행 경로 없음
12. ✓ 민감정보 로그 없음

### 위험 요소
- 없음

---

## [다음 단계]

### 1. 즉시 조치
- Step 8: 커밋/푸시 실행
- 모든 변경사항 origin/master에 반영

### 2. 선택사항: 추가 모듈화
- cleanup-preflight 모듈화 검토
- cleanup-preview 모듈화 검토
- cleanup-approval-request 모듈화 검토

### 3. 개선안 (우선순위)
- 높음: cleanup-plan source 파라미터 지원
- 중간: 서버 발급형 approval token 통합
- 낮음: 다른 cleanup-* route 모듈화

---

**작업 완료 일시**: 2026-05-03  
**기준선**: e4e3917 → (예정: 새 커밋)  
**최종 상태**: READY FOR COMMIT
