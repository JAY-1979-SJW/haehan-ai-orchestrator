# LOCAL-FILE-MAP-AUTO-CONTROL-1 자동 제어 상태 보고서

**생성 일시**: 2026-05-03 14:57:36
**기준선**: f269b0d
**종합 판정**: WARN

---

## 감사 결과 요약

| 감사 항목 | 상태 | 세부 |
|---------|------|------|
| 모듈화 | WARN | 5개 파일 초과 |
| 보안 | PASS | 0개 이슈 발견 |
| Component | PASS | 350줄 초과 0개 |

---

## 모듈화 감사

### 상태: WARN

**집계**:
- 총 파일 수: 69
- 총 라인 수: 9046
- 기준 초과: 5개

**기준**:
- API route: 150줄 이하
- Server lib: 250줄 이하
- Client lib: 200줄 이하
- React component: 350줄 이하
- Python module: 350줄 이하

**기준 초과 파일**:
- API Routes: admin-web\src\app\api\file-map\cleanup-approval-request\route.ts (406 / 150 줄, +256)
- API Routes: admin-web\src\app\api\file-map\cleanup-execution-package\route.ts (522 / 150 줄, +372)
- API Routes: admin-web\src\app\api\file-map\cleanup-preview\route.ts (250 / 150 줄, +100)
- API Routes: admin-web\src\app\api\file-map\report\route.ts (228 / 150 줄, +78)
- Python Modules: agent\local_inventory\file_map\cleanup_planner.py (364 / 350 줄, +14)

---

## 보안 정적 감사

### 상태: PASS

**집계**:
- 스캔 파일: 63개
- 발견 이슈: 0개

**검사 항목**:
- shell: true / shell=True ✓
- exec() / execSync ✓
- fs.rm / fs.unlink / fs.rmdir ✓
- os.remove / shutil.rmtree ✓
- local_file_map.json write ✓
- token/payload console.log ✓
- auto rollback ✓

**발견된 이슈**: 없음 ✓

---

## Component Line Count 감사

### 상태: PASS

**집계**:
- 총 component: 28개
- 총 라인: 2904줄
- 평균: 103줄/파일
- 350줄 초과: 0개
- 400줄 초과: 0개

**상위 10개 큰 Component**:
- admin-web\src\components\file-map\FileMapCleanupPreview.tsx: 302줄
- admin-web\src\components\file-map\FileMapCleanupPlanViewer.tsx: 250줄
- admin-web\src\components\file-map\FileMapReportViewer.tsx: 209줄
- admin-web\src\components\file-map\FileMapExecutionPackage.tsx: 199줄
- admin-web\src\components\file-map\FileMapPreflight.tsx: 184줄
- admin-web\src\components\file-map\FileMapExecute.tsx: 179줄
- admin-web\src\components\file-map\FileMapApprovalRequest.tsx: 176줄
- admin-web\src\components\file-map\FileMapAuditLog.tsx: 153줄
- admin-web\src\components\file-map\FileMapExecuteFlow.tsx: 151줄
- admin-web\src\components\file-map\approval\ApprovalGroupsList.tsx: 144줄

---

## 다음 단계

1. FAIL 항목 수정 필요
2. WARN 항목 검토 및 개선
3. 자동 점검 스크립트 정기 실행 (CI/CD 통합)
4. fixture 기반 smoke test 추가
5. 실제 사용자 파일 이동 테스트 (별도 sandbox 환경)

---

**최종 판정**: WARN
**검증 시점**: 2026-05-03T14:57:36.326922
