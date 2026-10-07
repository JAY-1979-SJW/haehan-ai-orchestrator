# 로그인 토큰 쿠키 HttpOnly 전환 기준서

- 작성: 2026-10-07 (W4) / 브랜치 `stage/console-auth-jwt` / 상태: **DRAFT — 기준서만. 구현은 아래 선행 조건(JWT_SECRET 시작 점검·OWNER_EMAILS 병합) 뒤에 한다.**
- 근거: 이번 변경으로 로그인 JWT가 `require_role` 라우트 약 260개에 통하게 됐다(커밋 `0574dab5`). 토큰이 탈취되면 그 계정 권한 전체가 넘어가므로, 토큰을 JS가 읽을 수 없게 만든다.
- 이 PC에서는 **실제 브라우저·Electron으로 로그인 흐름을 검증할 수 없다.** §8에 사람이 확인해야 할 항목을 모았고, 그 확인 전에는 서버에 반영하지 않는다.

## 1. 현재 상태 (코드 확인)

| # | 사실 | 근거 |
|---|---|---|
| 1 | 쿠키 `haehan_ai_token`을 **JS가** `document.cookie`로 만든다 → HttpOnly 불가. 속성: `path=/`, `max-age=30일`, `samesite=lax`, `secure`는 https일 때만 | `admin-web/src/lib/userAuth.ts:22-32` |
| 2 | 같은 토큰을 **localStorage에도** 저장한다 | `userAuth.ts:17-24`(`getToken`·`setToken`) |
| 3 | 로그인 응답이 토큰을 JSON 본문으로 주고 페이지가 `setToken(token)` 호출 | `admin-web/src/app/login/page.tsx:22` |
| 4 | 서버가 `Set-Cookie`하는 곳이 없다 | `admin-web` 전체 grep(`Set-Cookie`·`cookies.set`) 0건 |
| 5 | localStorage 토큰을 직접 읽는 곳 4곳: `cafeShared.ts:32`, `AiAnalysisTab.tsx:14`, `ApiStatusBanner.tsx:20`, `userAuth.ts`의 `getMe`·`changePassword`(`:68`,`:91`) | grep `localStorage.getItem("haehan_ai_token")`·`getToken()` |
| 6 | 쿠키를 서버에서 읽는 곳: 미들웨어(서명 검증), 프록시(쿠키→`Authorization: Bearer`), `/ops` 서버 컴포넌트 | `middleware.ts:50-67`, `api/proxy/[...path]/route.ts:49-58`, `app/ops/page.tsx:57` |
| 7 | Electron은 userData `config.json`의 `auth_token`을 preload가 localStorage와 쿠키(`SameSite=Lax; max-age=31536000`, **Secure 없음**, 1년)로 복제한다 | `admin-web/electron/webview_preload.js:28-42`, `electron/lib/config.js:119-125`, `main.js:253` |
| 8 | CSP·보안 헤더 설정이 없다. `dangerouslySetInnerHTML` 사용은 0건 | `next.config.mjs`(헤더 없음), `middleware.ts` |
| 9 | 프록시는 쿠키가 있으면 클라이언트 JS 없이도 Bearer를 붙인다 → **클라이언트가 토큰을 들고 있을 필요가 없다** | `route.ts:52-58` |

→ 쿠키만 HttpOnly로 바꾸면 localStorage(2·5)에서 여전히 읽힌다. **쿠키·localStorage를 함께** 없애야 의미가 있다.

## 2. 목표와 비목표
- 목표: 로그인 토큰이 **브라우저 JS에 노출되지 않는다.** 서버가 `HttpOnly; Secure; SameSite=Lax` 쿠키로만 보관하고, 프록시가 서버에서 Bearer로 변환한다.
- 비목표: JWT 형식·만료(30일)·서명키 변경, 토큰 폐기 목록(blacklist), 다중 기기 로그아웃, 로그인 시도 제한(별도 과제). Basic 인증·AUTH_ENABLED=false(데스크톱 자기완결) 동작은 바꾸지 않는다.

