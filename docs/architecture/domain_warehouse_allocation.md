# Domain별 창고 배정표 (Domain Warehouse Allocation)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_SHARED_WAREHOUSE_LOCK_01  
상태: LOCKED

기본 경로 패턴: `data/{warehouse}/{domain}/{task_id}/`  
session/cookie/token/password 저장 금지 — 모든 domain에 공통 적용

---

## 1. gabia

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/gabia/{task_id}/` | domain 초안, DNS 변경 계획 초안 | session 저장 |
| Approval | `data/approvals/gabia/{task_id}/` | DNS 변경 승인, 도메인 등록 승인 | 결제 자동화 |
| Evidence | `data/evidence/gabia/{task_id}/` | DNS 조회 결과 스냅샷, nslookup 결과 | session/cookie 포함 금지 |
| Report | `data/reports/gabia/`, `docs/reports/` | DNS 현황 보고서, 도메인 감사 보고서 | - |
| Artifact | `data/artifacts/gabia/{task_id}/` | 도메인 후보 목록, DNS 레코드 초안 | 실제 DNS 변경 파일 금지 |
| Manual Visit | `data/manual_visits/accounts.gabia.com/`, `data/manual_visits/dns.gabia.com/`, `data/manual_visits/my.gabia.com/` | read-only 스냅샷 | 자동화 재사용 금지 |
| Session | `data/sessions/gabia.com.json`, `data/sessions/my.gabia.com.json` | **BLOCKED** | 읽기/파싱/재사용 금지 |

---

## 2. g2b

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/g2b/{task_id}/` | 입찰 분석 초안, 서류 초안 | 투찰 자동화 |
| Approval | `data/approvals/g2b/{task_id}/` | 입찰 참여 승인 | 전자서명 자동화 |
| Evidence | `data/evidence/g2b/{task_id}/` | 공고 조회 결과, 다운로드 첨부파일 해시 | session 포함 금지 |
| Report | `data/reports/g2b/`, `docs/reports/` | 공고 분석 보고서, 입찰 결과 보고서 | - |
| Artifact | `data/artifacts/g2b/{task_id}/` | 다운로드 파일, 공고 PDF | 투찰서 자동 생성 금지 |
| Upload | `data/uploads/g2b/{task_id}/` | 입찰 서류 원본 | 원본 수정 금지 |

---

## 3. hiworks

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/hiworks/{task_id}/` | 메일 초안, 결재 초안 | 자동 발송 |
| Approval | `data/approvals/hiworks/{task_id}/` | 메일 발송 승인, 결재 상신 승인 | 결재 자동 처리 |
| Evidence | `data/evidence/hiworks/{task_id}/` | 메일 발송 결과, 결재 완료 증거 | session/cookie 포함 금지 |
| Report | `data/reports/hiworks/`, `docs/reports/` | 메일 발송 리포트, 결재 현황 보고서 | - |
| Artifact | `data/artifacts/hiworks/{task_id}/` | 메일 첨부 파일, 결재 문서 | - |
| Session | `data/sessions/office.hiworks.com.json` | **BLOCKED** | 읽기/파싱/재사용 금지 |

---

## 4. google

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/google/{task_id}/` | Docs 초안, Sheets 초안, 메일 초안 | 자동 발송 |
| Approval | `data/approvals/google/{task_id}/` | Drive 업로드 승인, 메일 발송 승인 | - |
| Evidence | `data/evidence/google/{task_id}/` | API 응답 결과, 파일 업로드 증거 | session/cookie 포함 금지 |
| Report | `data/reports/google/`, `docs/reports/` | Drive 현황 보고서, Calendar 보고서 | - |
| Artifact | `data/artifacts/google/{task_id}/` | 생성 문서, 변환 파일, 다운로드 | - |
| Manual Visit | `data/manual_visits/accounts.google.com/` 등 | read-only 스냅샷 | 자동화 재사용 금지 |

---

