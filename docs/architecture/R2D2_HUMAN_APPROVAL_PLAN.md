# R2d-2 — 사람이 발급하는 1회용 승인 설계서

- 상태: **설계 확정(대표님 승인) — 결정 5건 반영, 구현 진행 중(P0a·P0b부터)**
- 작성: W3, 기준: stage/r2-side-effect-gates (R2d-1 완료 상태)
- 관련: `docs/architecture/` R2 문서군, `C:\work\_coordination\R2_side_effect_gates.md`(경로별 전수 표)

## 0. 한눈에 보기

**문제.** 지금 외부 발행·발송은 *고정 문자열 문구*(`CONFIRM_TEXTS`)로 막혀 있다. 코드를 읽을 수 있는 AI 에이전트는 그 문구를 그대로 넣을 수 있고, 승인이 *무엇을* 승인했는지(내용)도 묶여 있지 않다. 예약 실행은 승인 뒤에 내용이 바뀌어도 새 내용이 실행된다.

**제안.** 승인을 "문구"에서 **"사람이 로그인한 화면에서 발급한, 특정 내용에 묶인 1회용 기록"** 으로 바꾼다.

| 항목 | 현재 | 제안 |
|---|---|---|
| 승인의 정체 | 코드에 적힌 고정 문구 | 서버에 저장된 승인 기록(대상 작업·수신자·**내용 해시**·만료·1회) |
| 발급 주체 | 누구든 문구를 알면 | **JWT 로그인 사용자(owner/admin)** 가 화면에서 승인 버튼을 누름. **승인 PIN은 사용자가 설정에서 켜는 선택 기능**(기본 꺼짐, 켜면 PIN 확인이 추가됨) |
| AI의 역할 | 문구를 알면 승인까지 가능 | 내용을 **제안하고, 승인된 것을 실행**할 수만 있다. 승인은 못 만든다 |
| 실행 직전 | 문구 문자열 비교 | 실제 내용의 해시를 다시 계산해 승인 기록과 대조, **원자적 소진** |
| 예약 실행 | 회차마다 버튼 한 번, 내용 변경 후에도 실행 | 예약 생성 시 내용 승인, **실행 시 해시 대조**, 다르면 중단+재승인 |

**결정 사항은 §11에 확정으로 정리했다**: PIN은 사용자 설정(기본 꺼짐), 인증을 끈 단독 모드에서도 로컬 화면에서 발급 가능, 예약은 생성 시 내용 승인, 텔레그램은 외부 발행 승인으로 불인정, 기존 상수 문구는 각 경로가 새 방식으로 옮겨지는 즉시 그 경로에서 폐지(전체 병행 기간 없음).

## 1. 현황과 문제 (실측)

R2d-1까지 구현된 것과 조사에서 확인된 사실이다.

1. **고정 문구 한계.** 차단 응답에서는 문구를 지웠지만, 문구가 코드 상수라 코드를 읽는 에이전트에게는 여전히 보인다.
2. **내용 무결속.** `content_publish_guard.check_content_matches_approval`은 해시가 아니라 문자열 포함 비교(`strict=False`)이고, 승인 미리보기가 비어 있으면 **통과**(fail-open)한다. 호출자는 실행할 내용 자체를 미리보기로 넘겨(`approved_preview=content[:100]`) 검사가 사실상 항상 참이다. 위임 권한(`delegated_permission_store`)은 프로세스 메모리에만 있다.
3. **예약 실행의 구멍.** `scheduled_job_service.update()`는 `params`를 덮어쓰고, 실행은 그 시점의 `job["params"]`를 읽는다(`runs`에 내용 스냅샷 없음). 승인 화면을 띄운 뒤 내용을 바꾸면 승인 클릭이 새 내용을 실행한다. 승인 대기 취소(`_cancel_awaiting`)는 진행 중인 승인과 원자적이지 않다. 승인 경로에는 문구·PIN 같은 두 번째 요인이 없다.
4. **승인 경로가 사람 전용이 아니다.**
   - `gates/approval.py`의 `approve_token`은 호출자가 넘긴 `role` 문자열을 믿고, `app.py`·`telegram_webhook.py` 등이 `approved_by="대표님", role="admin"`을 코드에서 직접 넣어 **자기 승인**한다. 텔레그램 승인 경로도 있다.
   - `naver_mailbox_router`의 `/send/confirm`은 `require_role("admin","owner")`만 확인한다. Basic 자격이 있으면 에이전트도 호출할 수 있다.
5. **인증 구조의 사실.**
   - `get_current_user`(`gates/auth.py`)는 Basic만 받고, 반환 dict(`{actor, role}`)에 **인증 방식 표지가 없다**. W4의 Bearer 지원은 `stage/console-auth-jwt` 브랜치에 있으며 역시 방식 표지를 만들지 않는다.
   - 사용자 JWT는 `sub`만 담고(role 없음, 매 요청 DB 조회), 로그인 응답 본문으로 내려가 브라우저가 **JS로** `localStorage`와 쿠키(`HttpOnly` 아님)에 저장한다.
   - `admin-web`의 `/api/proxy`는 클라이언트 Authorization → 쿠키(Bearer로 변환) → **서버가 가진 Basic 서비스 자격** 순으로 폴백한다. 브라우저 요청이 백엔드에는 Basic으로 보일 수 있다.
   - MCP 서버(`mcp_server.py`)는 요청에 **헤더를 전혀 싣지 않는다**. 인증이 켜져 있으면 401이고, `AUTH_ENABLED=false`(데스크톱 단독 모드)면 더미 owner(`system`)로 동작한다.
   - CSRF 토큰·Origin 검사는 **없다**(CORS 허용 목록만 있음).
