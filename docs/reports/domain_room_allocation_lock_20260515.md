# Domain Room Allocation Lock 보고서

작성일: 2026-05-15  
작업 ID: APP_FOUNDATION_DOMAIN_ROOM_ALLOCATION_01  
커밋 기준: aa43ebf → (이번 커밋)

---

## 1. 목적

전체 앱의 업무 기능을 세부 Domain Unit 단위로 나누고,  
각 기능이 들어갈 집/방/창고/출입문/게이트/테스트/보고서 위치를 확정한다.  
이후 신규 기능은 반드시 이 배정표 안에서만 생성된다.

---

## 2. 생성/고정한 문서

| 문서 | 경로 | 핵심 내용 |
|------|------|----------|
| Domain Room Allocation Rule | docs/architecture/domain_room_allocation_rule.md | 11개 필수 방·집 경계 금지선·gate decision 기준 |
| Gabia Room Allocation | docs/architecture/domain_units/gabia_room_allocation.md | 6개 세부 집·허용/금지 action·gate decision |
| G2B Room Allocation | docs/architecture/domain_units/g2b_room_allocation.md | 9개 세부 집·투찰/서명 BLOCKED·SERVER_BROWSER_GUARD |
| Common Domain Allocation | docs/architecture/domain_units/common_domain_room_allocation.md | Hiworks/Google/YouTube/CAD/HWPX/문서자동화/출퇴근/위험성평가 |
| Shared Facility Allocation | docs/architecture/shared_facility_allocation.md | 11개 공용시설·담당 책임·금지 접근·감사로그 |

---

## 3. 집 배정 기준 요약

### 필수 방 11개
```
entrance/router        → HTTP 진입점, 명령 분기만
resident-card/profile  → 사이트 프로필, capability 선언
security-door/gates    → gate 결정 (ALLOWED/BLOCKED/…)
inspection/validators  → 입력/응답 유효성 검사
living-room/usecase    → 업무 흐름, 초안 생성
external-door/adapter  → 외부 API, 브라우저 연동
parking/workflow       → 상태 기반 작업흐름
warehouse/storage      → 결과물, 증거, 아티팩트
cctv/audit             → 감사로그, 운영 리포트
alarm/tests            → 구조/기능 테스트
rulebook/docs          → 도메인 규칙, 집 배정표
```

### 집 경계 금지선
```
1. 다른 Domain Unit 직접 import 금지
2. router에서 DB 직접 접근 금지
3. adapter에서 타 도메인 adapter 체이닝 금지
4. storage 위치 불명확 금지
5. session/cookie/token/password 저장 금지
6. final submit/payment/sign 자동 실행 금지
```

---

## 4. Gabia 세부 집 배정 (6개)

| 집 | gate decision | USER_DIRECT | BLOCKED |
|----|--------------|-------------|---------|
| domain-registration | DRAFT_ALLOWED / USER_DIRECT_REQUIRED | ✅ 최종 등록 | session/OTP 자동화 |
| dns-management | READ_ONLY_ALLOWED / USER_DIRECT_REQUIRED | ✅ DNS 변경 | 서버 사이드 브라우저 |
| hosting-management | READ_ONLY_ALLOWED / USER_DIRECT_REQUIRED | ✅ 갱신/구매 | 결제 자동화 |
| mail-management | READ_ONLY_ALLOWED / USER_DIRECT_REQUIRED | ✅ 설정 변경 | 자동 발송 |
| account-readonly | READ_ONLY_ALLOWED | ❌ | 서버 사이드 로그인 |
| payment-billing | READ_ONLY_ALLOWED / BLOCKED | ✅ 결제 | 자동 결제 |

---

## 5. G2B 세부 집 배정 (9개)

| 집 | gate decision | BLOCKED |
|----|--------------|---------|
| public-notice | READ_ONLY_ALLOWED | 로그인 자동화 |
| notice-detail | READ_ONLY_ALLOWED | ❌ |
| attachment-download | READ_ONLY_ALLOWED / LOCAL_AGENT_REQUIRED | session 자동 로그인 |
| openapi-collector | READ_ONLY_ALLOWED | ❌ |
| login-restricted | LOCAL_AGENT_REQUIRED | 서버 사이드 G2B 로그인 |
| bid-analysis | DRAFT_ALLOWED | 입찰 자동 제출 |
| bid-submit | DRAFT_ALLOWED / BLOCKED | ✅ 투찰 자동화 |
| e-sign | BLOCKED | ✅ 전자서명 자동화 |
| evidence-report | ALLOWED / READ_ONLY_ALLOWED | ❌ |

---

## 6. 공용시설 배정 (11개)

Action Registry / Approval Gate / Permission Model / Workflow-Task Queue /  
Local Agent Gateway / Browser Execution Gateway / Evidence Store /  
Report Store / Audit Log / Admin Ops Center / Notification Center

---

## 7. 감사 스크립트 / 테스트

| 항목 | 결과 |
|------|------|
| `audit_domain_room_allocation.py` | 63/63 PASS |
| `test_domain_room_allocation.py` | 69/69 PASS |
| 기존 P1 gate 테스트 | 28/28 PASS |
| 기존 governance 테스트 | 50/50 PASS |
| 기존 Gabia 테스트 | 26/26 PASS |
| governance audit script | 82/82 PASS |
| layer audit (FORBIDDEN=0, SECURITY=0) | PASS |
| quality gate errors=0 / warnings=0 | PASS |

---

## 8. 안전 확인

| 항목 | 결과 |
|------|------|
| 기능 코드 변경 | 없음 (문서·감사 스크립트·테스트만) |
| DB/schema 변경 | 없음 |
| session/cookie 접근 | 없음 |
| secret/env 출력 | 없음 |
| 삭제/권한 변경 | 없음 |
| 서버 재시작/배포 | 없음 |
| HOLD 파일 stage | 없음 (close_2_more.py, eum_docs.py 유지) |

---

## 9. 다음 단계 제안

1. **G2B 집 skeleton 생성** — `scripts/g2b/profile.py`, `gates.py`, `validators.py` 작성
2. **Eum 집 보강** — `scripts/eum/profile.py`, `gates.py`, `validators.py` 작성
3. **Gabia DNS 집 구현** — `dns_assist.py` 작성, router 연결
4. **CAD/HWPX 독립 집 생성** — `scripts/cad/`, `scripts/hwpx/` 생성
5. **Evidence Store 위치 확정** — `data/evidence/` 구조 정의

---

## 10. 최종 판정

**PASS**
