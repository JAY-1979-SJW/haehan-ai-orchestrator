# 기준서 — 배포 클라이언트 씬(Thin) 전환

Status: DRAFT (승인 대기)
작성일: 2026-06-02
작성 근거: 4개 조사 에이전트 + 원격 서버 직접 probe + 코드 라인 확인
관련: `docs/architecture/APP_STRUCTURE.md`(server-first 원칙), `docs/architecture/APP_TREEMAP.md`

---

## 1. 배경과 목적

### 목적 (사용자 확인)
- exe를 만들어 **불특정 다수에게 배포**
- **서버(haehan-ai.kr)에서 통제**

### 현재 문제
`APP_STRUCTURE.md`는 "서버가 신원·인증·승인·정책·작업큐를 소유"하는 server-first 설계를 명시.
그러나 현재 구현은 **클라이언트 PC마다 서버 전체(FastAPI + Next.js)를 복제**해 넣음 → 목적과 정반대.

### 이 전환으로 얻는 것
| 항목 | 현재(풀 번들) | 전환 후(씬) |
|------|--------------|------------|
| 설치본 크기 | ~1GB | ~200MB |
| 사용자 차단 | 어려움 | 서버에서 즉시 |
| 기능 수정 | 1GB 재배포 | 서버만 수정 |
| 빌드 안정성 | 취약(오늘 3개 버그) | 부품 감소로 안정 |

---

## 2. 핵심 설계 원칙

> 배포 클라이언트 PC에 **물리적으로 로컬에 있어야 하는 것은 `local-agent`(브라우저 자동화)뿐.**
> 나머지(UI, 인증, 승인, 작업큐)는 원격 서버가 담당.

```
owner(개발자) PC          배포 클라이언트 PC
─────────────────         ─────────────────
Electron                  Electron (얇은 셸)
  + 로컬 FastAPI(8401)       → 원격 UI 로드
  + 로컬 Next.js(3000)       (haehan-ai.kr)
  + CDP Chrome              + CDP Chrome
  + local-agent             + local-agent
  (전부 로컬)                 → 원격 wss 연결
                            ※ 로컬 FastAPI/Next.js 없음
```

분기 스위치: **이미 존재하는 `config.owner_mode`** (`lib/config.js:52`)

---

## 3. 변경 범위 (파일별)

### 3-1. `admin-web/electron/lib/config.js` (L10 설정)
- 추가: 모드별 URL 해석 함수
  - owner: `SERVER_URL=http://127.0.0.1:3000`, `FASTAPI_URL=http://127.0.0.1:8401` (현행 유지)
  - client: `SERVER_URL=https://haehan-ai.kr/orchestrator`, `AGENT_WS=wss://haehan-ai.kr/orchestrator`
- 기존 상수는 보존, 신규 함수만 추가 (코드 보존 원칙)

### 3-2. `admin-web/electron/main.js` (L10 진입점)
- `app.whenReady()` 안에서 **모드 분기 추가**:
  - owner 모드 → 현행 그대로 (FastAPI + Next.js + CDP + agent 전부 로컬 시작)
  - client 모드 → **로컬 FastAPI/Next.js 시작 생략**, CDP + agent만 시작, 원격 UI 로드
- 변경 라인: 64~91 (FastAPI/Next.js 시작) 을 `if (isOwnerMode)` 로 감쌈

### 3-3. `admin-web/electron/lib/mainWindow.js` (L9 UI)
- L34: webview `?server=` 값을 모드별 SERVER_URL로
  - owner → localhost:3000
  - client → 원격 UI URL

### 3-4. `admin-web/electron/lib/agent.js` (L3)
- L55: `--server` 인수를 모드별로
  - owner → `ws://127.0.0.1:8401` (현행)
  - client → `wss://haehan-ai.kr/orchestrator`

### 3-5. 패키징 (`admin-web/electron/package.json`, specs)
- **빌드 프로파일 2개로 분리**:
  - owner 빌드: 현행 extraResources 전부 (haehan-server + nextjs + local-agent)
  - **client 빌드: local-agent만** (haehan-server, nextjs 번들 제외) → ~200MB
- `scripts/build_with_gates.py`에 `--profile client|owner` 옵션 추가

---

## 4. ✅ 원격 서버 실측 결과 (2026-06-02, SSH 직접 확인)

서버 haehan-ai.kr = **1.201.176.236 (haehan-app)**. 리버스 프록시 = `nginx` 컨테이너.
컨테이너 현황: `haehan-ai-orchestrator-api`(8400, healthy), `haehan-ai-orchestrator-admin-web`(3000, UI 가동).

### nginx 라우팅 실측 (`nginx` 컨테이너 `/etc/nginx/conf.d/default.conf`)