## 3. 선행 조건 (순서 고정)
1. 서버 `.env`에 `JWT_SECRET` 설정(`21d392e5`의 시작 점검이 경고). 설정 전에는 admin-web 미들웨어가 서명 검증을 건너뛰어 쿠키 보호 의미가 반감된다.
2. OWNER_EMAILS 변경 병합(승인 대기) — role 판정이 확정된 뒤에 로그인 흐름을 만진다.
3. 위 둘이 **서버에 반영되어 로그인이 정상인 것**을 확인한 뒤 이 변경을 시작한다.

## 4. 설계

### 4-1. 쿠키를 서버가 설정한다
Next 라우트 핸들러(같은 출처, Node 런타임)를 추가한다. 미들웨어 공개 경로에 `/api/auth`가 이미 있어 별도 허용이 필요 없다(`middleware.ts:9`).

| 경로 | 동작 |
|---|---|
| `POST /api/auth/login` | 본문 `{email, password}`를 백엔드 `/api/v1/users/login`에 전달. 성공하면 **토큰은 응답 본문에 싣지 않고** `Set-Cookie: haehan_ai_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000`을 설정하고 `{user}`만 반환. 실패는 백엔드 상태·메시지를 그대로 전달(401·403 승인 대기 문구 유지) |
| `DELETE /api/auth/session` | 쿠키를 `Max-Age=0`으로 삭제 |
| `POST /api/auth/session` | **이전 사용자 이행용**(§4-5): 본문 `{token}`을 백엔드 `/api/v1/users/me`로 검증해 유효할 때만 같은 속성으로 쿠키를 설정. 이행 기간이 끝나면 제거 |

- `Secure`: 요청이 https(`x-forwarded-proto`)일 때 설정. 로컬 개발·Electron의 `http://127.0.0.1`/`localhost`는 Chromium이 보안 컨텍스트로 취급하므로 Secure 쿠키가 동작하는지 **실제로 확인한다**(§8). 동작하지 않으면 http 환경에서만 `Secure`를 생략하는 분기를 둔다.
- 로그인 화면(`login/page.tsx`)은 토큰을 받지 않고 `/api/auth/login`만 부른다. `setToken` 호출을 제거한다.
- 로그아웃(`about/page.tsx:127`, `mypage/page.tsx:41`)은 `clearToken()` 대신 `DELETE /api/auth/session` 호출 후 이동.

### 4-2. localStorage 토큰을 없앤다
- `userAuth.ts`의 `getToken`·`setToken`·`clearToken`에서 localStorage·`document.cookie` 사용을 제거한다. `getMe`·`changePassword`는 `Authorization` 없이 `/api/proxy/...`를 부른다(프록시가 쿠키로 Bearer를 붙임, `route.ts:52-58`).
- 직접 읽던 3곳(`cafeShared.ts:32`, `AiAnalysisTab.tsx:14`, `ApiStatusBanner.tsx:20`)은 `Authorization` 헤더 구성을 삭제한다.
- 이행 기간 동안만 `loadLegacyToken()`으로 localStorage를 한 번 읽어 `/api/auth/session`에 넘기고 **즉시 삭제**한다(§4-5).

### 4-3. 프록시 보강
- 쿠키 → Bearer 자동 변환이므로 교차 사이트 요청 위조(CSRF)를 `SameSite=Lax`에만 기대지 않는다. 프록시에서 **안전하지 않은 메서드(POST·PUT·PATCH·DELETE)**는 `Sec-Fetch-Site: cross-site`이거나 `Origin` 호스트가 요청 호스트와 다르면 403으로 거절한다(헤더가 없는 비브라우저 호출은 통과시키지 않을지 정책을 정해야 함 — Electron·서버 간 호출 영향 확인 필요).
- 클라이언트가 보낸 `Authorization`이 쿠키보다 우선하는 현재 규칙은 유지한다(데스크톱·테스트 호환).

### 4-4. 보안 헤더·CSP
`next.config.mjs`에 `headers()` 추가: `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`(Electron webview 프레임 사용 여부 확인 후), `Content-Security-Policy`. CSP는 먼저 **`Content-Security-Policy-Report-Only`**로 켜서 위반을 수집한 뒤 강제로 전환한다(인라인 스크립트·외부 이미지·`connect-src` 확인 필요).