6. **하나팩스 승인서는 이미 내용 결속 모델이다.** `scope_hash`(수신자·제목·문서 해시)를 승인 시 `approved_scope_hash`로 고정하고 실행 때 재계산해 대조한다. 다만 승인 요청은 `confirmed: true` 불리언뿐이고, 설계 문서가 말한 PIN은 구현되어 있지 않다(`flags` 테이블만 있음).

## 2. 위협 모델

### 2.1 지키려는 성질

> **AI는 승인된 것을 "받아와서 실행"할 수는 있지만, 승인을 "만들" 수는 없다. 승인은 사람이, 사람이 본 그 내용에 대해서만 만든다.**

### 2.2 공격자와 능력

| # | 공격자 | 가진 것 | 시도 |
|---|---|---|---|
| A1 | MCP·서비스 경로의 AI 에이전트 | API 호출(헤더 없음 또는 Basic 서비스 자격) | 승인 발급 API 호출 |
| A2 | 코드를 읽는 AI 에이전트 | 소스, 상수, 로그 | 고정 문구·토큰을 알아내 재사용 |
| A3 | **사용자의 로그인된 브라우저를 조작하는 AI**(CDP·브라우저 자동화) | 브라우저의 JWT(JS로 읽힘), 화면 클릭 | 사용자 이름으로 승인 발급 |
| A4 | 승인 후 내용 변경 | 예약 수정 권한 | 승인된 예약의 본문 교체 |
| A5 | 승인 재사용·경쟁 | 동시 요청 | 같은 승인으로 두 번 실행, 승인과 수정 사이 경쟁 |
| A6 | 크로스 사이트 요청 | 사용자가 다른 사이트를 열어 둠 | 사용자의 세션으로 발급 요청 |
| A7 | 승인 채널 우회 | 텔레그램 봇, `approval.py` 자기 승인 | 사람 확인 없이 승인 기록 |

### 2.3 "AI는 만들 수 없다"를 무엇으로 보장하는가

**JWT와 CSRF/Origin 검사만으로는 보장되지 않는다.** A3 때문이다. 이 저장소는 사용자의 실제 브라우저를 CDP로 조작하는 에이전트를 쓰고, 현재 JWT는 JS로 읽을 수 있다. 그래서 보장은 **서로 독립인 여러 층**으로 둔다. 각 층이 막는 공격이 다르다.

| 층 | 방법 | 막는 공격 |
|---|---|---|
| L1 방식 구분 | 발급 API는 **Bearer JWT로 인증된 사용자만**. `auth_method`(`jwt`/`basic`/`disabled`)를 사용자 dict에 추가(W4 변경 위에), `jwt`가 아니면 403. MCP(헤더 없음)·Basic 서비스 자격·`AUTH_ENABLED=false`·프록시 Basic 폴백은 모두 403 | A1 |
| L2 사람 요인 (**선택, 기본 꺼짐**) | 사용자가 설정에서 **승인 PIN을 켜면** 승인할 때 PIN을 직접 입력해야 한다. 서버에는 솔트 해시만 저장, 시도 횟수 제한(5회 실패 시 분 단위 증가 잠금), 실패는 감사 기록. PIN 설정·변경은 owner만. PIN은 JWT·쿠키·로컬스토리지·화면 코드 어디에도 저장하지 않는다. **꺼져 있으면 이 층이 없다**(§2.4 잔여 위험) | **A3**(켰을 때), A2 |
| L3 출처 검사 | 발급 API는 `Origin`/`Referer`가 허용 목록(관리 화면 도메인)이고 `Sec-Fetch-Site`가 same-origin일 때만. 본문 `Content-Type: application/json` 강제(단순 요청 폼 차단) | A6 | ※ 백엔드 Origin 검사는 프록시 구조에서 성립하지 않아 **§13(프록시 증명)으로 대체**
| L4 승인 비노출 | 승인은 **서버 저장 기록**이고 비밀 토큰이 없다. 실행은 실제 내용을 해시해 일치하는 승인을 소진한다. 차단 응답·로그에 문구·PIN·해시 원문을 싣지 않는다 | A2 |
| L5 내용 결속·1회·만료 | 해시·대상 불일치 또는 만료·소진이면 실패. 소진은 DB의 원자적 갱신(CAS) | A4, A5 |
| L6 에이전트 도구 차단 | 발급·PIN 설정 엔드포인트는 MCP `API_REGISTRY`에 없다. "MCP 레지스트리에 발급 경로가 없음", "발급 경로가 `jwt` 외에서 403"을 **계약 시험**으로 고정 | A1 |
| L7 승인 채널 정리 | 외부 발행·발송 승인은 **텔레그램·`approve_token(role=...)` 자기 승인 경로를 인정하지 않는다**(§11-4). 기존 코드 하드코딩 승인은 새 승인과 분리 | A7 |

**쿠키 `HttpOnly` 전환(W4 후속 ②)을 선행 조건으로 둔다.** 전환하면 에이전트가 JS로 JWT를 읽을 수 없다(A3 약화). PIN을 켜면 브라우저를 조작해 *화면에서* 승인 버튼을 누르는 에이전트도 PIN을 입력할 수 없어 막힌다. **PIN이 꺼져 있으면(기본)** L1·L3~L7로 AI 도구 경로·문구 재사용·내용 변경·교차 사이트는 막지만, **실제 브라우저를 조작하는 에이전트가 승인 버튼을 누르는 것은 막지 못한다.** 설정 화면은 PIN이 꺼져 있을 때 "AI가 브라우저를 조작하는 환경에서는 PIN 사용을 권장합니다"를 한 줄 보여 준다(강제하지 않는다).

