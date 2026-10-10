# R2d-2 — 사람이 발급하는 1회용 승인 설계서

- 상태: **설계안(구현 전, 대표님 승인 대기)**
- 작성: W3, 기준: stage/r2-side-effect-gates (R2d-1 완료 상태)
- 관련: `docs/architecture/` R2 문서군, `C:\work\_coordination\R2_side_effect_gates.md`(경로별 전수 표)

## 0. 한눈에 보기

**문제.** 지금 외부 발행·발송은 *고정 문자열 문구*(`CONFIRM_TEXTS`)로 막혀 있다. 코드를 읽을 수 있는 AI 에이전트는 그 문구를 그대로 넣을 수 있고, 승인이 *무엇을* 승인했는지(내용)도 묶여 있지 않다. 예약 실행은 승인 뒤에 내용이 바뀌어도 새 내용이 실행된다.

**제안.** 승인을 "문구"에서 **"사람이 로그인한 화면에서 발급한, 특정 내용에 묶인 1회용 기록"** 으로 바꾼다.

| 항목 | 현재 | 제안 |
|---|---|---|
| 승인의 정체 | 코드에 적힌 고정 문구 | 서버에 저장된 승인 기록(대상 작업·수신자·**내용 해시**·만료·1회) |
| 발급 주체 | 누구든 문구를 알면 | **JWT 로그인 사용자(owner/admin)** + **승인 PIN**(사람만 아는 비밀) |
| AI의 역할 | 문구를 알면 승인까지 가능 | 내용을 **제안하고, 승인된 것을 실행**할 수만 있다. 승인은 못 만든다 |
| 실행 직전 | 문구 문자열 비교 | 실제 내용의 해시를 다시 계산해 승인 기록과 대조, **원자적 소진** |
| 예약 실행 | 회차마다 버튼 한 번, 내용 변경 후에도 실행 | 예약 생성 시 내용 승인, **실행 시 해시 대조**, 다르면 중단+재승인 |

**대표님께 결정을 받을 것은 §11의 5가지**다(승인 PIN 도입, 데스크톱 단독 모드 처리, 예약 승인 방식, 텔레그램 승인의 지위, 이행 기간).

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
| L2 사람 요인 (step-up) | 발급 요청에 **승인 PIN**이 필요. 사용자가 화면에서 직접 입력한다. 서버에는 솔트 해시만 저장, 5회 실패 시 잠금(분 단위 증가), 실패는 감사 기록. PIN은 JWT·쿠키·로컬스토리지·화면 코드 어디에도 저장하지 않는다 | **A3**(JWT를 훔쳐도 PIN을 모름), A2 |
| L3 출처 검사 | 발급 API는 `Origin`/`Referer`가 허용 목록(관리 화면 도메인)이고 `Sec-Fetch-Site`가 same-origin일 때만. 본문 `Content-Type: application/json` 강제(단순 요청 폼 차단) | A6 |
| L4 승인 비노출 | 승인은 **서버 저장 기록**이고 비밀 토큰이 없다. 실행은 실제 내용을 해시해 일치하는 승인을 소진한다. 차단 응답·로그에 문구·PIN·해시 원문을 싣지 않는다 | A2 |
| L5 내용 결속·1회·만료 | 해시·대상 불일치 또는 만료·소진이면 실패. 소진은 DB의 원자적 갱신(CAS) | A4, A5 |
| L6 에이전트 도구 차단 | 발급·PIN 설정 엔드포인트는 MCP `API_REGISTRY`에 없다. "MCP 레지스트리에 발급 경로가 없음", "발급 경로가 `jwt` 외에서 403"을 **계약 시험**으로 고정 | A1 |
| L7 승인 채널 정리 | 외부 발행·발송 승인은 **텔레그램·`approve_token(role=...)` 자기 승인 경로를 인정하지 않는다**(§11-4). 기존 코드 하드코딩 승인은 새 승인과 분리 | A7 |

**쿠키 `HttpOnly` 전환(W4 후속 ②)을 선행 조건으로 둔다.** 전환하면 에이전트가 JS로 JWT를 읽을 수 없다(A3 약화). 그래도 L2(PIN)는 유지한다. 브라우저를 조작해 *화면에서* 승인 버튼을 누르는 에이전트는 PIN을 입력할 수 없기 때문이다.

### 2.4 잔여 위험(막지 못하는 것)

