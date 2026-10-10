# 앱 트리맵

전체 모듈·통신·게이트·레이어 구조: **`docs/architecture/APP_TREEMAP.md`**  
(포트맵, 라우터 트리, L1~L12 레이어, 게이트 체계, 알려진 이슈 포함)

---

# 기존 구현 확인 의무 (위반 = 중복 구현 금지)

## 자동화·수집·사이트 작업 전 필수 실행

사이트 자동화, 데이터 수집, CDP 조작, 스크래핑 코드를 **새로 작성하기 전에** 반드시 아래를 먼저 실행한다.

```bash
python tools/hooks/capability_check.py <도메인>
# 예시
python tools/hooks/capability_check.py cafe
python tools/hooks/capability_check.py smartstore
python tools/hooks/capability_check.py eum
python tools/hooks/capability_check.py naver mail
```

출력에서 기존 구현(API 엔드포인트, Python 함수, CLI 커맨드)이 확인되면:
- **기존 것을 사용한다** — 새로 짜지 않는다
- API가 있으면 API 호출, Python 함수가 있으면 import해서 사용
- 없을 때만 신규 작성 허용

**CDP 직접 조작(websocket, JS 실행)은 기존 구현이 전혀 없을 때의 최후 수단이다.**

---

# 배포 운영규칙

## 로컬 Docker 없음 — 로컬 Docker CLI 호출 금지

- **로컬 PC에 Docker CLI 미설치** → `docker` / `docker-compose` 명령어 로컬 실행 불가
- 배포는 **원격 서버에서만** 수행: `git push` 후 서버가 `git pull` + `docker compose up` 자체 처리
- Python 스크립트에서 `subprocess`로 `docker` / `docker-compose` 직접 호출 금지
- 위반 시 quality gate `NO_LOCAL_DOCKER_CLI` 에러로 커밋 차단됨
- 삭제된 스크립트(복구 금지): `deploy_api_with_runtime_gates.py`, `verify_compose_project_boundary.py`, `verify_docker_context_policy.py`, `verify_container_orphans.py`, `docker/docker-compose.dev.yml`, `docker/docker-compose.file-map-executor.yml`

### 정책 예외 (Scoped Exception) — `tools/server_deploy.py`

