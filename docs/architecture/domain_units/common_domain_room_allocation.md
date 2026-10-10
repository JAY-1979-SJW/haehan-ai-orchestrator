# 공통 Domain 집 배정표 (Hiworks / Google / YouTube / CAD / HWPX / 문서자동화 / 출퇴근 / 위험성평가)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_DOMAIN_ROOM_ALLOCATION_01  
상태: LOCKED

cross-domain 직접 import 금지: 각 도메인 간 직접 import 금지. 공용시설(site_engine, local_agent) 경유만 허용.

---

## 1. Hiworks

**경로:** `scripts/hiworks/`  
**현황:** router/profile/gates/validators/actions/workflows ✅ (가장 완성도 높음)

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | 메일 수신함 조회, 공지사항 조회 | READ_ONLY_ALLOWED |
| read-only | 결재 목록 조회, 근태 현황 조회 | READ_ONLY_ALLOWED |
| draft | 메일 초안 작성, 결재 초안 생성 | DRAFT_ALLOWED |
| write | 메일 발송, 결재 상신 | APPROVAL_REQUIRED |
| submit/sign | 결재 승인/반려 | USER_DIRECT_REQUIRED |
| local-agent | 로컬 메일 배치 발송 | LOCAL_AGENT_REQUIRED |
| blocked | session/cookie 자동 로그인, 결재 자동 처리 | BLOCKED |

| 방 | 파일 | 현황 |
|----|------|------|
| router | `scripts/hiworks/router.py` | ✅ |
| profile | `scripts/hiworks/site_profile.py` | ✅ |
| gates | `scripts/hiworks/gates.py` | ✅ |
| validators | `scripts/hiworks/validators.py` | ✅ |
| usecase | `scripts/hiworks/actions.py`, `service_explorer.py` | ✅ |
| workflow | `scripts/hiworks/workflows.py` | ✅ |
| adapter | `scripts/hiworks/mail.py`, `mail_batch.py` | ✅ |
| storage | `data/hiworks/` | ❌ (미정) |
| test | `tests/test_hiworks_*.py` | ✅ |
| docs | 미작성 | ❌ |

---

## 2. Google

**경로:** `scripts/google/`  
**현황:** router/profile/gates/validators/workflows + Drive/Docs/Gmail/Calendar/Sheets API ✅

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | Drive 파일 목록, Docs 읽기, Gmail 수신 조회 | READ_ONLY_ALLOWED |
| read-only | Calendar 일정 조회, Sheets 읽기 | READ_ONLY_ALLOWED |
| draft | Docs 초안 생성, 메일 초안 | DRAFT_ALLOWED |
| write | Docs 편집, Sheets 수정, 파일 업로드 | APPROVAL_REQUIRED |
| submit/sign | Gmail 발송, Calendar 초대 발송 | USER_DIRECT_REQUIRED |
| local-agent | 로컬 파일 → Drive 업로드 | LOCAL_AGENT_REQUIRED |
| blocked | Google 계정 비밀번호 자동 입력, 2FA 자동 처리 | BLOCKED |

| 방 | 파일 | 현황 |
|----|------|------|
| router | `scripts/google/router.py` | ✅ |
| profile | `scripts/google/site_profile.py` | ✅ |
| gates | `scripts/google/gates.py` | ✅ |
| validators | `scripts/google/validators.py` | ✅ |
| usecase | `scripts/google/common/workflows.py`, `surfaces.py` | ✅ |
| adapter | `scripts/google/*_api.py` (gmail_api, drive_api 등) | ✅ |
| storage | `data/google/` | ❌ (미정) |
| test | `tests/test_google_*.py` | ✅ |
| docs | 미작성 | ❌ |

---

## 3. YouTube

**경로:** `scripts/youtube/`  
**현황:** router/profile/gates/validators ✅ / uploader/recording ✅

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | 채널 통계 조회, 동영상 목록 조회 | READ_ONLY_ALLOWED |
| draft | 업로드 초안 생성, 자막 초안 | DRAFT_ALLOWED |
| write | 동영상 메타데이터 수정 | APPROVAL_REQUIRED |
| submit/sign | 동영상 업로드, 게시 | USER_DIRECT_REQUIRED |
| local-agent | 로컬 파일 업로드 | LOCAL_AGENT_REQUIRED |
| blocked | 자동 대량 업로드, 계정 자동 로그인 | BLOCKED |

| 방 | 파일 | 현황 |
|----|------|------|
| router | `scripts/youtube/router.py` | ✅ |
| profile | `scripts/youtube/site_profile.py` | ✅ |
| gates | `scripts/youtube/gates.py` | ✅ |
| validators | `scripts/youtube/validators.py` | ✅ |
| usecase | `scripts/youtube/recording.py`, `uploader.py` | ✅ |
| storage | `data/youtube/` | ❌ (미정) |
| test | `tests/test_youtube_*.py` | ✅ |
| docs | 미작성 | ❌ |

---

## 4. CAD (CAD 파일 자동화)

**경로:** `scripts/local_agent/g2b/` (임시), 별도 집 미생성  
**현황:** local_agent 경유 구현, 독립 집 없음

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | DWG/DXF 파일 읽기, 레이어 목록 조회 | LOCAL_AGENT_REQUIRED |
| draft | 도면 초안 편집, 레이어 수정 계획 생성 | LOCAL_AGENT_REQUIRED |
| write | 도면 편집, 저장 | LOCAL_AGENT_REQUIRED |
| submit/sign | 도면 제출, 서명 | USER_DIRECT_REQUIRED |
| local-agent | 모든 CAD 작업 | LOCAL_AGENT_REQUIRED |
| blocked | 서버 사이드 CAD 파일 직접 편집 자동화 | BLOCKED |