- 사용자 PC를 완전히 장악한 에이전트(키 입력 가로채기, PIN 입력을 화면에서 관찰)는 못 막는다. 그 경우 사용자 본인도 속는다.
- 사용자가 PIN을 에이전트에게 알려 주면 무의미하다. PIN은 문서·채팅·로그에 적지 않는다는 운영 규칙이 필요하다.
- 내용 해시는 *내용 변경*을 막지만 *처음부터 나쁜 내용*을 사람이 승인하는 것은 막지 못한다. 화면은 사람이 실제 내용을 보게 해야 한다(§5).
- `AUTH_ENABLED=false` 단독 모드(§11-2).

## 3. 승인 기록과 흐름

### 3.1 흐름 (AI는 제안·실행만, 사람이 승인)

```
(1) 제안   누구나(에이전트 포함) 인증된 호출자 → POST /approvals/requests
             {op, target, content}  → 서버가 내용 스냅샷·해시 저장, 상태 pending, request_id 반환
(2) 승인   사람(owner/admin, Bearer JWT, PIN) → POST /approvals/{id}/approve
             화면이 스냅샷 전체를 보여 주고 PIN 입력 → 상태 approved(만료 시각 설정)
(3) 실행   원래 발행·발송 함수 → consume_approval(op, target, content)
             실제 content 를 해시 → (op, target_hash, content_hash)가 일치하는 approved 기록을
             `UPDATE ... SET status='used' WHERE status='approved' AND expires_at>now` 로 소진
             소진 실패 → GateBlocked(문구·토큰 미노출)
```

- 토큰이 없다. 에이전트가 가진 것은 `request_id`(내용 스냅샷의 번호)뿐이고, 승인 상태는 서버만 안다. **승인된 내용과 한 글자라도 다르면 실행되지 않는다.**
- 사용자가 화면에서 직접 발행하는 흐름은 (1)(2)(3)을 한 번에 이어 주는 UI로 만든다. 사용자는 확인 모달에서 내용을 보고 PIN을 입력하는 한 번의 조작만 한다.

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

**원인**: 게이트 핵심 `scripts/common/gate.py`가 scripts 패키지에 있고, `ai_orchestrator`와 `scripts`가 서로를 쓴다. 게이트 핵심은 `scripts.common.logger`, `scripts.common.schemas`(`GateResult`, `GateVerdict`, `RiskLevel`), `scripts.common.op_log`(함수 안 import)에 의존한다.

**계획**
1. `tools/gates/gate_core.py`를 만들어 게이트 핵심(`check`, `require_side_effect`, `require_approved`, 수신거부 목록, 승인 소진)을 옮긴다. 층은 같은 L2.
2. **`gate_core`는 `scripts`를 import하지 않는다.** 필요한 타입(`GateResult`/`GateVerdict`/`RiskLevel`)은 `gate_core`에 정의하고, `scripts/common/schemas.py`가 거기서 재수출한다(의존 방향을 뒤집음). 로깅은 표준 `logging`, 감사 기록은 **싱크 등록**(`gate_core.set_audit_sink(fn)`)으로 주입하고 `scripts/common/op_log.py`가 import 시점에 등록한다.
3. `scripts/common/gate.py`는 **shim**으로 남긴다. 저장소의 분리 shim과 같은 방식(`sys.modules[__name__] = import_module("tools.gates.gate_core")`). 모듈 전역 상태(`_RISK_REGISTRY`, `force_approved`의 thread-local)는 한 객체로 공유되므로 동작이 같다.
4. `ai_orchestrator` 쪽 호출자(`send_approval.py`, 라우터들)는 새 경로를 직접 import한다. `scripts` 쪽 호출자는 shim을 그대로 쓰다 점진 이전한다(R2 커버리지 테스트의 `GUARDS` 이름은 유지).
5. 검증: `verify_change`의 순환 수가 80으로 돌아오는지 확인한다. 돌아오지 않으면 남은 `gates → scripts` 간선을 목록으로 보고하고 알려진 항목으로 기록한다.

**주의**: mypy는 `sys.modules` 치환 shim을 정적으로 따라가지 못하므로(R-split 경험), 이전된 모듈 간 import는 새 경로로 쓴다. `scripts/common/gate.py`를 import하는 29곳은 shim으로 계속 동작한다.

## 5. 승인 화면(UI)

- **관리 화면(`admin-web`)에 "승인 요청함"** 페이지를 둔다. 대기 중인 요청의 *실제 내용 전체*(제목·본문·수신자·첨부 미리보기)를 보여 주고, PIN을 입력해 승인/거부한다. 승인 직전에 내용이 바뀌면(요청이 새 해시로 대체되면) 화면이 갱신을 알린다.
- 기존 모달(R2b/R2d)은 같은 `Modal`에 **내용 요약 + PIN 입력란**으로 교체한다. 확인 문구 안내(`SEND_CONFIRM_HINT`)는 없앤다.
- PIN은 `type="password"`, `autoComplete="off"`, 상태에 보관하지 않고 요청 직후 비운다. 서버 응답은 PIN 오류 시 남은 횟수만 알린다.
- **PIN 설정**: owner가 서버 설정 화면(`OWNER_EMAILS`로 지정된 owner, W4)에서 직접 설정·변경한다. 에이전트용 API는 만들지 않는다. 설정은 JWT + 현재 PIN(최초 설정은 서버 설치 시 환경변수의 일회용 코드) 필요.