### 2.4 잔여 위험(막지 못하는 것)

- 사용자 PC를 완전히 장악한 에이전트(키 입력 가로채기, PIN 입력을 화면에서 관찰)는 못 막는다. 그 경우 사용자 본인도 속는다.
- 사용자가 PIN을 에이전트에게 알려 주면 무의미하다(PIN을 켠 경우). PIN은 문서·채팅·로그에 적지 않는다는 운영 규칙이 필요하다.
- **PIN 꺼짐(기본) 시 잔여 위험**: 실제 브라우저를 조작하는 에이전트(CDP·브라우저 자동화)가 로그인된 화면에서 승인 버튼을 눌러 승인을 발급할 수 있다. 내용 해시·1회·만료·감사 기록은 그대로 적용되므로 *승인된 내용 그대로만* 실행되고 사후 추적은 가능하지만, 사람 없이 승인되는 것 자체는 막지 못한다. AI가 브라우저를 조작하는 환경에서는 PIN 사용을 권장한다.
- 내용 해시는 *내용 변경*을 막지만 *처음부터 나쁜 내용*을 사람이 승인하는 것은 막지 못한다. 화면은 사람이 실제 내용을 보게 해야 한다(§5).
- 인증을 끈(`AUTH_ENABLED=false`) 단독 모드: 모든 요청이 더미 owner라 L1의 "JWT" 구분이 성립하지 않는다. 확정 정책은 §11-2(로컬 화면에서 발급 가능, PIN을 설정했으면 PIN 필요).

## 3. 승인 기록과 흐름

### 3.1 흐름 (AI는 제안·실행만, 사람이 승인)

```
(1) 제안   누구나(에이전트 포함) 인증된 호출자 → POST /approvals/requests
             {op, target, content}  → 서버가 내용 스냅샷·해시 저장, 상태 pending, request_id 반환
(2) 승인   사람(owner/admin, Bearer JWT; PIN을 켠 경우 PIN) → POST /approvals/{id}/approve
             화면이 스냅샷 전체를 보여 주고 승인 버튼(PIN을 켠 경우 PIN 입력) → 상태 approved(만료 시각 설정)
(3) 실행   원래 발행·발송 함수 → consume_approval(op, target, content)
             실제 content 를 해시 → (op, target_hash, content_hash)가 일치하는 approved 기록을
             `UPDATE ... SET status='used' WHERE status='approved' AND expires_at>now` 로 소진
             소진 실패 → GateBlocked(문구·토큰 미노출)
```

- 토큰이 없다. 에이전트가 가진 것은 `request_id`(내용 스냅샷의 번호)뿐이고, 승인 상태는 서버만 안다. **승인된 내용과 한 글자라도 다르면 실행되지 않는다.**
- 사용자가 화면에서 직접 발행하는 흐름은 (1)(2)(3)을 한 번에 이어 주는 UI로 만든다. 사용자는 확인 모달에서 내용을 보고 승인 버튼(PIN을 켠 경우 PIN 입력)을 누르는 한 번의 조작만 한다.

### 3.2 승인 기록 (저장: SQLite, `ai_orchestrator/storage/human_approvals.db`)

| 필드 | 설명 |
|---|---|
| `id` | `ha_` + uuid4 |
| `op` | 대상 작업(`blog_publish`, `mail_send`, `gmail_send` …, 레지스트리 키) |
| `target_hash` / `target_preview` | 정규화한 수신자·채널의 해시 / 사람이 읽는 요약(마스킹) |
| `content_hash` | 정규화 내용의 sha256(§3.3) |
| `content_snapshot` | 승인 화면에 보인 내용(제목·본문·수신자·첨부 요약). 감사·재현용, 비밀값 제외 |
| `requested_by` | 제안한 주체(사용자 또는 `agent:<경로>`) |
| `status` | `pending` → `approved` → `used` / `expired` / `rejected` / `revoked` |
| `approved_by`, `approved_at`, `approved_via` | 승인한 사용자(JWT actor)·시각·`jwt+pin` |
| `expires_at` | 즉시 실행형 기본 15분. 예약형은 §6 |
| `max_uses` / `uses` | 기본 1 |
| `schedule_job_id` | 예약에 묶인 승인이면 그 job id |

- **원자성·동시성**: SQLite(WAL)의 단일 `UPDATE ... WHERE status=...` 가 CAS 이며 프로세스 간에도 안전하다(기존 `scheduled_job_store`, `fax_authorization_store`와 같은 방식). R2의 `opt_out` JSON 목록은 지금처럼 락 파일(`_opt_out_guard`)을 유지하고, 같은 락을 *경로를 인자로 받는 범용 컨텍스트 매니저*로 일반화해 PIN 실패 카운터 등 파일 상태가 필요한 곳에 재사용한다(`_opt_out_guard` → `file_guard(path)`).
- **감사**: 발급·승인·거부·소진·만료·PIN 실패를 `op_log`/`realtime_audit`에 기록한다(내용 원문·PIN 제외, 해시 앞 8자만).

### 3.3 내용 정규화(해시) — 작업별 표

해시는 **서버가 계산**한다(클라이언트가 보낸 해시를 믿지 않는다). 정규화는 키 정렬 JSON(`ensure_ascii=False`), 문자열 `strip()`, 수신자는 소문자·중복 제거·정렬.