### 4-5. 기존 로그인 사용자 이행
- 배포 직후 기존 사용자는 localStorage와 JS 쿠키를 가지고 있다. 첫 로드에서 localStorage 토큰이 있으면 `POST /api/auth/session`으로 서버가 검증·쿠키 설정 → 성공 시 localStorage·옛 JS 쿠키 삭제. 실패하면 로그인 화면으로.
- 옛 JS 쿠키(HttpOnly 아님)와 같은 이름의 서버 쿠키가 공존할 수 있다. 서버 쿠키 설정 응답에서 옛 쿠키를 `Max-Age=0`으로 지우는 `Set-Cookie`를 함께 보내고, 같은 이름·경로·도메인 속성이 맞는지 **실제 브라우저에서 확인**한다.
- 이행 기간(예: 2주) 후 `POST /api/auth/session`·`loadLegacyToken` 제거.

### 4-6. Electron(데스크톱 웹뷰)
- 현재 preload가 `document.cookie`·localStorage에 토큰을 넣는다(`webview_preload.js:28-42`). HttpOnly 쿠키는 JS로 만들 수 없으므로 **main 프로세스**가 `session.cookies.set({url, name:'haehan_ai_token', value, httpOnly:true, sameSite:'lax', expirationDate: 30일})`로 설정하도록 바꾸고, preload의 localStorage·쿠키 복제를 제거한다. 만료는 JWT와 같은 30일로 맞춘다(현재 1년).
- 웹뷰가 **어느 세션(partition)을 쓰는지**에 따라 쿠키가 닿지 않을 수 있다 → §8에서 확인.
- AUTH_ENABLED=false 자기완결 모드는 토큰이 필요 없고(`get_jwt_user`가 owner 반환) `OWNER_MODE`는 미들웨어를 끈다 — 이 경로는 바꾸지 않는다.

### 4-7. 서버 컴포넌트·미들웨어
- `app/ops/page.tsx:57`과 미들웨어는 이미 쿠키를 서버에서 읽으므로 변경 없음(HttpOnly여도 서버는 읽는다).
- 미들웨어는 `JWT_SECRET`이 없으면 서명 검증을 건너뛴다(`middleware.ts:57-67`). §3 선행 조건 1이 지켜지면 항상 검증한다. 이 건너뛰기를 운영에서 막을지(미설정이면 로그인 페이지로) 별도 결정.

## 5. 변경 범위 (예상)
| 파일 | 변경 |
|---|---|
| `admin-web/src/app/api/auth/login/route.ts`(신규), `.../session/route.ts`(신규) | 쿠키 설정·삭제·이행 |
| `admin-web/src/lib/userAuth.ts` | localStorage·document.cookie 제거, 이행 함수 |
| `admin-web/src/app/login/page.tsx`, `about/page.tsx`, `mypage/page.tsx` | 로그인·로그아웃 호출 교체 |
| `cafeShared.ts`, `AiAnalysisTab.tsx`, `ApiStatusBanner.tsx` | Authorization 구성 삭제 |
| `admin-web/src/app/api/proxy/[...path]/route.ts` | 교차 사이트 변경 요청 차단 |
| `admin-web/next.config.mjs` | 보안 헤더·CSP(Report-Only) |
| `admin-web/electron/webview_preload.js`, `main.js` | 쿠키를 main 프로세스에서 설정, preload 복제 제거 |
| 시험 | 라우트 핸들러 단위 시험(쿠키 속성·실패 전달·본문에 토큰 없음), 프록시 CSRF 시험, 기존 `node` 시험 실행기가 없으므로 **실행기 도입 여부를 먼저 결정**(admin-web에는 jest·vitest가 없음) |

백엔드(`ai_orchestrator`) 변경은 없다(JWT 발급·검증은 그대로).

## 6. 위험
- **로그인 흐름 전체를 건드린다.** 잘못되면 전원이 로그인하지 못한다 → 이행 경로(§4-5)와 롤백(§7)을 갖추고 실제 브라우저로 확인한 뒤 반영.
- Electron 웹뷰의 쿠키 경로(partition)가 맞지 않으면 데스크톱 앱이 로그인 화면에서 막힌다.
- Secure 쿠키가 http 환경(로컬·Electron)에서 거부되면 로그인이 안 된다.
- CSP를 강제로 켜면 인라인 스크립트·외부 리소스가 막힐 수 있다 → Report-Only 선행.
- 프록시의 `Sec-Fetch-Site`/`Origin` 차단이 Electron·서버 간 호출·테스트를 막을 수 있다.
- 토큰 폐기 수단이 없어(로그아웃은 쿠키 삭제뿐, 토큰 자체는 30일 유효) 쿠키가 이미 새어 나갔다면 HttpOnly 전환으로는 회수되지 않는다. 필요하면 `JWT_SECRET` 교체로 전원 로그아웃(§3 키 설정 시점에 이미 1회 발생).