## 5. youtube

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/youtube/{task_id}/` | 업로드 계획 초안, 자막 초안 | 자동 게시 |
| Approval | `data/approvals/youtube/{task_id}/` | 동영상 게시 승인 | - |
| Evidence | `data/evidence/youtube/{task_id}/` | 업로드 완료 증거, API 응답 | session/cookie 포함 금지 |
| Report | `data/reports/youtube/`, `docs/reports/` | 채널 현황 보고서, 업로드 결과 | - |
| Artifact | `data/artifacts/youtube/{task_id}/` | 업로드 파일, 자막 파일 | - |
| Upload | `data/uploads/youtube/{task_id}/` | 영상 원본 | 원본 수정 금지 |
| Manual Visit | `data/manual_visits/studio.youtube.com/` | read-only 스냅샷 | 자동화 재사용 금지 |

---

## 6. eum

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/eum/{task_id}/` | 단말기 설치 계획 초안, 영업 메일 초안 | 자동 설치 신청 |
| Approval | `data/approvals/eum/{task_id}/` | 업무 처리 승인 | - |
| Evidence | `data/evidence/eum/{task_id}/` | 단말기 현황 스냅샷, 조회 결과 | session/cookie 포함 금지 |
| Report | `data/reports/eum/`, `docs/reports/` | 단말기 현황 보고서, 영업 분석 보고서 | - |
| Artifact | `data/artifacts/eum/{task_id}/` | 생성 영업 메일, 단말기 목록 파일 | - |
| Manual Visit | `data/manual_visits/eum.cw.or.kr/` | read-only 스냅샷 | 자동화 재사용 금지 |
| Session | `data/sessions/eum.cw.or.kr.json` | **BLOCKED** | 읽기/파싱/재사용 금지 |

---

## 7. cad

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/cad/{task_id}/` | 도면 편집 계획 초안 | 서버 사이드 도면 편집 |
| Evidence | `data/evidence/cad/{task_id}/` | 도면 처리 결과 증거 | - |
| Report | `data/reports/cad/`, `docs/reports/` | 도면 처리 보고서 | - |
| Artifact | `data/artifacts/cad/{task_id}/` | 처리된 도면 파일 (로컬 에이전트 생성) | 원본 수정 금지 |
| Upload | `data/uploads/cad/{task_id}/` | 원본 도면 파일 | 원본 수정 금지 |

---

## 8. hwpx

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/hwpx/{task_id}/` | 문서 초안 | 서버 사이드 직접 편집 |
| Evidence | `data/evidence/hwpx/{task_id}/` | 처리 결과 증거 | - |
| Report | `data/reports/hwpx/`, `docs/reports/` | 문서 처리 보고서 | - |
| Artifact | `data/artifacts/hwpx/{task_id}/` | 처리된 HWP/HWPX 파일 | 원본 수정 금지 |
| Upload | `data/uploads/hwpx/{task_id}/` | 원본 HWP/HWPX 파일 | 원본 수정 금지 |

---

## 9. document_automation (문서 자동화)

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/document_automation/{task_id}/` | 문서 템플릿 초안 | 자동 서명/제출 |
| Approval | `data/approvals/document_automation/{task_id}/` | 문서 발행 승인 | - |
| Evidence | `data/evidence/document_automation/{task_id}/` | 문서 생성 증거 | - |
| Artifact | `data/artifacts/document_automation/{task_id}/` | 생성 문서 최종본 | 원본 수정 금지 |

---

## 10. attendance (출퇴근)

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/attendance/{task_id}/` | 근태 정정 초안 | 자동 위조 |
| Evidence | `data/evidence/attendance/{task_id}/` | 출퇴근 기록 증거 | 위조 금지 |
| Report | `data/reports/attendance/`, `docs/reports/` | 근태 현황 보고서 | - |

---

## 11. safety_docs / risk_assessment (안전서류 / 위험성평가)

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Draft | `data/drafts/safety_docs/{task_id}/` | 위험성평가 초안, 안전서류 초안 | 자동 서명/제출 |
| Approval | `data/approvals/safety_docs/{task_id}/` | 서류 발행 승인 | - |
| Evidence | `data/evidence/safety_docs/{task_id}/` | 서류 작성 증거 | - |
| Artifact | `data/artifacts/safety_docs/{task_id}/` | 완성 안전서류 | 원본 수정 금지 |
| Upload | `data/uploads/safety_docs/{task_id}/` | 원본 서류 파일 | 원본 수정 금지 |

---

## 12. common (공통)

| 창고 | 경로 | 허용 action | 금지 |
|------|------|------------|------|
| Manual Visit | `data/manual_visits/{host}/` | read-only 스냅샷 | 자동화 재사용, session 추출 |
| Audit Log | `data/logs/` | APPEND_ONLY | 수정/삭제 |
| Session Store | `data/sessions/` | **BLOCKED** | 읽기/파싱/재사용/신규 생성 |

---

## 13. 공통 금지 규칙

```
모든 domain 창고에 공통 적용:
- session/cookie/token/password 저장 금지
- secret/env 값 저장 금지
- task_id 없는 창고 사용 금지 (레거시 제외)
- 원본 파일 자동 수정 금지
- evidence 삭제/수정 금지
- data/sessions 읽기/파싱/재사용 금지
```