## 6. 예약 실행 통합

**현재의 문제**는 §1-3. 설계:

1. 예약 **생성/수정 화면**이 내용 전체와 실행 계획(언제, 몇 회, 수신자)을 보여 주고 PIN으로 승인한다. 승인 기록은 `schedule_job_id`와 `content_hash(params)`를 담고 `expires_at`·`max_uses`(= 예정 회차 수)를 가진다.
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
- 바뀌는 것은 **승인 행위**뿐이다. 지금의 `POST /authorizations/{id}/approve`(`confirmed:true`)를 승인 요청함의 PIN 승인으로 일원화한다. 서비스는 승인 기록(`op=hanafax_send`, `content_hash=scope_hash`)이 `approved`일 때만 `store.approve`를 호출한다.
- 단건 `/hanafax/send`는 일반 `consume_approval` 경로. `batch/execute`의 `HANAFAX_APPROVED_BATCH` 문구와 `scripts/hanafax/batch.py`·캠페인 스크립트·`hanafax_auto_sender`(R2e 후보)는 승인서 경로로 편입하거나, 승인서 없이는 실행되지 않게 한다.
- 승인서의 `approved_by`는 승인 기록의 `approved_by`를 쓴다(JWT actor). 승인서 승인에도 `auth_method=jwt` + PIN을 요구한다.
- 범용으로 합칠 수 있는 것(승인 기록·PIN·만료·CAS·플래그 저장)은 새 승인 스토어로 옮기고, **팩스 고유 로직(번호 정규화, 한도, 로그)은 남긴다.**

## 8. 이행 계획 (호출자별 단계)

원칙: **새 방식을 먼저 병행 도입**하고, 호출자별로 옮긴 뒤, 마지막에 상수 문구를 제거한다. 병행 기간에는 환경변수 `GATE_LEGACY_PHRASE`(기본 true)로 기존 문구를 계속 받는다. 모든 호출자를 옮기면 기본값을 false로, 이어서 코드를 제거한다.

| 단계 | 내용 | 선행 조건 |
|---|---|---|
| P0 | 승인 스토어(SQLite), `consume_approval`, 발급 API(L1·L3), 감사 기록, 게이트 핵심 이전(§4). 아직 아무 호출자도 바꾸지 않음 | W4 Bearer + `auth_method` |
| P1 | PIN 설정·검증(L2), 실패 잠금. `HttpOnly` 쿠키 전환(W4) 확인 | owner 지정 `OWNER_EMAILS` |
| P2 | 승인 요청함 화면 + 확인 모달 교체 | P0–P1 |
| P3 | 화면에서 쓰는 경로부터 이전: Gmail `/reply`·`/send`, 블로그 `/write-to-naver`, hiworks·eum `/send`, 하나팩스 `/send` | P2 |
| P4 | 예약 실행(§6), 하나팩스 승인서(§7) | 대표님 결정(§11-3) |
| P5 | CLI·스크립트: 문구 `--confirm` → `--approval-id`(제안은 CLI가 만들고, 승인은 화면). `blog_*`, `publish_ep_batch*`, `eum_send_mail_batch`, `ig_batch`, `hanafax send`, `hiworks send-batch` | P3 |
| P6 | 에이전트 호출 경로: `smartstore submit_reply`, `drive share_link`, 인스타·유튜브 함수, MCP 도구 설명. 에이전트는 제안→(사람 승인)→실행 | P3 |
| P7 | `GATE_LEGACY_PHRASE=false` 기본, `CONFIRM_TEXTS`·모든 문구 안내 제거, 커버리지 테스트의 가드 이름을 `consume_approval`로 교체 | P3–P6 완료 |