| 경로 | 접근 제어 | 프록시 대상 | 용도 |
|------|----------|------------|------|
| `/orchestrator/admin-web/` | **IP 허용목록** (220.79.246.190=owner, 서버, localhost, docker) `deny all` | admin-web:3000 | **owner 전용 관리 콘솔** |
| `/orchestrator/` (API) | **IP 허용목록** (동일) | 172.18.0.1:5050 | owner 전용 |
| `/orchestrator/api/v1/local-agents/register-with-code` | **공개** (1회용 코드가 보안) | api:8400 | **배포 클라이언트 등록** |
| `/orchestrator/api/v1/local-agents/ws` | **공개** (device_token이 보안, IP락 제거됨) | api:8400 (WS) | **배포 클라이언트 통제 연결** |
| `/orchestrator/api/v1/local-agents/` (그 외) | IP 허용목록 | api:8400 | owner 관리 |

### 실측 응답
- `admin-web/` → 200 (단, 내 IP=220.79.246.190 = 허용된 owner IP라서. **타인은 차단**)
- `register-with-code` → 422 (공개 엔드포인트 **존재** ✅)
- `local-agents/ws` → 공개 (device_token 인증)

### ⚠️ 기준서 핵심 가정 정정

**틀린 가정:** "배포 클라이언트가 원격 UI를 로드한다"
→ **불가.** UI(`admin-web`)는 **owner IP에 잠겨 있음**. 의도된 설계는 UI = owner 전용 관리 콘솔.

**실제 서버가 구현한 배포 모델:** 클라이언트는 **헤드리스 통제 에이전트**.
- 1회용 코드로 등록(`register-with-code`)
- `device_token`으로 WS 연결(`local-agents/ws`)
- **owner가 자기 관리 콘솔에서 → 서버 → 클라이언트 에이전트들을 통제**

```
[owner 관리 콘솔]  (IP 잠김, 220.79.246.190)
      │ 작업 지시
      ▼
[서버 haehan-ai.kr]  (작업큐 · 승인 · device_token 레지스트리)
      │ 공개 WS로 디스패치 (device_token 인증)
      ▼
[배포 클라이언트 N대]  1회용 코드로 등록된 local-agent
      각자 PC에서 브라우저 자동화 실행, 서버가 통제
```

이것이 "서버에서 통제 + 불특정 다수"의 실제 구현 형태. 단, **배포 클라이언트는 newer `local-agents/ws`(device_token) 프로토콜**을 써야 함 — 현재 owner-로컬 코드가 쓰는 `smartstore/agent/ws?license=`(구 프로토콜)가 아님.

---

## 4-B. 확정 목표: 모델 A + B 동시 (멀티유저 SaaS + 중앙 통제)

사용자 결정(2026-06-02): **두 모델 다.**
- 모델 A: owner가 관리 콘솔에서 모든 클라이언트 에이전트를 중앙 통제
- 모델 B: 배포 사용자가 각자 로그인해 자기 화면에서 직접 조작

### 통합 아키텍처
```
[owner super-admin 콘솔]──┐         [사용자별 로그인 UI]──┐
                          │                              │
                          ▼                              ▼
              [서버 haehan-ai.kr] (멀티테넌트: 사용자별 데이터 격리 + 작업큐 + 승인)
                          │ 공개 WS (device_token)
                          ▼
              [배포 클라이언트 N대] Electron(얇음) + local-agent
                                    각 PC에서 브라우저 자동화
```

### 클라이언트는 항상 "얇게" 유지
- 배포 exe = **Electron 셸 + local-agent.exe만** (haehan-server.exe·Next.js 번들 없음, ~200MB)
- UI는 원격 서버가 사용자별로 제공 (모델 B), 통제는 device_token WS (모델 A)

### 서버에 이미 있는 것 vs 추가 필요
| 부품 | 상태 |
|------|------|
| 사용자 로그인 (JWT) `users/login` | ✅ 있음 (422 확인) |
| 기기 등록 `register-with-code` | ✅ 공개 가동 |
| 통제 WS `local-agents/ws` (device_token) | ✅ 공개 가동 |
| 작업큐·승인·레지스트리 | ✅ 있음 |
| **UI 멀티유저 접근** (현재 owner IP 잠김) | ⚠️ **추가 필요** — IP락 → 사용자별 JWT 인증 전환 |
| **사용자별 데이터 격리(테넌트)** | ⚠️ **확인/추가 필요** |

---

## 4-C. 단계별 실행 로드맵

### Phase 1 — 배포 클라이언트 기반 (서버 변경 0, 모델 A 토대)
- 클라이언트 빌드 프로파일 분리: Electron + local-agent만 (~200MB)
- local-agent를 **newer `local-agents/ws`(device_token) 프로토콜**로 전환 (현 `smartstore/agent/ws?license=` → 신규)
- register-with-code 온보딩 흐름
- 산출: 1회용 코드 입력 → 서버 연결 → owner 콘솔에서 통제 가능
- **서버 위험 0** (공개 엔드포인트 이미 가동)

