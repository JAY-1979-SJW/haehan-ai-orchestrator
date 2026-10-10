# Domain Room Allocation Rule (집 배정 기준)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_DOMAIN_ROOM_ALLOCATION_01  
상태: LOCKED

---

## 1. 개요

모든 업무 기능은 Domain Unit(집) 단위로 배정된다.  
각 집은 반드시 아래 방 구조를 따른다.  
이 배정표는 신규 기능이 반드시 지정된 위치에만 생성되도록 강제한다.

---

## 2. 필수 방 구조 (11개 방)

| 방 이름 | 역할 | 파일 위치 패턴 |
|---------|------|--------------|
| entrance/router | HTTP 진입점, 명령 분기만 | `scripts/{domain}/router.py` |
| resident-card/profile | 사이트 프로필, 능력(capability) 선언 | `scripts/{domain}/profile.py` |
| security-door/gates | gate 결정 (ALLOWED/BLOCKED/…) | `scripts/{domain}/gates.py` |
| inspection/validators | 입력/응답 유효성 검사 | `scripts/{domain}/validators.py` |
| living-room/usecase | 업무 흐름, 초안 생성, assist | `scripts/{domain}/{feature}_assist.py` 또는 `usecase.py` |
| external-door/adapter | 외부 API, 브라우저 연동 | `scripts/{domain}/adapter.py` 또는 `scripts/site_engine/adapters/{domain}.py` |
| parking/workflow | 상태 기반 작업흐름, 큐 | `scripts/{domain}/workflows.py` |
| warehouse/storage-artifact-evidence | 결과물, 증거, 아티팩트 저장 | `data/{domain}/` |
| cctv/audit-report-log | 감사로그, 운영 리포트 | `data/logs/`, `data/reports/{domain}/` |
| alarm/tests | 구조/기능 테스트 | `tests/test_{domain}_*.py` |
| rulebook/docs | 도메인 규칙, 집 배정표 | `docs/architecture/domain_units/{domain}_room_allocation.md` |

---

## 3. 집 경계 금지선

모든 Domain Unit에 공통 적용되는 절대 금지 규칙:

```
1. 다른 Domain Unit 직접 import 금지
   - gabia ↔ hiworks ↔ g2b ↔ eum ↔ google ↔ youtube ↔ cad ↔ hwpx 간 직접 import 금지
   - 공용시설(site_engine, local_agent) 경유만 허용

2. router에서 DB 직접 접근 금지
   - router.py에 sqlite3/sqlalchemy/psycopg2/cursor 사용 금지
   - 모든 DB 접근은 저장소 레이어(scripts/ops, data/) 경유

3. adapter에서 다른 site adapter 직접 호출 금지
   - adapter는 자신의 외부 대상만 연동
   - 타 도메인 adapter 체이닝 금지

4. storage 위치 불명확 금지
   - 결과물은 반드시 data/{domain}/ 아래에 저장
   - 루트 레벨 임시 파일 누적 금지

5. session/cookie/token/password 저장 금지
   - data/sessions/ 파일 읽기/파싱/재사용 전면 금지
   - credential 자동 입력 금지

6. final submit/payment/sign 자동 실행 금지
   - 결제, 투찰, 전자서명, 최종 제출은 USER_DIRECT_REQUIRED
   - 서버 사이드에서 해당 사이트로 브라우저 실행 금지 (SERVER_BROWSER_GUARD)
```

---

## 4. gate decision 분류 기준

| 기능 유형 | 기본 gate decision |
|----------|------------------|
| 공개 데이터 조회/검색 | READ_ONLY_ALLOWED |
| 내부 데이터 조회 | ALLOWED |
| 초안 생성 | DRAFT_ALLOWED |
| 승인 필요 작업 | APPROVAL_REQUIRED |
| 사용자 직접 실행 필요 | USER_DIRECT_REQUIRED |
| 로컬 에이전트 필요 | LOCAL_AGENT_REQUIRED |
| 절대 금지 | BLOCKED |

---

## 5. 방 생성 의무

신규 Domain Unit 추가 시 의무 생성 순서:

```
1. rulebook/docs 먼저 작성 (집 배정표)
2. resident-card/profile 선언
3. security-door/gates 정의
4. inspection/validators 작성
5. entrance/router 연결
6. alarm/tests 추가
7. 이후 living-room/usecase, external-door/adapter, parking/workflow 순으로 구현
```

---

## 6. 대상 Domain Unit 전체 목록

### Site Domain Units
| 집 | 경로 | 현황 |
|----|------|------|
| Gabia | scripts/gabia/ | router/profile/gates/validators ✅ |
| G2B | scripts/g2b/ | router ✅ / profile/gates/validators ❌ |
| Hiworks | scripts/hiworks/ | router/profile/gates/validators/workflows ✅ |
| Google | scripts/google/ | router/profile/gates/validators/workflows ✅ |
| YouTube | scripts/youtube/ | router/profile/gates/validators ✅ |
| Eum | scripts/eum/ | router ✅ / profile/gates/validators ❌ |
| Naver | scripts/naver/ | router ✅ / profile/gates/validators ❌ |
| Kakao | scripts/kakao/ | router ✅ / profile/gates/validators ❌ |
| Smartstore | scripts/smartstore/ | router ✅ / profile/gates/validators ❌ |

### Local PC Domain Units
| 집 | 경로 | 현황 |
|----|------|------|
| CAD | scripts/local_agent/g2b/ | 부분 |
| HWPX | 미정 | ❌ |
| 문서 자동화 | 미정 | ❌ |
| 출퇴근 앱 | 미정 | ❌ |
| 위험성평가/안전서류 | 미정 | ❌ |
| File Map | scripts/file-map/ | 부분 |

### Shared Facility
| 집 | 경로 | 현황 |
|----|------|------|
| Site Engine | scripts/site_engine/ | ✅ |
| Local Agent | scripts/local_agent/ | ✅ |
| Action Registry | scripts/site_engine/registry.py | ✅ |
| Audit/Log | scripts/ops/ | ✅ |

---

## 7. 감사 기준

다음을 자동 감사로 강제:
- 각 Domain Unit 집 배정 문서 존재 여부
- 필수 방(router/profile/gates/validators) 파일 존재 여부
- 금지 action 명시 여부
- USER_DIRECT_REQUIRED / LOCAL_AGENT_REQUIRED / BLOCKED 정책 명시 여부
- cross-domain 직접 import 금지 문구 존재 여부

감사 스크립트: `tools/audits/app/audit_domain_room_allocation.py`  
감사 테스트: `tests/test_domain_room_allocation.py`