| op | 해시에 들어가는 것 | target |
|---|---|---|
| `blog_publish` | 계정, 제목, 본문, 태그, 카테고리, 공개 범위, 첨부 이미지 파일 sha256 목록 | 블로그 id |
| `mail_send` / `gmail_send` | 수신자(To/Cc), 제목, 본문, 첨부 sha256 | 수신자 집합 |
| `eum_sales_mail` | 위와 동일 + 대량이면 수신자 목록 전체 | 수신자 집합 |
| `instagram_publish` | 미디어 URL/파일 sha256, 캡션 | 계정 id |
| `youtube_upload` | 계획 파일 sha256, 영상 파일 sha256, 제목·설명·공개 범위·예약 시각 | 채널 |
| `smartstore_reply` | 답변 본문, 문의 식별자 | 문의 id |
| `drive_share` | 파일 id, 공유 범위(role), 대상 | 파일 id |
| `hanafax_send` | 기존 `scope_hash`(수신자·제목·문서 해시)를 그대로 사용 | 승인서 id |
| `scheduled:<action>` | 예약 `params` 전체(정규화) | job id |

## 4. 게이트 핵심 이전 (순환 해소)

**목적**: `ai_orchestrator/gates ↔ scripts` 순환(verify_change 80→81)을 구조로 해결한다. import를 함수 안으로 숨기는 방식은 쓰지 않는다.

**원인**: 게이트 핵심 `scripts/gate.py`가 scripts 패키지에 있고, `ai_orchestrator`와 `scripts`가 서로를 쓴다. 게이트 핵심은 `scripts.logger`, `scripts.schemas`(`GateResult`, `GateVerdict`, `RiskLevel`), `scripts.op_log`(함수 안 import)에 의존한다.

**계획**
1. `ai_orchestrator/gates/gate_core.py`를 만들어 게이트 핵심(`check`, `require_side_effect`, `require_approved`, 수신거부 목록, 승인 소진)을 옮긴다. 층은 같은 L2.
2. **`gate_core`는 `scripts`를 import하지 않는다.** 필요한 타입(`GateResult`/`GateVerdict`/`RiskLevel`)은 `gate_core`에 정의하고, `scripts/schemas.py`가 거기서 재수출한다(의존 방향을 뒤집음). 로깅은 표준 `logging`, 감사 기록은 **싱크 등록**(`gate_core.set_audit_sink(fn)`)으로 주입하고 `scripts/op_log.py`가 import 시점에 등록한다.
3. `scripts/gate.py`는 **shim**으로 남긴다. 저장소의 분리 shim과 같은 방식(`sys.modules[__name__] = import_module("ai_orchestrator.gates.gate_core")`). 모듈 전역 상태(`_RISK_REGISTRY`, `force_approved`의 thread-local)는 한 객체로 공유되므로 동작이 같다.
4. `ai_orchestrator` 쪽 호출자(`send_approval.py`, 라우터들)는 새 경로를 직접 import한다. `scripts` 쪽 호출자는 shim을 그대로 쓰다 점진 이전한다(R2 커버리지 테스트의 `GUARDS` 이름은 유지).
5. 검증: `verify_change`의 순환 수가 80으로 돌아오는지 확인한다. 돌아오지 않으면 남은 `gates → scripts` 간선을 목록으로 보고하고 알려진 항목으로 기록한다.

**주의**: mypy는 `sys.modules` 치환 shim을 정적으로 따라가지 못하므로(R-split 경험), 이전된 모듈 간 import는 새 경로로 쓴다. `scripts/gate.py`를 import하는 29곳은 shim으로 계속 동작한다.

## 5. 승인 화면(UI)

- **관리 화면(`admin-web`)에 "승인 요청함"** 페이지를 둔다. 대기 중인 요청의 *실제 내용 전체*(제목·본문·수신자·첨부 미리보기)를 보여 주고, PIN을 입력해 승인/거부한다. 승인 직전에 내용이 바뀌면(요청이 새 해시로 대체되면) 화면이 갱신을 알린다.
- 기존 모달(R2b/R2d)은 같은 `Modal`에 **내용 요약 + 승인 버튼(PIN을 켠 경우 PIN 입력란)** 으로 교체한다. 확인 문구 안내(`SEND_CONFIRM_HINT`)는 없앤다.
- (PIN을 켠 경우) PIN은 `type="password"`, `autoComplete="off"`, 상태에 보관하지 않고 요청 직후 비운다. 서버 응답은 PIN 오류 시 남은 횟수만 알린다.
- **PIN 설정(선택)**: 설정 화면에서 **owner만** 켜기·끄기·변경한다. 기본은 꺼짐이며, 꺼져 있으면 "AI가 브라우저를 조작하는 환경에서는 PIN 사용을 권장합니다" 안내를 한 줄 보인다(강제하지 않음). 이미 켜져 있을 때 끄거나 바꾸려면 현재 PIN이 필요하다. 해시로 저장하고 시도 횟수를 제한하며 모든 변경을 감사 기록한다. 에이전트용 API는 만들지 않는다(MCP 레지스트리에 없음, 계약 시험).

## 6. 예약 실행 통합

**현재의 문제**는 §1-3. 설계:

1. 예약 **생성/수정 화면**이 내용 전체와 실행 계획(언제, 몇 회, 수신자)을 보여 주고 승인한다(PIN을 켠 경우 PIN 포함). 승인 기록은 `schedule_job_id`와 `content_hash(params)`를 담고 `expires_at`·`max_uses`(= 예정 회차 수)를 가진다.
2. `jobs`에 `approved_content_hash`, `approval_id`를 추가한다. **`update()`는 내용 필드가 바뀌면 승인을 자동 철회**하고 `awaiting` 회차를 취소한다(현재도 하는 일이지만 승인 기록 철회까지 같은 트랜잭션으로).
3. 실행 직전(`_execute`) `consume_approval("scheduled:<action>", job_id, params)`를 호출한다.
   - 일치: 소진(회차당 1회) 후 실행.
   - 불일치·만료·소진: 실행 **중단**, 회차를 `blocked_content_changed`(또는 `approval_expired`)로 기록하고 **재승인 요청 알림**(기존 텔레그램 `send_message`는 *알림 전용*으로만 사용, 승인 채널이 아님)을 보낸다.