### Phase 2 — 사용자별 로그인 UI (모델 B, 서버 UI 인증 변경)
- 서버: admin-web UI의 IP락 → 사용자 JWT 인증으로 전환
- 멀티테넌트 데이터 격리 확인/구현
- 클라이언트: 원격 UI 로드(사용자 로그인) — 여전히 번들 없음
- **서버 변경 동반** → 별도 기준서 + 승인

### Phase 3 — 통합 super-admin
- owner가 전체 테넌트/에이전트 조망, 사용자는 자기 것만

---

## 4-D. 인증 모델 (이중 구조 — 구현됨)

| 대상 | 인증 방식 | 적용 엔드포인트 |
|------|----------|----------------|
| 배포 사용자(end user) | **JWT** (`users/login` → 토큰) | `/users/me`, 사용자 기능 |
| 관리자(owner) | **HTTP Basic Auth** (`require_role`, `/api/proxy`가 자동 주입) | `/users/pending`, `/users/{id}/approve`, `/admin/licenses` 등 |

- 회원 승인 화면(`/admin/users`)은 기존 `admin/licenses`와 동일하게 `/api/proxy` 경유 → Basic Auth 자동 주입 → owner 콘솔에서 바로 동작.
- 프로덕션: `/orchestrator/api/v1/users/pending|approve` 는 nginx `/orchestrator/` catch-all IP 잠금(owner IP)으로 추가 보호. **단, `/users/signup`·`/users/login` 은 배포 사용자용으로 공개 예외 필요(Phase 2 nginx 작업).**

---

## 5. owner / client 흐름 (전환 후)

### owner (당신) — 변화 없음
```
1. config.owner_mode = true
2. 로컬 FastAPI(8401) 시작
3. 로컬 Next.js(3000) 시작
4. CDP Chrome 시작
5. local-agent → ws://localhost:8401
6. webview → localhost:3000
7. 라이선스 게이트 생략, 즉시 진입
```

### client (배포본) — 신규
```
1. config.owner_mode = false (기본값)
2. [생략] 로컬 FastAPI 시작 안 함
3. [생략] 로컬 Next.js 시작 안 함
4. CDP Chrome 시작
5. local-agent → wss://haehan-ai.kr/orchestrator
6. webview → https://haehan-ai.kr/orchestrator (원격 UI)
7. 라이선스/로그인 → 원격 서버 인증
8. 원격 서버가 작업 통제
```

---

## 6. 영향 분석

| 영역 | 영향 | 비고 |
|------|------|------|
| 보안 | ↑ 향상 | 인증·정책이 서버로 일원화, 클라이언트에 로직 노출 안 됨 |
| DB | 변화 없음 | 클라이언트는 DB 직접 접근 없음(원래도 없음) |
| API 응답 키 | 변화 없음 | 기존 엔드포인트 그대로 사용 |
| 산식/정책 | 변화 없음 | |
| owner 워크플로 | 변화 없음 | 로컬 전체 스택 그대로 |
| 레이어 | 위반 없음 | config(L10)/main(L10)/mainWindow(L9)/agent(L3) 각자 계층 내 변경 |

---

## 7. 드라이런 계획 (실제 수정 전 시뮬레이션)

1. config.js 모드별 URL 해석 — 예상 diff 표시 (실제 미수정)
2. main.js 분기 — 예상 diff 표시
3. client 모드로 앱을 **임시 환경변수**(`HAEHAN_OWNER=0` + 원격 URL)로 띄워 원격 UI 로드 가능 여부만 확인 (코드 미수정, 환경변수 주입 테스트)
4. 게이트 3종 예상 통과 여부 점검

---

## 8. 리스크 / 롤백

| 리스크 | 대응 |
|--------|------|
| 원격 UI가 basic-auth로 막힘 (선행조건 A) | 하이브리드로 후퇴: UI는 로컬 번들 유지, FastAPI만 원격 |
| 원격 WS 미작동 (선행조건 C) | 서버측 WS 라우팅 수정 선행 |
| owner 흐름 회귀 | owner 분기는 현행 코드 그대로 → 회귀 위험 최소 |
| 롤백 | 모드 분기는 `if`로 감싸므로, client 분기 제거 시 즉시 현행 복귀 |

---

## 9. 작업 순서 (승인 후)

1. **선행조건 A·B·C 검증** (원격 서버 상태 확인 — 코드 수정 없음)
2. 검증 통과 시 → config.js → main.js → mainWindow.js → agent.js 순차 수정 + 각 단계 검증
3. client 빌드 프로파일 분리 (package.json + build_with_gates.py)
4. client 설치본 빌드 → 다른 환경 가정 테스트
5. 게이트 3종 실행 → 커밋

---

## 결정 필요 사항

- 이 기준서대로 **선행조건 검증(9-1)**부터 진행할지?
- 또는 선행조건 중 일부(원격 서버 변경)는 사용자가 서버 접근 권한으로 직접 확인이 필요할 수 있음.