- **함수 서명 변화**: `approval: str | None`(문구) → `approval_id: str | None`(승인 요청 번호, 선택) + 내용은 이미 인자로 갖고 있으므로 *내용으로 승인을 찾는다*. `approval_id`는 편의일 뿐 보안 요소가 아니다.
- **W2(마케팅 운영)**: `marketing_ops_router`는 P3에서 같은 `consume_approval`을 쓰도록 안내한다.
- **롤백**: 각 단계는 독립 커밋. P3 이전 호출자는 `GATE_LEGACY_PHRASE=true`로 즉시 기존 방식으로 복귀 가능.

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
- **PIN(L2)**: 틀린 PIN은 승인 안 됨, 5회 후 잠금, 잠금 중 올바른 PIN도 거부, 성공 시 카운터 초기화, 동시 시도에서 카운터 정확.
- **출처(L3)**: Origin/Referer 불일치·`Sec-Fetch-Site: cross-site`·비JSON 본문 → 403.
- **내용 결속(L5)**: 승인 후 한 글자 변경, 수신자 추가, 첨부 교체 → 소진 실패. 정확히 같은 내용만 통과. 만료·거부·철회 후 실패.
- **1회·경쟁**: 같은 승인으로 두 번째 실행 실패, 동시 16개 실행에서 정확히 1건만 성공(프로세스 간 포함).
- **비노출(L4)**: 모든 차단 응답·로그에 문구·PIN·해시 원문이 없음을 경로별로 고정(R2d 시험 확장).
- **계약(L6)**: MCP `API_REGISTRY`에 발급·PIN 경로가 없음. 에이전트 도구 목록에서 `approvals/*/approve` 호출 불가.
- **예약**: 승인 후 `update()`로 본문 변경 → 실행 중단+알림, 승인 철회 확인. `approve`와 `update` 경쟁에서 일관성. 만료·최대 회차 초과 시 중단.
- **하나팩스**: 승인서 승인에 PIN이 필요하고 `scope_hash`가 승인 기록과 일치할 때만 `store.approve`.
- **커버리지**: 기존 AST 기준선 테스트의 가드 목록에 `consume_approval`을 추가하고, P7에서 `require_approved`/문구 가드를 제거. 스캐너는 호출명 패턴이 아니라 **발행·발송 sink 함수 목록**을 명시한다(`write_post`·`edit_post`·`confirm_publish`를 추가해 사각지대였던 BlogWriter 계열 발행 경로를 잡음). 새로 잡힌 기존 경로(예약 실행 `_run_blog_publish`, `marketing_ops_router.publish_blog`, 카페·`_runner` 등 10건)는 기준선에 고정했고, 예약 실행은 §6에서, `publish_blog`는 W2 연결에서 기준선을 줄인다.
- **게이트 이전**: 이전 전후 동작 동일(기존 29곳 호출자 특성화 시험), `verify_change` 순환 수.

## 11. 대표님 결정이 필요한 것

1. **승인 PIN 도입 (권장: 도입).** 이 설계에서 "AI가 승인을 만들 수 없다"는 보장의 핵심이다. 없으면 에이전트가 사용자의 로그인된 브라우저로 승인 버튼을 누르는 경우를 막을 수 없다. 대안: PIN 없이 JWT+Origin만(보장이 약해짐).
2. **`AUTH_ENABLED=false` 데스크톱 단독 모드.** 이 모드는 모든 요청이 더미 owner다. 권장: 이 모드에서는 외부 발행·발송 승인을 **발급할 수 없게** 해 발송이 막히도록 하고, 데스크톱 앱에는 "로그인 모드로 전환" 경로를 안내한다. 대안: 앱 로컬 확인창(OS 네이티브 대화상자)을 별도 승인 수단으로 허용(구현·검증 부담 큼).
3. **예약 승인 방식.** 권장 A(예약 생성 시 내용 승인 + 유효기간·최대 회차 + 실행 시 해시 대조). 대안 B(회차마다 승인 유지).
4. **텔레그램 등 기존 승인 채널의 지위.** 권장: 외부 발행·발송 승인으로는 **인정하지 않음**(봇 토큰·자동화 접근 위험). 텔레그램은 *알림 전용*. 개발 등록 승인(`dev_reg_approval`) 등 기존 용도는 이번 범위 밖.
5. **이행 기간.** 권장: 병행 기간 동안 `GATE_LEGACY_PHRASE=true`를 두고 P3·P5 완료 후 끄기. 한 번에 전환하면 스크립트·CLI 사용이 일시 중단된다.

## 12. 범위와 비범위

- **이번 문서**: 설계만. 구현은 대표님 승인 후 단계별 커밋(P0부터).
- **범위 밖**: `apps/ig-comment-dm-bot`·`apps/marketing-standalone`(별도 앱), 개발 등록 승인(`dev_reg_approval`), `scripts/google/common/drive.py` CLI 업로드, 네이버 대량메일·하나팩스 대량의 자체 상한 정책(승인 행위만 통합).
- **의존**: W4의 Bearer·`OWNER_EMAILS`·`HttpOnly` 쿠키 전환 및 `auth_method` 표지. W2의 `marketing_ops_router`는 P3에서 합류.