4. 현재의 회차별 30분 승인 대기(`awaiting_approval`)는 두 방식 중 하나로 바꾼다(§11-3 결정).
   - **A(권장)**: 예약 생성 시 내용 승인 + 유효기간·최대 회차 제한. 무인 실행이 예약의 목적이므로 회차마다 사람이 필요하면 의미가 없다. 안전은 내용 해시·만료·1회 소진·kill-switch가 맡는다.
   - **B**: 회차마다 승인 대기를 유지하되 승인 시 해시 대조와 PIN을 추가.
5. `ACTIONS`별 처리: `blog_publish`·`naver_mail_send`·`telegram_notify`는 위 해시 대상. `hanafax_send`·`naver_mail_bulk_send`는 이미 `authorization_id`로 내용이 묶여 있으므로 §7을 따른다.
6. 레이스 해소: `approve`와 `update`가 같은 DB 트랜잭션에서 `approved_content_hash`를 비교하므로 "승인 화면 → 수정 → 승인 클릭" 경쟁이 없다. `runs`에 실행 시점 `params` 해시를 기록해 사후 감사가 가능하게 한다.

## 7. 하나팩스 승인서와의 통합

- 승인서(`authorizations`)는 **그대로 둔다**: 불변 범위(`scope_hash`), 한도(`max_per_run/day/total`), 시간대, `send_log` 중복 방지, 팩스 번호 수신거부, 킬 스위치.
- 바뀌는 것은 **승인 행위**뿐이다. 지금의 `POST /authorizations/{id}/approve`(`confirmed:true`)를 승인 요청함의 사람 승인(PIN을 켠 경우 PIN 포함)으로 일원화한다. 서비스는 승인 기록(`op=hanafax_send`, `content_hash=scope_hash`)이 `approved`일 때만 `store.approve`를 호출한다.
- 단건 `/hanafax/send`는 일반 `consume_approval` 경로. `batch/execute`의 `HANAFAX_APPROVED_BATCH` 문구와 `scripts/hanafax/batch.py`·캠페인 스크립트·`hanafax_auto_sender`(R2e 후보)는 승인서 경로로 편입하거나, 승인서 없이는 실행되지 않게 한다.
- 승인서의 `approved_by`는 승인 기록의 `approved_by`를 쓴다(JWT actor). 승인서 승인에도 `auth_method=jwt`(PIN을 켠 경우 PIN 포함)를 요구한다.
- 범용으로 합칠 수 있는 것(승인 기록·PIN·만료·CAS·플래그 저장)은 새 승인 스토어로 옮기고, **팩스 고유 로직(번호 정규화, 한도, 로그)은 남긴다.**

## 8. 이행 계획 (호출자별 단계)

원칙: **새 방식을 먼저 도입하고 호출자별로 옮긴다. 기존 상수 문구는 각 경로가 새 방식으로 옮겨지는 즉시 그 경로에서 폐지한다**(전체 병행 기간은 두지 않는다). 아직 옮기지 않은 경로에만 경로별 환경변수(`GATE_LEGACY_PHRASE_<경로>`, 예 `..._BLOG`)가 적용되고, 옮긴 경로는 코드에서 문구 검사 자체를 지운다. 경로별로 끄는 시점이 곧 그 경로의 이행 완료 시점이다.

| 단계 | 내용 | 선행 조건 |
|---|---|---|
| P0 | 승인 스토어(SQLite), `consume_approval`, 발급 API(L1·L3), 감사 기록, 게이트 핵심 이전(§4). 아직 아무 호출자도 바꾸지 않음 | W4 Bearer + `auth_method` |
| P1 | PIN 설정·검증(L2, **선택 기능·기본 꺼짐**), 설정 화면 안내, 실패 잠금. `HttpOnly` 쿠키 전환(W4) 확인 | owner 지정 `OWNER_EMAILS` |
| P2 | 승인 요청함 화면 + 확인 모달 교체 | P0–P1 |
| P3 | 화면에서 쓰는 경로부터 이전: Gmail `/reply`·`/send`, 블로그 `/write-to-naver`, hiworks·eum `/send`, 하나팩스 `/send` | P2 |
| P4 | 예약 실행(§6), 하나팩스 승인서(§7) | 대표님 결정(§11-3) |
| P5 | CLI·스크립트: 문구 `--confirm` → `--approval-id`(제안은 CLI가 만들고, 승인은 화면). `blog_*`, `publish_ep_batch*`, `eum_send_mail_batch`, `ig_batch`, `hanafax send`, `hiworks send-batch` | P3 |
| P6 | 에이전트 호출 경로: `smartstore submit_reply`, `drive share_link`, 인스타·유튜브 함수, MCP 도구 설명. 에이전트는 제안→(사람 승인)→실행 | P3 |
| P7 | 남아 있는 `GATE_LEGACY_PHRASE_*` 키와 `CONFIRM_TEXTS` 최종 제거, 커버리지 테스트의 가드 이름을 `consume_approval`로 교체(경로별 폐지는 P3–P6에서 이미 진행) | P3–P6 완료 |