## 7. 롤백
- 라우트 핸들러·프록시 변경은 이전 커밋으로 되돌리면 된다. 쿠키 이름이 같으므로 이전 코드(`document.cookie`)로 돌아가도 새로 심은 HttpOnly 쿠키는 JS가 덮어쓰지 못해 **로그인 상태가 꼬일 수 있다** → 롤백 시 `DELETE /api/auth/session`으로 쿠키를 지우는 안내(전원 재로그인)를 포함한다.
- 이행 기간 동안은 localStorage 이행 경로가 있어 부분 롤백이 가능하다.

## 8. 실제 브라우저·Electron으로 확인해야 할 항목 (이 PC에서는 못 함)
**브라우저(Chrome·Edge, https 운영 도메인과 http 로컬 각각)**
1. 로그인 후 개발자도구 Application→Cookies에서 `haehan_ai_token`이 **HttpOnly ✓, Secure ✓(https), SameSite=Lax, Max-Age 30일**.
2. 콘솔에서 `document.cookie`에 토큰이 **보이지 않는다**. `localStorage`에 `haehan_ai_token`이 **없다**.
3. 로그인 응답(네트워크 탭)의 본문에 **토큰이 없다**.
4. 새로고침·새 탭에서 로그인 유지, 미로그인 상태에서 보호 경로 접근 시 로그인으로 이동(미들웨어).
5. AI 작업 콘솔 채팅이 정상(`/chat/sessions`·`/ai-agent/run`이 쿠키→Bearer로 200).
6. `/ops` 서버 컴포넌트 패널이 정상(서버가 쿠키를 읽음).
7. 로그아웃 후 쿠키가 사라지고 보호 경로가 막힌다. 만료된 토큰(시간 경과·서명키 교체)에서 로그인 화면으로 간다.
8. **기존 사용자 이행**: 배포 전 로그인해 localStorage 토큰을 가진 브라우저가 배포 후 첫 로드에서 자동으로 서버 쿠키로 이행되고 localStorage·옛 JS 쿠키가 지워진다. 옛 쿠키와 새 쿠키 중복이 없는지.
9. **교차 사이트 변경 요청 차단**: 다른 출처의 페이지에서 `/api/proxy/...`로 POST를 보내면 403(쿠키가 실려도 거절).
10. CSP Report-Only 위반 보고에 정상 화면의 위반이 없는지(있으면 정책 조정 후 강제).
11. 비밀번호 변경·가입 승인 대기 로그인 등 기존 흐름(`mypage`, `login`의 403 문구).

**Electron(데스크톱)**
12. 앱 실행 시 자동 로그인 유지(저장된 `auth_token` → main 프로세스가 설정한 쿠키), 앱 재시작 후에도 유지.
13. 웹뷰가 쓰는 세션(partition)에 쿠키가 실제로 들어간다(`/ops`·채팅 정상).
14. `http://127.0.0.1:3000`에서 Secure/HttpOnly 쿠키가 거부되지 않는다.
15. AUTH_ENABLED=false 자기완결 모드·`OWNER_MODE`에서 로그인 없이 동작이 이전과 같다.
16. 쿠키 만료가 30일로 맞춰졌고, 만료 후 재로그인이 정상.

## 9. 결정 필요
1. admin-web **시험 실행기 도입**(jest 또는 vitest) 여부 — 없으면 §5의 시험을 만들 수 없고 §8 수동 확인에 전적으로 의존한다.
2. 프록시 CSRF 차단에서 `Origin`·`Sec-Fetch-Site` 헤더가 없는 호출(서버 간·Electron)을 허용할지.
3. Electron 쿠키 설정을 main 프로세스로 옮기는 변경의 승인(데스크톱 로그인 경로 변경).
4. 미들웨어가 `JWT_SECRET` 미설정일 때 서명 검증을 건너뛰는 동작을 운영에서 금지할지.
5. 이행 기간(권장 2주)과 옛 쿠키·localStorage 정리 시점.
