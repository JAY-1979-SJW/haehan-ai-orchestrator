# EUM 자동화 시스템 설계서

**프로젝트**: haehan-ai-orchestrator  
**대상 사이트**: https://eum.cw.or.kr (건설근로자공제회 단말기 관리 시스템)  
**작성일**: 2026-05-12  
**버전**: v1.0

**관련 참조**
- 공통 사이트 자동화 인덱스: `docs/site_automation_reference_index.md`
- EUM 로직 참조 설계: `docs/eum_logic_reference_20260513.md`

---

## 1. 개요

### 1.1 목적

비전아이(주)가 임대 운영 중인 건설 현장 단말기(22대)의 전체 생애주기를 자동화한다.  
수작업으로 처리하던 조회·모니터링·보고·메일 발송 업무를 스크립트 1개 명령으로 처리한다.

### 1.2 업무 범위

| 단계 | 업무 | 자동화 여부 |
|------|------|-------------|
| 1 | 신규 현장 발굴 (WEBMAN380M00) | ✓ 완성 |
| 2 | 홍보 메일 초안 생성 | ✓ 완성 |
| 3 | 홍보 메일 발송 (네이버 메일) | ✓ 완성 (승인 필요) |
| 4 | 단말기설치현황 전체 추출 (WEBMAN390M00) | ✓ 완성 |
| 5 | 운용 모니터링 (통신단절/장기설치/준공임박) | ✓ 완성 |
| 6 | 단말기 이력 조회 (WEBMAN400M00) | ✓ 구현 (검증 필요) |
| 7 | 철거 현황 조회 (WEBMAN382M00) | ✓ 구현 (검증 필요) |
| 8 | 철거 신청 | △ 게이트 차단 (승인 후 실행) |
| 9 | 정산 보고서 생성 | △ 미구현 |

---

## 2. 시스템 아키텍처

```
사용자
  │
  ▼
python scripts/entry/cdp_cli.py eum <task>
  │
  ▼
scripts/site_engine/command_router.py  → dispatch()
  │
  ▼
scripts/eum/router.py  →  run_eum(task, sub, args)
  │
  ├── gate.check()          위험 등급 확인
  │
  ├── auth.py               로그인 (EUM_ID / EUM_PW)
  ├── full_explorer.py      전체 사이트 탐색
  ├── monitor.py            운용 모니터링
  ├── history.py            단말기 이력
  ├── demolition.py         철거 관리
  │
  ├── (기존 스탠드얼론)
  │   ├── eum_extract_all_devices.py   WEBMAN390M00 추출
  │   ├── eum_extract_new_sites.py     WEBMAN380M00 신규현장
  │   ├── eum_business_dashboard.py    업무 대시보드
  │   ├── eum_prioritize_and_mail.py   홍보메일
  │   └── eum_task_runner.py           전체 파이프라인
  │
  └── op_log / gate                    감사 로그 + 위험 제어
```

---

## 3. 모듈 상세 설계

### 3.1 `scripts/eum/auth.py` — 로그인

**역할**: `.env`의 `EUM_ID` / `EUM_PW`로 EUM 자동 로그인

**핵심 함수**:
```python
login(page) -> dict{ok, reason, user}
is_logged_in(page) -> bool
```

**로그인 흐름**:
```
EUM_ID / EUM_PW 환경변수 확인
  → 현재 세션 로그인 여부 확인
  → 로그인 URL 후보 순서 시도:
       /login → /web/login → /user/login → /member/login
  → ID/PW 필드 탐색 (다중 selector 후보)
  → 입력 → 버튼 클릭 or Enter
  → 성공 여부: URL 패턴 + 로그아웃 버튼 DOM 확인
```

**환경변수** (`.env`):
```
EUM_ID=아이디
EUM_PW=비밀번호
```

---

### 3.2 `scripts/eum/full_explorer.py` — 전체 사이트 탐색

**역할**: 사이트 전체를 자동 탐색하여 페이지 구조 JSON 생성

**탐색 범위**:
- 메인 페이지 (`/main`) 네비게이션 링크 전체
- 마이페이지 (`/mypage`) 구조
- WEBMAN 페이지 24개 (알려진 6개 + 추정 18개)
- 메뉴에서 발견된 추가 링크 (최대 30개)

**탐색 대상 WEBMAN 페이지**:

| 코드 | 명칭 | 접근 예상 |
|------|------|-----------|
| WEBMAN370M00 | 설치안내대상 | △ |
| WEBMAN380M00 | 현장별단말기목록 | ✓ |
| WEBMAN381M00 | 단말기설치계획 | △ 권한 제한 |
| WEBMAN382M00 | 단말기철거 | △ 권한 제한 |
| WEBMAN383M00 | 철거확인 | ? |
| WEBMAN390M00 | 단말기설치현황 | ✓ 검증완료 |
| WEBMAN391M00 | 단말기설치현황상세 | ? |
| WEBMAN400M00 | 단말기이력관리 | △ |
| WEBMAN401M00 | 단말기이력상세 | ? |
| WEBMAN300~330 | 공사/현장 관리 | ? 추정 |
| WEBMAN100~200 | 회원/업체/공제 | ? 추정 |
| WEBMAN500~600 | 통계/보고서 | ? 추정 |
| WEBMAN700~900 | 시스템/마이페이지 | △ |

**각 페이지 추출 항목**:
```
- URL / 실제 최종 URL / 접근 여부
- 테이블: 헤더 컬럼 전체, 전체 행 수, 데이터 샘플 1행
- 폼: action/method/입력필드 타입/name 전체
- 버튼: 텍스트/type/id/onclick 전체
- Select 필터: 모든 옵션값/텍스트
- 팝업/모달 존재 여부
- 페이지네이션 존재 여부
- API 엔드포인트 패턴 (.json/.do/.action)
- 에러/접근제한 메시지
```

**출력 파일**:
```
data/eum_full_site_map.json   ← 전체 구조 JSON
data/eum_full_site_map.txt    ← 사람이 읽기 쉬운 보고서
```

---

### 3.3 `scripts/eum/monitor.py` — 운용 모니터링

**역할**: 기존 추출 데이터 분석 → 이상 단말기 탐지

**입력**: `data/eum_all_devices_complete.json` (WEBMAN390M00 추출 결과)

**탐지 항목**:
```
① 통신단절   — 통신상태 ≠ "정상" (즉시 조치 필요)
② 장기설치   — 설치일수 > 180일 (준공 가능성 확인 필요)
③ 준공임박   — 철거일 존재 + 30일 이내 (회수 준비)
④ 미처리건수 — 처리건수 == 0 (설치 후 미사용)
```

**출력**: 콘솔 + `data/eum_monitor_YYYYMMDD.json`

---

### 3.4 `scripts/eum/history.py` — 단말기 이력관리 (WEBMAN400M00)

**역할**: 특정 단말기의 전체 이력 이벤트 조회

**흐름**:
```
로그인 확인
  → WEBMAN400M00 이동
  → 단말기 번호 입력 (검색 폼)
  → 결과 테이블 추출
  → data/eum_history_<번호>.json 저장
```

---

### 3.5 `scripts/eum/demolition.py` — 철거 관리 (WEBMAN382M00)

**역할**: 철거 대상 단말기 조회 및 신청

**게이트 정책**:
```
조회  → gate: AUTO (eum_extract_all_devices)
신청  → gate: APPROVE (eum_remove) — 사용자 명시 승인 필수
```

**철거 신청 명령**:
```bash
python scripts/entry/cdp_cli.py eum demolition           # 조회만
python scripts/entry/cdp_cli.py eum demolition apply     # 신청 (승인 필요)
```

---

## 4. 데이터 흐름

```
[EUM 사이트]
     │
     │ WEBMAN390M00 (단말기설치현황)
     ▼
eum_extract_all_devices.py
     │
     ▼
data/eum_all_devices_complete.json    ← 원본 데이터 (22대)
     │
     ├──→ monitor.py          통신단절/장기/준공임박 분류
     │         │
     │         ▼
     │    data/eum_monitor_YYYYMMDD.json
     │
     └──→ eum_business_dashboard.py    종합 업무 현황
               │
               ├──→ data/business_dashboard_YYYYMMDD.json
               └──→ eum_prioritize_and_mail.py
                         │
                         ▼
                    data/promo_mails_YYYYMMDD.txt
                         │
                         ▼ (승인 후)
                    네이버 메일 발송
```

---

## 5. 명령어 인터페이스