- **함수 서명 변화**: `approval: str | None`(문구) → `approval_id: str | None`(승인 요청 번호, 선택) + 내용은 이미 인자로 갖고 있으므로 *내용으로 승인을 찾는다*. `approval_id`는 편의일 뿐 보안 요소가 아니다.
- **W2(마케팅 운영)**: `marketing_ops_router`는 P3에서 같은 `consume_approval`을 쓰도록 안내한다.
- **롤백**: 각 단계는 독립 커밋. 아직 옮기지 않은 경로는 기존 문구 방식 그대로이고, 옮긴 경로는 해당 커밋을 되돌리면 복귀한다(경로별 `GATE_LEGACY_PHRASE_*`는 이행 중 임시 스위치).

## 9. 재사용하는 것 / 새로 만드는 것

| 대상 | 판단 |
|---|---|
| `content_publish_guard.validate_publish_request`(길이·스팸·대량 정책) | **유지**(정책 검사). 해시 승인과 별개 |
| `content_publish_guard.check_content_matches_approval` | **보조로만**. 문자열 포함·fail-open이라 신뢰하지 않는다. 해시 대조가 주(主). 재사용하려면 `strict=True`, 빈 미리보기 거부로 고치고, 해시 비교 함수(`check_content_hash`)를 같은 모듈에 추가 |
| R2 `opt_out` 잠금(`_opt_out_guard`) | **경로 인자 일반화 후 재사용**(PIN 실패 카운터·소규모 파일 상태). 승인 기록은 SQLite |
| W4 JWT(`get_jwt_user`, Bearer 해석) | 재사용. 단 **`auth_method` 표지 추가**가 필요(W4와 조율). 역할은 DB 조회라 권한 철회가 즉시 반영됨 |
| `scheduled_job_service`의 CAS(`transition_run`), `fax_authorization_store`의 원샷 승인 | **패턴 재사용**(같은 SQLite 갱신 방식) |
| `gates/approval.py`(`approve_token`, JSONL) | 개발 등록 승인용으로 **그대로 두되, 외부 발행·발송 승인으로는 인정하지 않는다**(§11-4) |
| `naver_mailbox_flow`의 메모리 `_pending` 토큰 | P3에서 승인 스토어로 대체(재시작 소실·사람 전용 보장 없음) |

## 10. 시험 계획

- **발급 권한(L1)**: 헤더 없음(MCP)·Basic·`AUTH_ENABLED=false`·프록시 Basic 폴백·역할 `viewer/operator/user` → 모두 403. `jwt`+owner/admin만 통과.
- **PIN(L2, 켠 경우)**: 틀린 PIN은 승인 안 됨, 5회 후 잠금, 잠금 중 올바른 PIN도 거부, 성공 시 카운터 초기화, 동시 시도에서 카운터 정확. **PIN 꺼짐(기본)**: PIN 없이 승인 버튼만으로 발급되지만 L1·L3·L5·L6은 그대로 적용됨을 시험으로 고정(MCP·Basic·프록시 폴백은 여전히 403). PIN 설정·변경은 owner만, 에이전트용 경로 없음.
- **출처(L3)**: Origin/Referer 불일치·`Sec-Fetch-Site: cross-site`·비JSON 본문 → 403.
- **내용 결속(L5)**: 승인 후 한 글자 변경, 수신자 추가, 첨부 교체 → 소진 실패. 정확히 같은 내용만 통과. 만료·거부·철회 후 실패.
- **1회·경쟁**: 같은 승인으로 두 번째 실행 실패, 동시 16개 실행에서 정확히 1건만 성공(프로세스 간 포함).
- **비노출(L4)**: 모든 차단 응답·로그에 문구·PIN·해시 원문이 없음을 경로별로 고정(R2d 시험 확장).
- **계약(L6)**: MCP `API_REGISTRY`에 발급·PIN 경로가 없음. 에이전트 도구 목록에서 `approvals/*/approve` 호출 불가.
- **예약**: 승인 후 `update()`로 본문 변경 → 실행 중단+알림, 승인 철회 확인. `approve`와 `update` 경쟁에서 일관성. 만료·최대 회차 초과 시 중단.
- **하나팩스**: 승인서 승인은 사람 승인 기록(PIN을 켠 경우 PIN 포함)이 있고 `scope_hash`가 승인 기록과 일치할 때만 `store.approve`.
- **커버리지**: 기존 AST 기준선 테스트의 가드 목록에 `consume_approval`을 추가하고, P7에서 `require_approved`/문구 가드를 제거. 스캐너는 호출명 패턴이 아니라 **발행·발송 sink 함수 목록**을 명시한다(`write_post`·`edit_post`·`confirm_publish`를 추가해 사각지대였던 BlogWriter 계열 발행 경로를 잡음). 새로 잡힌 기존 경로(예약 실행 `_run_blog_publish`, `marketing_ops_router.publish_blog`, 카페·`_runner` 등 10건)는 기준선에 고정했고, 예약 실행은 §6에서, `publish_blog`는 W2 연결에서 기준선을 줄인다.
- **게이트 이전**: 이전 전후 동작 동일(기존 29곳 호출자 특성화 시험), `verify_change` 순환 수.

## 11. 결정 사항 (대표님 확정)