- **유일하게 docker 호출이 허용된 스크립트.** `configs/quality_gate.json` 의 `no_local_docker_cli_allow_paths` 에 등록.
- 사유: 서버 배포는 docker compose가 정당하게 필요(서버는 docker로 구동). 배포 스크립트를 repo에 두어 버전관리·리뷰 대상으로 유지하기 위함.
- 안전장치: 스크립트 최상단 `_guard_server_only()` 가 docker 미설치(=로컬 PC) 시 `exit 3`로 즉시 차단 → 로컬에서 절대 실행 불가.
- 이 예외는 **이 파일 1개에만** 적용. 다른 파일의 docker 호출은 그대로 차단.
- ⚠️ **정정(2026-09-29, docs/defect_index.json #6):** 이 스크립트를 호출하던 배포 데몬
  `scripts/ops/deploy_trigger_daemon.py`는 2026-06-02 커밋 `b4ad2f70`에서 "좀비 스크립트"로
  **삭제됨**(`deploy_router.py`의 관련 참조도 같은 커밋에서 제거). 그런데 `ai_orchestrator/routers/deploy_router.py`의
  GitHub webhook 핸들러(`/api/v1/deploy/webhook`)는 여전히 호스트의 `TRIGGER_URL`
  (`host.docker.internal:8401/trigger`)로 전달을 시도한다 — 그 주소를 리슨하는 데몬이
  더 이상 없으므로 **현재 webhook 자동배포는 끊긴 상태로 추정**(운영 서버 직접 확인 전까지
  "추정"). 상세 배경은 `docs/architecture/PROD_DEPLOY_PLAN.md`(2026-06-02, 운영 HEAD가
  origin보다 23커밋 밀려 있던 걸 실측한 문서, 그 이후 최신 상태 미확인)와
  `docs/architecture/DEPLOY_PIPELINE_REPAIR.md` 참고. 실제 배포는 여전히 `server_deploy.py`를
  운영 서버에서 직접 실행(SSH 등)하는 방식으로 우회 가능 — 데몬 복구/재설계는 운영 서버
  접근이 필요해 별도 사용자 승인 후 진행(docs/defect_index.json #4 와 동일 범위).

---

# 작업 원칙

## 수동 실행 요청 절대 금지

사용자에게 명령어 직접 실행을 요청하지 않는다.

**금지 표현 (절대 사용 불가):**
- "터미널에서 실행하세요"
- "직접 입력하세요"
- "! python ... 입력하시면"
- "다음 명령을 실행하세요"
- "수동으로 진행하세요"
- "콘솔에서 직접 확인하세요"
- "오류 내용을 보여주세요"
- "화면에 표시된 메시지를 알려주세요"
- "어떤 오류인지 알려주세요"

**오류 발생 시 AI가 직접:**
- 현재 사이트/URL/페이지 상태를 CDP로 확인
- 오류 원인 파악 후 수정
- 재실행

**대신 AI가 직접:**
- Bash/PowerShell 도구로 명령 실행
- 스크립트 직접 실행
- CDP 브라우저 조작
- 파일 읽기/쓰기

**예외 — 사용자가 직접 해야 하는 것 (보안 구조적 한계):**
- 로그인 OTP / SMS / 생체인증
- 결제·과금 최종 확인
- 비가역 작업 최종 저장 버튼

위 예외가 아닌 모든 작업은 AI가 도구를 사용해 직접 수행한다.

## 사용자 승인 후 자동 진행

사용자가 명시적으로 한 흐름을 승인하면 ("진행해", "자동으로 해줘", "모두 동의해" 등) 그 흐름 내 모든 sub-step을 중간 컨펌 없이 끝까지 자동 진행한다. 매 클릭/입력마다 재확인하지 않는다.

**예외 — 매번 재확인 필수:**
- 외부 공개 발행 (블로그/카페/SNS 게시)
- 메일/메시지 전송
- 결제·과금
- 데이터 삭제
- repo boundary 외부에 영향
- 정책/약관상 위험 작업

흐름 도중에는 짧은 진행 보고만, 막힘이나 종료 시점에만 사용자에게 결정 요청.

## 코드 작성 전 기준서 → 드라이 런 → 승인 → 실행

신규 코드 작성 또는 기존 코드 변경 전에 반드시 다음 3단계를 거친다.

1. **기준서 작성** — 무엇을 왜 어떻게 변경하는지 설계 문서를 먼저 작성한다.  
   - 변경 범위, 레이어, 영향 파일, 보안/DB/API 영향 여부를 명시한다.
2. **드라이 런** — 실제 파일 수정 없이 변경 시뮬레이션을 실행하고 결과를 보고한다.  
   - 예상 diff, 게이트 통과 여부, 예상 사이드 이펙트를 보여준다.
3. **사용자 승인 후 코드 실행** — 사용자가 "진행해" 등으로 승인해야만 실제 파일을 수정한다.

**예외 (즉시 실행 허용):**
- 오타·변수명·주석 수정 등 단순 1줄 수정
- 테스트 실행, 로그 조회 등 read-only 작업
- 사용자가 명시적으로 "바로 해줘", "기준서 생략해" 등을 요청한 경우

## 직렬 진행

단계는 직렬로 진행하되, 각 단계는 자동으로 다음으로 이어진다. 검증은 코드가 수행하며, 사용자 컨펌은 흐름 시작 시점에만 받는다.

## 백그라운드 작업 지시

"백그라운드로 해", "알아서 해", "백그라운드 작업" 등의 지시가 있으면:
- 스크린샷·파일 읽기·빌드·실행 등 모든 중간 단계를 사용자 개입 없이 완주
- 중간에 tool use 결과를 사용자에게 확인받거나 흐름을 끊지 않음
- 완료 후 1회 결과 요약만 전달
- Agent 서브에이전트 또는 연속 도구 호출로 끝까지 진행

## 외부 사이트 자동화 — 수동요청 금지 원칙

사용자가 외부 사이트 작업을 지시하면 AI가 CDP 브라우저로 직접 수행한다. "사용자가 직접 하세요", "수동으로 진행하세요" 안내 금지.

**AI가 직접 수행하는 것 (사용자 수동 요청 금지):**
- 개발자 콘솔 앱 등록 (카카오, 네이버, 구글 등)
- Redirect URI / 플랫폼 / 동의항목 설정
- API 키 발급 및 조회
- 도메인·DNS 레코드 입력 준비 (가비아 등)
- 공공데이터포털 활용신청·인증키 발급 신청
- 폼 자동 입력·화면 이동·설정 변경

**사용자가 직접 해야 하는 것 (AI 자동화 불가 — 보안상 구조적 한계):**
- 최초 로그인 / OTP / SMS 인증 / 카카오앱 인증
- 결제·과금·환불
- 최종 저장·제출 버튼 (DNS 변경, 도메인 연장 등 비가역 작업)

**흐름:**
1. 사용자가 작업 지시
2. AI가 로그인 감지 시작 → 사용자가 브라우저에서 로그인 (1회만)
3. 로그인 감지 후 AI가 나머지 모든 단계 자동 수행
4. 완료 후 결과 보고

## 코드 보존

기존 코드 무단 삭제/변경 금지. 기능 추가는 신규 모듈/함수로. "다시 개발" 요청은 기존 파일 보존하고 별도 구현.

## 로그인 세션 보존 (필수)

로그인된 세션은 CDP 영구 프로필에 유지된다. **AI는 작동 중인 로그인 세션을 임의로 파기하지 않는다.**

**금지 (위반 = session-guard 훅 차단):**
- `nidlogin.logout` 등 **로그아웃 URL 접속**으로 세션 종료
- `clear_cookies` / `delete_cookies` / `deleteAllCookies` 등 **쿠키 삭제**
- 로그인 테스트를 위해 **실제 세션을 로그아웃** (필요하면 별도 프로필/계정으로)

**원칙:**
- 한 번 로그인하면 계속 유지 → "매번 로그인" 방지. AI가 깨지 않는 한 세션은 남는다.
- 세션 확인은 `session_probe`(읽기 전용 점검)로만. 로그인 상태를 *바꾸지* 않는다.
- 만료/로그아웃 감지 시: 파기하지 말고 **사용자에게 재로그인 요청**(OTP/캡차는 사용자만 가능).
- 정당한 로그아웃 코드(예: 사용자가 명시 요청한 로그아웃 기능)는 해당 줄에 `# session-ok` 주석.

---

# 앱 구조/보안/레이어 운영규칙

## 레이어 기준

```
L1 Shared Contracts  — 스키마, DTO, 모델, 리덕션 헬퍼
L2 Policy/Gate       — 리스크 게이트, 정책, 승인, 허용목록
L3 Connectors        — 외부 클라이언트, 저수준 IO 래퍼
L4 Browser Engine    — 브라우저/세션/폼 자동화 (범용)
L5 Site Modules      — 사이트별 라우터, 셀렉터, 능력
L6 Business Workflows— 업무 흐름 오케스트레이션, 큐
L7 Persistence/Audit — DB, 감사, 운영 로그, 마이그레이션
L8 Server API        — FastAPI/Flask 라우터, 서버 태스크 API
L9 Admin UI          — 프론트엔드/관리/데스크톱 UI
L10 Local PC App     — Excel/HWP/CAD/재고/파일맵 자동화
L11 Tests/Fixtures   — 테스트 및 픽스처
L12 Docs/Reports     — 설계서, 운영규칙, 감사 결과
```

## 의존성 방향 (위반 = FORBIDDEN_IMPORT 게이트 FAIL)

허용: 상위 레이어 → 하위 레이어  
금지:
- core/domain(L2) → API(L8) / UI(L9) / DB 직접
- site router(L5) → DB 직접
- 서로 다른 업무 도메인 간 직접 import (hiworks ↔ eum ↔ youtube ↔ g2b)
- 하위 레이어 → 상위 레이어 역방향

## 신규 코드 위치 규칙

신규 코드 작성 전 반드시 확인:
1. 이 기능이 어느 레이어에 속하는가
2. 기존 모듈이 있는가 (재사용 우선)
3. 새 파일 생성 위치가 허용된 위치인가
4. 기존 API 응답 key / DB schema / SQL / 산식 / 정책을 변경하는가
5. 보안 영향이 있는가
6. 순환 의존성 또는 역방향 import가 생기는가
7. 테스트와 audit gate가 있는가

금지:
- router에 SQL 작성
- UI에 업무 산식
- core/domain에 환경변수 직접 접근
- 외부 API 호출 코드 여러 곳 중복
- 거대 파일에 기능 누적

## 보안 금지선 (위반 = SECURITY_PATTERN 게이트 FAIL)

```
secret/token/password 값 출력/로깅 금지
.env 값 원문 출력 금지
운영 DB update/delete/drop/truncate 승인 없이 금지
schema 변경 승인 없이 금지
chmod/chown 자동 변경 금지
투찰/전자서명/송금/결제 자동 실행 금지
쿠키/session 추출 금지
```

## 게이트 실행 의무

작업 후 반드시 실행:
```bash
python tools/repo_gates/codebase_layer_audit.py
pytest tests/test_codebase_layer_audit.py -q
python tools/quality/quality_gate.py --staged --enforce --allow-existing-code-change
```

FORBIDDEN_IMPORT > 0 → STOP  
SECURITY_PATTERN > 0 → STOP  
CIRCULAR_IMPORT > 0 → STOP  
quality gate errors > 0 → STOP

## 병렬 실행 규칙

병렬 가능: read-only 감사, 문서 조사, 독립 정적 분석  
병렬 금지: git, DB, 배포, 서버 재시작, 파일 삭제, 권한 변경, secret 작업, 같은 파일 수정  
병렬 결과는 통합 리포트로 병합 → 전체 게이트 직렬 재실행 → commit은 1회만

## 지시문 공통 블록

모든 지시문에 포함할 원칙:
1. 신규 코드는 정해진 레이어, 정해진 디렉터리에만 작성
2. 기존 구현이 있으면 재사용, 중복 구현 금지
3. router = HTTP 처리만 / service = 업무 흐름만 / core = 순수 정책·산식·판정만 / repository = DB만 / adapter = 외부 연동만
4. 역방향 import, 순환 import 금지
5. API 응답 key, DB schema, SQL, 핵심 산식, 보안 정책 임의 변경 금지
6. secret/token/password/env 값 출력 금지
7. 운영 DB write, schema 변경, 서버 배포/재시작, 파일 삭제, 권한 변경은 승인 없이 금지
8. 신규 파일 생성 시 왜 이 위치가 맞는지 보고
9. 작업 후 layer audit, cycle audit, security audit, test 실행
10. PASS/WARN/FAIL로 최종 판정, FAIL 즉시 STOP 보고

---

# EUM (건설근로자공제회) 사이트 탐색 결과 (2026-05-11)

## 사이트 구조

```
eum.cw.or.kr
├── 메인: https://eum.cw.or.kr/main (진입점)
├── 마이페이지: https://eum.cw.or.kr/mypage
└── 관리 섹션
    ├── WEBMAN380M00: 현장별 단말기 목록 (프로젝트별)
    ├── WEBMAN381M00: 단말기 설치계획 (접근 제한)
    ├── WEBMAN382M00: 단말기 철거 (접근 제한)
    ├── WEBMAN390M00: 단말기설치현황 ⭐ 핵심 데이터 소스
    └── WEBMAN400M00: 단말기별 이력관리
```

## 핵심 발견사항 (2026-05-11 재탐색 확정)

### 1️⃣ 단말기 데이터 (최종 확정)
- **현재 임대 중: 22대** (전체 사이트 확인)
- **임대 현장: 22개** (모두 "정상" 상태, 철거일 없음 = 임대 진행 중)
- **임차인: 비전아이(주)** (22개 현장 전체 동일)
- **구매/기타: 사이트에 미표시** (임대 단말기만 목록에 표시)

### 2️⃣ WEBMAN390M00 (단말기설치현황) - 핵심 페이지 + 올바른 추출 방법
- **테이블#1에 실제 44행(헤더2+데이터42)** - `table.querySelectorAll('tr')` 사용 (tbody 아닌 전체 table)
- **각 단말기 = 2행으로 표현**: 행1(14열 주정보) + 행2(13열 보조정보) = 27개 컬럼
- **헤더도 2행**: 행0(NO~총비용 14열) + 행1(단말기ID~잔존가치 13열)
- **필터:** 13개 select (시범사업장여부, 관할지사, 전자카드구분, 의무/자율, 승인상태, 단말기유형, 운용상태, 통신상태, 설치유형, 계약유형, 예외여부, 표시개수, 검색조건)
- **추출 방법:** `table.querySelectorAll('tr')` → 2행씩 묶어 단말기 1개 매핑

### 3️⃣ 27개 컬럼 구조
```
행1 (14열): NO, 고유번호, 단말기번호, 공제가입번호, 공사명, 발주기관, 전자카드구분, 지정업체, 단말기유형, 운용상태, 설치일, 처리건수, 계약유형, 총비용
행2 (13열): 단말기ID, 공사번호, 공사상태, 공사업체, 관할지사, 설치예외, 유통업체, 지정단말기명, 통신상태, 철거일, 설치일수, 설치유형, 잔존가치
```

### 4️⃣ 임대 현장 목록 22개 (2026-05-11 확인)
| NO | 공사명 | 임차인 | 관할지사 |
|----|--------|--------|---------|
| 1 | 부곡커뮤니티센터 신축공사(소방) | 비전아이(주) | 경기지사 |
| 2 | 서울신남초 교사 개축 소방공사 | 비전아이(주) | 서울남부센터 |
| 3 | 양주회천 A-25BL 아파트 정보통신공사 8공구 | 비전아이(주) | 의정부센터 |
| 4 | 2024~2026년 부천지역 열수송관시설 유지보수공사 | 비전아이(주) | 인천지사 |
| 5 | 구둔-일신간 도로확포장공사(1차) | 비전아이(주) | 경기지사 |
| 6 | 수내교 교통우회용 가설교량 설치공사 | 비전아이(주) | 경기지사 |
| 7 | 논현동 221-16 청년주택 신축공사 | 비전아이(주) | 서울남부센터 |
| 8 | 분당 어린이종합지원센터 건립 소방공사 | 비전아이(주) | 경기지사 |
| 9 | 평택우체국 건립 소방공사 | 비전아이(주) | 경기지사 |
| 10 | 인천부평 행복주택 및 도시재생뉴딜 혁신센터 전기공사 | 비전아이(주) | 인천지사 |
| 11 | 연수체육센터 건립 소방공사[계속비] | 비전아이(주) | 인천지사 |
| 12 | 인천남부초 공간재구조화 증개축 소방공사(계속비) | 비전아이(주) | 인천지사 |
| 13 | 서울애니메이션센터 건립 통신공사(장기1차) | 비전아이(주) | 서울지사 |
| 14 | 서울면중초 그린스마트 미래학교 개축 소방공사(장기계속) | 비전아이(주) | 서울지사 |
| 15 | 자전거주차장 내 소공연장 증축 및 리모델링 공사(소방) | 비전아이(주) | 서울지사 |
| 16 | 신선어린이공원 지하주차장 조성공사 | 비전아이(주) | 인천지사 |
| 17 | (주)수정실업 공장 신축공사 | 비전아이(주) | 경기지사 |
| 18 | 만경지구 수리시설개보수사업 토목건축기계공사 | 비전아이(주) | 전주센터 |
| 19 | 그린스타트업타운 복합허브센터 건립공사(건축) | 비전아이(주) | 광주지사 |
| 20 | MTV근로자지원시설 건립공사(전기) | 비전아이(주) | 인천지사 |
| 21 | 영천경마공원 1단계 건설 전기공사 | 비전아이(주) | 대구지사 |
| 22 | 24-D-00부대 생활관 개수 통신공사(2040) | 비전아이(주) | 대전지사 |

## 단말기 임대 전체 파이프라인

```
[1단계] 신규 현장 발굴/홍보
  EUM WEBMAN380M00 → 신규 공사 목록 → 홍보 메일 발송 → 계약 체결

[2단계] 계약 및 EUM 등록 (수동)
  임대 계약서 → EUM 설치 신청 등록 → 공제회 승인 확인

[3단계] 단말기 설치 (수동)
  현장 방문 → 설치 → EUM 설치일 등록 → 통신 확인

[4단계] 운용 모니터링 (자동화됨)
  주 1회 WEBMAN390M00 추출 → 통신단절/미사용 감지 → 조치

[5단계] 준공/임대 종료 (수동)
  준공 통보 → EUM 철거 신청 → 단말기 회수

[6단계] 정산 및 서류 종료 (수동)
  임대료 정산(설치일수 기준) → 계약 종료 서류 → 재고 복귀
```

## 자동화 로직

> 2026-09-29 정정(docs/defect_index.json #28): 아래에서 예전에 안내하던
> `scripts/eum_extract_all_devices.py` / `scripts/eum_business_dashboard.py` /
> `scripts/archive/eum_legacy/eum_device_inventory_automation.py` 는 2026-09-23
> 정리에서 삭제됨(`docs/deleted_code_index.md`의 `scripts` 항목, 복원은 그 문서 안내
> 그대로 `git checkout backup/pre-cleanup-20260923 -- <경로>`). 삭제 후에도 실행법을
> 계속 안내하고 있었던 걸 바로잡는다(CLAUDE.md는 9/29에 먼저 정정, 이 파일은 누락돼
> 있던 걸 뒤늦게 정정). 현재 단말기설치현황(WEBMAN390M00) 자동 점검의 실제 진입점은
> `scripts/eum/daily_check.py`.

### 올바른 추출 로직 (WEBMAN390M00, 삭제된 스크립트가 실측으로 확인했던 내용 — 여전히 유효)
```python
# table.querySelectorAll('tr') 로 전체 TR (tbody 아닌 table 전체)
# 2행씩 묶기: 14열(주정보) + 13열(보조정보) → 단말기 1개
# 헤더2행 스킵 (td_count == 0인 행)
```

### 실행 방법
```bash
python scripts/eum/daily_check.py
```

## 사이트맵 파일
- `data/sitemap/eum.cw.or.kr_complete_sitemap_v2.json` - 전체 구조 + 자동화 가이드
- `data/eum_all_devices_complete.json` - 최신 완전 추출 데이터 (22대)

## 주의사항
- ⚠️ 철거일 없음 = 임대 진행 중 (22개 현장 전부 정상 임대 중)
- ⚠️ 영천 현장 = NO 21 (영천경마공원 1단계 건설 전기공사) 확인됨
- ⚠️ 임차인은 모두 "비전아이(주)" - 단말기 사용하는 실제 공사업체는 "공사업체" 컬럼에 별도 기재
- ⚠️ tbody 기반 추출은 실패 → 반드시 `table.querySelectorAll('tr')` 사용

---

# 네이버 OpenAPI 운영규칙 (2026-05-29 확인)

## 앱 정보

| 항목 | 값 |
|------|-----|
| 앱 이름 | 해한AI검색 |
| Client ID | `.env` 의 `NAVER_OPENAPI_CLIENT_ID` 참조 |
| Client Secret | `.env` 의 `NAVER_OPENAPI_CLIENT_SECRET` 참조 |
| 개발 상태 | **개발 중** (검수 전 — 본인 계정만 로그인 가능) |
| 카테고리 | 기타 |
| 앱 URL | `https://developers.naver.com/apps/#/myapps/cSW_L1d1Gic9ElCbzA_k/overview` |

## 등록된 API

| API | 유형 | 일일 허용량 | 상태 |
|-----|------|------------|------|
| **검색** (`search/**`) | 비로그인 오픈 API | 25,000 회/일 | ✅ 활성 |
| 네이버 로그인 | 로그인 오픈 API | — | 개발 중 (검수 전) |

## 서비스 환경 설정

| 환경 | URL |
|------|-----|
| 비로그인 WEB | `http://localhost` |
| 로그인 PC 웹 서비스 URL | `http://localhost` |
| 로그인 Callback URL | `http://localhost/callback` |

⚠️ 실서비스 배포 시 위 URL을 실제 도메인으로 변경 필요

## 운영 정책

```
NAVER_OPENAPI_DRY_RUN=false   # 실제 호출 활성화
NAVER_SEARCH_DB_ENABLED=true  # SQLite DB 적재 활성화
일일 한도: 25,000 회 (검색 API)
```

### 금지 사항 (개발자센터 정책 + 보안 정책)
- 유료 API 키 발급 금지
- 광고 캠페인 생성 / 예산 설정 / 결제 등록 금지
- 카페 쓰기 API — 현재 앱에 미등록, 사용 금지
- Client ID / Secret 원문 로그 출력 금지
- 일일 허용량 초과 자동 호출 금지

### 허용 범위 (비로그인 검색 API)
- 블로그 검색: `GET /v1/search/blog.json`
- 쇼핑 검색 (경쟁사 조사): `GET /v1/search/shop.json`
- 뉴스 검색: `GET /v1/search/news.json`
- 정렬: `sim`(유사도) / `date`(날짜) 만 허용

## 카페 API 미등록 확인

사용자가 앱 등록 시 **카페 API를 선택하지 않음** — 검색 API만 등록됨.
카페 자동화는 **CDP 브라우저 세션 방식**으로만 운영 (OpenAPI 미사용).

## CDP 강제 시작

브라우저 CDP가 내려갔을 때:
```bash
python scripts/browser/cdp/cdp_force_start.py start [URL]
python scripts/browser/cdp/cdp_force_start.py status
python scripts/browser/cdp/cdp_force_start.py stop
```
- 샌드박스 게이트 우회 버전 (`assert_browser_launch_allowed` 미호출)
- 프로필: `data/cdp_profile/ai_chrome`
- PID 파일: `data/cdp_force_pid.json`

---

# YouTube Data API / OAuth 운영규칙 (2026-05-30 설정 완료)

## GCP 프로젝트 정보

| 항목 | 값 |
|------|-----|
| 프로젝트 | haehan-ai |
| API 키 이름 | haehan-youtube-data-api |
| OAuth 클라이언트 | haehan-youtube-server-captions (웹 애플리케이션) |
| 콜백 URI | `https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback` |

## 환경변수 (.env 기준)

```
YOUTUBE_DATA_API_KEY=<.env 파일의 실제 값 참조 — 문서에 원문 기록 금지, 2026-09-30 유출 정정>
YOUTUBE_CLIENT_SECRETS_FILE=ai_orchestrator/storage/secrets/youtube_oauth_client.json
YOUTUBE_OAUTH_TOKEN_FILE=ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json
YOUTUBE_OAUTH_REDIRECT_URI=https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback
YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED=true
```

## OAuth 토큰 스코프 (2026-05-30 인가 완료)

| 스코프 | 용도 |
|--------|------|
| `youtube.force-ssl` | 자막 조회, 댓글 읽기 |
| `youtube.upload` | 영상 업로드 |
| `userinfo.profile` / `email` / `openid` | 계정 확인 |

- 토큰 파일: `ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json`
- refresh_token 포함 → 자동 갱신 가능
- 인가 계정: skyjwshin@gmail.com

## 토큰 만료 시 재인가 절차

```python
from scripts.youtube import oauth
result, _ = oauth.build_auth_plan({'scope': 'force-ssl upload'})
# result['auth_url'] 을 브라우저에서 열어 승인
# 콜백 code= 파라미터 추출 후:
result2, _ = oauth.exchange_code({'code': '<CODE>'})
```

또는 데스크 앱에서 자동 처리 (아래 참조).

## 데스크 앱 YouTube OAuth 자동 로그인

- `admin-web/electron/main.js` — 앱 시작 시 토큰 유효성 검사
- 토큰 없거나 만료 시 → 승인 다이얼로그 표시
- 사용자 승인 → OAuth 팝업 자동 열기 → 콜백 감지 → 토큰 저장
- 토큰 파일 경로: `config.json`의 `youtube_token_file` 키로 관리

## 금지 사항

- API 키 / client_secret 원문 로그 출력 금지
- 타 계정 영상 무단 업로드 금지
- youtube.upload 스코프 자동 실행 — 사용자 명시 승인 후에만
- public 공개 영상 업로드 — 별도 승인 필수 (기본값: private)

---

# 로컬 개발 스택 포트 구성 (2026-05-30 기준)

| 서비스 | 포트 | 비고 |
|--------|------|------|
| FastAPI 서버 | 8401 | `python -m uvicorn ai_orchestrator.asgi:app --host 127.0.0.1 --port 8401` |
| Next.js 프론트엔드 | 3000 | `cd admin-web && npm run dev` |
| Electron 앱 | — | `dist-electron/win-unpacked/Haehan AI.exe` |

## 서버 시작 순서
1. FastAPI: `python -m uvicorn ai_orchestrator.asgi:app --host 127.0.0.1 --port 8401`
2. Next.js: `cd admin-web && npm run dev`
3. Electron 앱 실행

## Electron 앱 설정 경로
- userData: `%APPDATA%\Haehan AI\config.json`
- 라이선스 키: config.json 의 `license_key` 참조 (원문 출력 금지)
- asar 위치: `dist-electron\win-unpacked\resources\app.asar`

## Electron asar 패치 절차
```powershell
$asarPath = "C:\work\01. haehan-ai-orchestrator\dist-electron\win-unpacked\resources\app.asar"
$extractDir = "C:\work\01. haehan-ai-orchestrator\dist-electron\app-extracted"
Set-Location "C:\work\01. haehan-ai-orchestrator\admin-web\electron"
# 1. 추출
node -e "const asar=require('@electron/asar');asar.extractAll(process.argv[1],process.argv[2]);console.log('ok');" -- $asarPath $extractDir
# 2. 수정된 파일 복사
Copy-Item "admin-web\electron\main.js" "$extractDir\main.js" -Force
Copy-Item "admin-web\electron\shell.html" "$extractDir\shell.html" -Force
# 3. 재패킹
node -e "const asar=require('@electron/asar');asar.createPackage(process.argv[1],process.argv[2]).then(()=>console.log('packed'));" -- $extractDir $asarPath
```

## YouTube OAuth 자동 팝업 정책 (2026-05-30 변경)
- 앱 시작 시 자동 팝업 **제거** (기존: 2초 후 자동 표시)
- 연결 방법: 트레이 메뉴 "YouTube 계정 재연결" 또는 화면 내 "● YouTube 미연결" 버튼 클릭
- `checkYouTubeToken()` 은 packed app에서 `process.execPath` 기준 경로로 토큰 파일 탐색

## shell.html webview 레이아웃
- body: `display: flex; flex-direction: column; height: 100%`
- webview: `flex: 1; min-height: 0` — calc(100vh) 대신 flex로 전체 높이 채움