```bash
# 로그인
python scripts/entry/cdp_cli.py eum login

# 전체 사이트 탐색 (최초 1회 또는 구조 변경 시)
python scripts/entry/cdp_cli.py eum explore

# 단말기 데이터 추출 (주 1회)
python scripts/entry/cdp_cli.py eum extract

# 업무 대시보드
python scripts/entry/cdp_cli.py eum dashboard

# 운용 모니터링 (통신단절/미사용/준공임박)
python scripts/entry/cdp_cli.py eum monitor

# 단말기 이력 조회
python scripts/entry/cdp_cli.py eum history
python scripts/entry/cdp_cli.py eum history <단말기번호>

# 철거 현황 조회
python scripts/entry/cdp_cli.py eum demolition

# 철거 신청 (승인 필요)
python scripts/entry/cdp_cli.py eum demolition apply

# 신규 현장 발굴
python scripts/entry/cdp_cli.py eum new-sites

# 홍보메일 초안
python scripts/entry/cdp_cli.py eum mail

# 홍보메일 발송 (승인 필요)
python scripts/entry/cdp_cli.py eum mail send

# 전체 파이프라인 자동 실행
python scripts/entry/cdp_cli.py eum task-run

# 개발현황 확인
python scripts/entry/cdp_cli.py status
```

---

## 6. 위험 등급 (Gate Policy)

| 작업 | Gate 등급 | 설명 |
|------|-----------|------|
| 단말기 추출/조회 | AUTO | 읽기 전용 |
| 사이트 탐색 | AUTO | 읽기 전용 |
| 로그인 | NOTIFY | 세션 변경 |
| 홍보메일 초안 | AUTO | 내부 파일 생성 |
| 홍보메일 발송 | APPROVE | 외부 발송 |
| 철거 신청 | APPROVE | 비가역 작업 |
| 데이터 삭제 | APPROVE | 비가역 작업 |

---

## 7. 파일 구조

```
scripts/
  eum/
    __init__.py           패키지 진입점
    router.py             명령 라우터 (run_eum)
    auth.py               ID/PW 자동 로그인
    site_explorer.py      기본 탐색 (골격)
    full_explorer.py      세밀 전체 탐색 ⭐ 신규
    monitor.py            운용 모니터링
    history.py            이력 조회 (WEBMAN400M00)
    demolition.py         철거 관리 (WEBMAN382M00)

  eum_extract_all_devices.py    WEBMAN390M00 추출 (기존)
  eum_extract_new_sites.py      WEBMAN380M00 신규현장 (기존)
  eum_business_dashboard.py     업무 대시보드 (기존)
  eum_prioritize_and_mail.py    홍보메일 (기존)
  eum_task_runner.py            전체 파이프라인 (기존)

data/
  eum_all_devices_complete.json   단말기 전체 데이터 (22대)
  eum_full_site_map.json          전체 사이트 탐색 결과 ⭐
  eum_full_site_map.txt           탐색 결과 보고서 ⭐
  eum_monitor_YYYYMMDD.json       모니터링 결과
  business_dashboard_YYYYMMDD.json  업무 대시보드
  promo_mails_YYYYMMDD.txt        홍보메일 초안

.env
  EUM_ID=           ← 여기에 입력
  EUM_PW=           ← 여기에 입력
```

---

## 8. 실행 순서 (최초 셋업)

```
1. .env에 EUM_ID / EUM_PW 입력

2. CDP 데몬 실행 (브라우저 세션 관리)
   python scripts/browser/cdp/cdp_daemon.py start

3. EUM 로그인 확인
   python scripts/entry/cdp_cli.py eum login

4. 전체 사이트 탐색 (구조 파악 — 최초 1회)
   python scripts/entry/cdp_cli.py eum explore
   → data/eum_full_site_map.txt 확인

5. 단말기 전체 추출
   python scripts/entry/cdp_cli.py eum extract

6. 업무 대시보드 확인
   python scripts/entry/cdp_cli.py eum dashboard

7. 이후 주 1회 자동 실행
   python scripts/entry/cdp_cli.py eum task-run
```

---

## 9. 향후 개발 항목

| 우선순위 | 항목 | 설명 |
|----------|------|------|
| 1 | 탐색 결과 기반 미확인 페이지 구현 | explore 실행 후 접근가능 페이지 자동 구현 |
| 2 | 철거 신청 자동화 | WEBMAN382M00 폼 제출 (승인 플로우 포함) |
| 3 | 설치계획 조회 | WEBMAN381M00 접근 가능 시 |
| 4 | 정산 보고서 | 설치일수 × 단가 자동 계산 |
| 5 | 주간 자동 실행 | cron 또는 스케줄러 연동 |
| 6 | 슬랙/카카오 알림 | 통신단절 감지 시 즉시 알림 |