1. **승인 PIN은 사용자가 정하는 선택 기능(기본 꺼짐).** 설정에서 켜고 끈다. 꺼져 있으면 로그인한 화면에서 사람이 승인 버튼을 누르는 것으로 발급한다. 켜면 PIN 확인이 추가된다. PIN 설정·변경은 owner만, 해시 저장, 시도 횟수 제한, 감사 로그. 꺼진 상태에서도 AI 도구 경로(MCP·Basic 서비스 자격·프록시의 서버 Basic 폴백) 발급 불가, Origin 검사, 내용 해시·1회·만료 결속, 비노출, 감사 로그는 유지한다. 설정 화면은 꺼져 있을 때 "AI가 브라우저를 조작하는 환경에서는 PIN 사용을 권장합니다"를 한 줄 보여 주되 강제하지 않는다. **잔여 위험은 §2.4에 명시**(PIN 꺼짐 시 브라우저를 조작하는 에이전트가 승인 버튼을 누를 수 있음).
2. **`AUTH_ENABLED=false` 단독 모드에서도 로컬 화면에서 승인 발급이 가능**(PIN을 설정했으면 PIN 필요). "발급 불가"는 쓰지 않는다. 이 모드는 요청이 모두 더미 owner(`system`)라 JWT 구분이 성립하지 않으므로, 발급 API는 이 모드에서 *로컬 화면의 요청(Origin·로컬 호스트 검사)* 만 받고 MCP·서비스 경로 차단은 요청 출처·방식으로 구분한다. 구체 구분 수단은 P0c에서 W4의 인증 결과를 보고 정한다(**미정 항목**).
3. **예약 승인 방식 A**: 예약 생성 시 내용 승인 + 유효기간·최대 회차 + 실행 시 해시 대조.
4. **텔레그램 등 기존 승인 채널은 외부 발행·발송 승인으로 인정하지 않는다.** 텔레그램은 알림 전용.
5. **기존 상수 문구는 각 경로가 새 승인 방식으로 옮겨지는 즉시 그 경로에서 폐지한다.** 전체 병행 기간은 두지 않는다. `GATE_LEGACY_PHRASE_*`는 아직 옮기지 않은 경로에만 적용하고 경로별로 끈다(§8).


## 12. 범위와 비범위

- **이번 문서**: 설계만. 구현은 대표님 승인 후 단계별 커밋(P0부터).
- **범위 밖**: `apps/ig-comment-dm-bot`·`apps/marketing-standalone`(별도 앱), 개발 등록 승인(`dev_reg_approval`), `scripts/google/drive.py` CLI 업로드, 네이버 대량메일·하나팩스 대량의 자체 상한 정책(승인 행위만 통합).
- **의존**: W4의 Bearer·`OWNER_EMAILS`·`HttpOnly` 쿠키 전환 및 `auth_method` 표지. W2의 `marketing_ops_router`는 P3에서 합류.

## 13. §P0c 수정안 — Origin 검사를 "프록시 증명"으로 대체 (P0c 구현 전 보강, 2026-10-07)

> 상태: **구현됨(P0c).** 대표님이 (a) HMAC 증명 방식과 (b) `APPROVAL_PROXY_SECRET`·admin-web 프록시 변경을 승인했다(2026-10-07, "권장대로 진행"). 추가 요구: 사용자에게 보이는 단계를 늘리지 않는다 — 증명은 화면 뒤에서 자동으로 붙고 승인 버튼 흐름은 그대로이며, PIN 은 기본 꺼짐을 유지한다.
>
> 구현 위치: `ai_orchestrator/gates/human_session.py`(증명 검증·`require_human_session`), `ai_orchestrator/routers/human_approval_router.py`(제안·조회·발급, `/api/v1/approvals/*`), `admin-web/src/lib/approvalProxy.ts`(서명)와 `admin-web/src/app/api/proxy/[...path]/route.ts`(승인 발급 경로 분기), `.env.example`·`docker-compose.yml`(`APPROVAL_PROXY_SECRET`), `admin-web/electron/main.js`(Electron 은 실행마다 자동 생성 — 사용자 설정 불필요). 시험: `tests/test_human_session_p0c.py`(30개).
>
> 구현 세부: 인증 꺼짐(단독 모드)의 승인자 이름은 `local-owner`, `approved_via` 는 허용 목록의 `jwt` 로 기록한다. nonce 는 프로세스 메모리에 120초 기억한다(단일 워커 전제 — 다중 워커로 확장하면 공유 저장소로 옮긴다. 재전송이 다른 워커로 가도 승인 전이는 CAS 로 1회만 성공한다). 프록시는 승인 발급 경로에서 POST·same-origin·JSON 이 아니면 403, 비밀이 없으면 503 을 돌려주고, 클라이언트 `Authorization` 과 서버 Basic 은 쓰지 않는다.
>
> **후속 항목(이번 범위 아님)** — PIN 을 켰을 때의 불편을 줄이는 기능: ① PIN 확인 일정 시간 기억 ② 묶음 승인. 둘 다 PIN(P1)과 함께 설계한다.
> ③ **다중 워커 전환 시 nonce 기억을 공유 저장소로 옮길 것**(현재 운영 uvicorn 은 워커 1개 — W4 확인 — 라 프로세스 메모리로 충분).

### 13.1 발견: 백엔드의 Origin 검사는 프록시 구조에서 성립하지 않는다

- 관리 화면(`admin-web`)의 `/api/proxy/[...path]`는 백엔드로 `content-type`, `accept`, `cache-control`, `x-request-id`, `x-device-token`, `authorization`만 전달한다. **`Origin`·`Referer`·`Cookie`·`User-Agent`는 전달하지 않는다.** 쿠키의 JWT는 `Authorization: Bearer`로 바뀌어 간다.
- 따라서 백엔드가 `Origin`을 요구하면 **정상 화면 요청도 거부**되고, 요구하지 않으면 검사가 없는 것과 같다. 직접 호출하는 스크립트는 `Origin`·`Sec-Fetch-*` 헤더를 마음대로 쓸 수 있어 위조도 쉽다.
- 정리: Origin·Fetch-Metadata 검사는 *다른 사이트의 브라우저 요청(CSRF, A6)* 만 막는다. 백엔드는 쿠키가 아니라 `Authorization` 헤더로 인증하므로 클래식 CSRF는 원래 해당이 적고, **JWT를 가진 스크립트(A3 일부)와 서비스 자격(A1)은 Origin 검사로 막지 못한다.** 이 둘을 막는 것은 L1(JWT 전용·방식 구분), 아래의 프록시 증명, 그리고 PIN(L2)이다.
- §2.3의 L3 "Origin 검사"는 이 절로 **대체**한다.