| 방 | 파일 | 현황 |
|----|------|------|
| router | 미생성 | ❌ |
| profile | 미생성 | ❌ |
| gates | 미생성 | ❌ |
| validators | 미생성 | ❌ |
| usecase | `scripts/local_agent/g2b/` (부분) | 부분 |
| storage | `data/cad/` | ❌ |
| test | `tests/test_cad_*.py` | ✅ (구조 테스트) |
| docs | 미작성 | ❌ |

**필요 작업:** `scripts/cad/` 독립 집 생성, profile/gates/validators/router 작성

---

## 5. HWPX (HWP/HWPX 문서 자동화)

**경로:** 미생성  
**현황:** 집 없음

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | HWP 내용 조회, 표 추출 | LOCAL_AGENT_REQUIRED |
| draft | 문서 초안 생성, 빈 양식 채우기 계획 | LOCAL_AGENT_REQUIRED |
| write | 문서 편집, 저장 | LOCAL_AGENT_REQUIRED |
| submit/sign | 전자 제출, 서명 | USER_DIRECT_REQUIRED |
| local-agent | 모든 HWPX 작업 | LOCAL_AGENT_REQUIRED |
| blocked | 서버 사이드 HWPX 자동 편집 | BLOCKED |

| 방 | 파일 | 현황 |
|----|------|------|
| router | 미생성 | ❌ |
| profile | 미생성 | ❌ |
| gates | 미생성 | ❌ |
| validators | 미생성 | ❌ |
| usecase | 미생성 | ❌ |
| storage | `data/hwpx/` | ❌ |
| test | 미생성 | ❌ |
| docs | 미작성 | ❌ |

**필요 작업:** `scripts/hwpx/` 독립 집 전체 생성

---

## 6. 문서 자동화 (Document Automation)

**경로:** 미생성 (기능 일부가 google/, hiworks/, scripts/ 루트에 산재)  
**현황:** 독립 집 없음

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | 템플릿 목록 조회, 입력 변수 확인 | READ_ONLY_ALLOWED |
| draft | 문서 초안 자동 생성 (Google Docs / HWPX / HWP) | DRAFT_ALLOWED |
| write | 초안 → 완성본 저장 | APPROVAL_REQUIRED |
| submit/sign | 완성본 제출, 서명 | USER_DIRECT_REQUIRED |
| local-agent | 로컬 파일 생성 | LOCAL_AGENT_REQUIRED |
| blocked | 자동 발송, 자동 서명 | BLOCKED |

| 방 | 파일 | 현황 |
|----|------|------|
| router | 미생성 | ❌ |
| profile | 미생성 | ❌ |
| gates | 미생성 | ❌ |
| usecase | 산재 | 부분 |
| storage | `data/documents/` | ❌ |
| test | 미생성 | ❌ |
| docs | 미작성 | ❌ |

---

## 7. 출퇴근 앱 (Attendance App)

**경로:** 미생성  
**현황:** Hiworks 출퇴근 기능 일부 포함

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | 출퇴근 현황 조회, 근태 통계 | READ_ONLY_ALLOWED |
| draft | 근태 정정 신청 초안 | DRAFT_ALLOWED |
| write | 근태 정정 제출 | APPROVAL_REQUIRED |
| submit/sign | 근태 서명, 확인 | USER_DIRECT_REQUIRED |
| local-agent | 로컬 장치 기반 자동 체크인 (허용 범위 내) | LOCAL_AGENT_REQUIRED |
| blocked | 자동 출퇴근 기록 위조 | BLOCKED |

---

## 8. 위험성평가 / 안전서류 (Risk Assessment / Safety Docs)

**경로:** 미생성  
**현황:** 집 없음

| 기능 유형 | 기능명 | gate decision |
|----------|--------|--------------|
| read-only | 위험성평가 목록 조회, 안전서류 현황 조회 | READ_ONLY_ALLOWED |
| draft | 위험성평가 초안 생성, 안전서류 양식 작성 | DRAFT_ALLOWED |
| write | 초안 저장, 보완 | APPROVAL_REQUIRED |
| submit/sign | 제출, 서명 | USER_DIRECT_REQUIRED |
| local-agent | 로컬 파일 기반 서류 생성 | LOCAL_AGENT_REQUIRED |
| blocked | 서명 자동화, 관계기관 자동 제출 | BLOCKED |

---

## 9. 현황 종합

| 도메인 | 독립 집 | router | profile/gates/validators | usecase | test |
|--------|---------|--------|--------------------------|---------|------|
| Hiworks | ✅ | ✅ | ✅ | ✅ | ✅ |
| Google | ✅ | ✅ | ✅ | ✅ | ✅ |
| YouTube | ✅ | ✅ | ✅ | ✅ | ✅ |
| CAD | ❌ | ❌ | ❌ | 부분 | ✅ |
| HWPX | ❌ | ❌ | ❌ | ❌ | ❌ |
| 문서 자동화 | ❌ | ❌ | ❌ | 부분 | ❌ |
| 출퇴근 앱 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 위험성평가/안전서류 | ❌ | ❌ | ❌ | ❌ | ❌ |