### 13.2 대체안: 프록시가 증명하는 방식 (L3')

1. **백엔드 의존성 `require_human_session`** (`ai_orchestrator/gates/human_session.py`, 신규)
   - 인증 방식 도출: 요청의 `Authorization` 스킴으로 판단한다(`Bearer`→`jwt`, `Basic`→`basic`, 인증 꺼짐→`disabled`). `get_current_user`가 이미 한 가지 스킴만 검증하므로 도출은 안전하다. **`auth.py`와 사용자 dict에는 키를 추가하지 않는다** — `/auth/me`가 `{actor, role}` 정확 일치 응답을 계약 시험으로 고정하고 있어, 키를 더하면 API 계약이 바뀐다.
   - 조건: `jwt` + 역할 `admin`·`owner` + 프록시 증명 유효. 그 밖(Basic·MCP·인증 꺼짐·viewer/operator)은 403.
2. **프록시 증명 `X-Approval-Proxy`** (서버 비밀 `APPROVAL_PROXY_SECRET`)
   - admin-web 프록시가 `approvals/*/{approve,reject,revoke}` 경로에서만 다음을 한다.
     ① 브라우저 same-origin 요청만 통과(`Origin` 호스트 = 요청 호스트, `Sec-Fetch-Site: same-origin`, `Content-Type: application/json`) — CSRF 차단(A6)
     ② 클라이언트가 보낸 `Authorization`을 무시하고 쿠키→Bearer만 사용
     ③ `HMAC-SHA256(secret, METHOD | PATH | 타임스탬프 | sha256(본문) | sha256(Bearer))`을 `X-Approval-Proxy: <ts>.<nonce>.<hex>`로 첨부
   - 백엔드는 같은 비밀로 검증한다: 서명 일치, 타임스탬프 ±60초, nonce 1회용(재전송 차단, 기억 창 안에서), 본문·경로 변조 시 불일치.
   - 증명이 없거나 틀리면 403(응답에 비밀·기대값 비노출).
3. **fail-closed**: `APPROVAL_PROXY_SECRET`이 설정되지 않으면 발급 API(`approve`·`reject`·`revoke`)는 **503**(발급 미구성)으로 닫힌다. 제안(`POST /approvals/requests`)과 조회는 열려 있다(제안은 승인을 만들지 않는다).
4. **인증 꺼짐(단독 모드)**: §11-2대로 로컬 화면에서 발급 가능하다. 단 같은 프록시 경로(Electron 포함)를 거쳐 증명이 있어야 하고, PIN을 설정했으면 PIN이 필요하다. 이 모드는 JWT 구분이 없어 **PIN이 사실상 유일한 사람 요인**이다(§2.4에 같은 취지로 명시).

### 13.3 효과와 한계 (정직한 정리)

| 공격 | 막는가 | 수단 |
|---|---|---|
| A1 MCP·Basic 서비스 자격으로 발급 | 막음 | L1(jwt 전용) + 증명 비밀 없음 |
| 직접 백엔드를 호출하는 스크립트(JWT 소지) | 막음 | 증명 비밀 없음 → 403 |
| A6 다른 사이트의 브라우저 요청 | 막음 | 프록시의 same-origin 검사 |
| 증명 헤더 재전송·본문 변조 | 막음 | 타임스탬프·nonce·본문 해시 |
| 사용자 브라우저를 직접 조작하는 에이전트(A3) | **PIN 켠 경우만 막음** | PIN(L2). 꺼져 있으면 승인 버튼을 누를 수 있다(§2.4) |
| 서버 환경변수(`APPROVAL_PROXY_SECRET`)를 읽을 수 있는 프로세스 | 못 막음 | 범위 밖 — 서버 접근 통제 |
| PC 완전 장악 | 못 막음 | 범위 밖 |

### 13.4 구현·시험 계획 (P0c)

- 신규: `ai_orchestrator/gates/human_session.py`(의존성·증명 검증), `ai_orchestrator/routers/human_approval_router.py`(제안 `POST /approvals/requests` — admin·owner·operator 인증, 대기 목록·상세 조회, `approve`·`reject`·`revoke` — 사람 세션 전용), `router.py` 등록, admin-web 프록시 `route.ts` 분기와 서명 함수(`admin-web/src/lib/approvalProxy.ts`), `.env.example`에 `APPROVAL_PROXY_SECRET` 안내.
- 시험:
  - 인증 방식 행렬: 무인증 401, Basic(admin) 제안 200·발급 403, JWT viewer/operator 발급 403, JWT admin/owner + 증명 200.
  - 증명: 헤더 없음·서명 불일치·시각 초과·nonce 재사용·본문/경로 변조 403, 비밀 미설정 503.
  - `/auth/me` 응답 불변(계약 시험 기존 그대로 통과).
  - **교차 언어 시험**: 프록시의 서명 함수(`approvalProxy.ts`)를 `node`(type stripping)로 실행한 값을 파이썬이 검증해, 두 구현의 정규화 문자열이 같음을 고정한다.
  - **계약 시험**: MCP `API_REGISTRY`에 `approvals` 경로가 없음, `human_approval.approve`의 호출처가 발급 라우터 1곳뿐임(P0b의 AST 시험 갱신).
  - 차단 응답에 비밀·해시·승인 번호가 없음(R2d 정책 확장).
- PIN(L2)은 P1에서 구현한다. P0c 시점의 `approved_via`는 `jwt`다.
