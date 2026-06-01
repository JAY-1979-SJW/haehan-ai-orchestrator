# 기준서 — 승인 사용자 UI 접근 (보안 강화 포함)

Status: DRAFT (승인 대기 — 실행 전)
작성일: 2026-06-02
근거: 운영 SSH 확인 + middleware.ts 코드 분석
관련: PROD_DEPLOY_PLAN.md, THIN_CLIENT_PLAN.md

> ⚠️ 운영 + **보안** 직결. UI를 공개로 여는 변경 → 인증 강화가 선행되어야 안전.

---

## 1. 문제 (현재 빈틈)

가입→승인→로그인 API는 공개됐으나, **화면(`admin-web`)은 owner IP에만 열림**.
→ 승인된 사용자가 로그인 토큰을 받아도 **화면 진입 불가** = "사용" 불가.

그러나 단순히 nginx IP 잠금만 풀면 **보안 구멍**:
- `middleware.ts:52-64` — JWT 쿠키 **존재만** 확인, **위조 검증 안 함**(TODO로 남음)
- → 아무나 가짜 쿠키로 보호 경로 진입 가능
- `middleware.ts:36` — 홈(`/`)은 공개
- 관리자 경로(`/admin` 등) role 검증은 클라이언트(PageShell)에만 의존

---

## 2. 목표

승인 사용자(유효 JWT)는 화면 사용 가능, 비로그인/위조는 로그인으로 차단.
관리자 작업(승인 등)은 계속 owner 전용(서버 Basic Auth + IP).

---

## 3. 변경 범위

### 3-1. 프론트 보안 강화 (선행, 로컬)
`admin-web/src/middleware.ts`:
- JWT **서명 검증** 추가 (`jose` — Edge Runtime 호환). 유효하지 않으면 로그인 리다이렉트.
- `JWT_SECRET` 을 admin-web 컨테이너 env로 주입 (api와 동일 시크릿).
- OWNER_MODE 우회는 유지(owner 로컬/콘솔).
- (선택) 관리자 경로는 JWT payload의 role 확인 — 단 role이 토큰에 없으면 서버 게이트로만.

의존성:
- `jose` 패키지 추가 (`admin-web/package.json`)
- `JWT_SECRET` 가 admin-web 빌드/런타임 env에 존재해야 함 → compose 환경 확인 필요

### 3-2. nginx 잠금 해제 (운영, 후행)
`/orchestrator/admin-web/` 및 `/orchestrator/admin-web/_next/static/` 의 IP allowlist 제거 → 공개.
- 보안 layer = 강화된 middleware(JWT 검증).
- 백업 → `nginx -t` → reload.

### 3-3. 서버 관리자 보호 (변경 없음 — 확인만)
`/users/pending`, `/users/{id}/approve`, `/admin/licenses` 등은 `/orchestrator/api/` IP 잠금 + Basic Auth 유지.

---

## 4. 단계별 + 드라이런

1. **로컬**: middleware JWT 검증 구현 + `jose` 추가 → 타입체크 + 로컬 테스트
   - 드라이런: 유효 토큰 통과 / 위조·만료 토큰 차단 / 비로그인 리다이렉트 단위 검증
2. **로컬**: admin-web 빌드 성공 확인 (JWT_SECRET env 주입 형태 결정)
3. push → 운영 배포 (api 불필요, admin-web 재빌드)
4. **운영**: nginx admin-web 잠금 해제 (백업→test→reload)
5. **검증**: 외부 IP에서 (a) 비로그인→로그인화면 (b) 승인 사용자 로그인→화면 사용 (c) 위조 쿠키→차단

---

## 5. 리스크 / 안전장치

| 리스크 | 대응 |
|--------|------|
| UI 공개 노출 | middleware JWT 서명 검증 선행(필수). 검증 전 nginx 해제 금지 |
| JWT_SECRET 누출 | env 주입만, 로그 출력 금지. api와 동일 시크릿 |
| 관리자 기능 노출 | 서버 require_role(Basic Auth)+IP 유지 — UI만 열고 관리 API는 안 엶 |
| 홈(/) 공개 | 현행 유지 가능(둘러보기). 민감 데이터는 보호 경로에만 |
| 롤백 | nginx 백업 복원 / middleware 이전 커밋 / admin-web 이전 이미지 |

---

## 6. ⚠️ 더 큰 미해결 (이 단계로도 안 풀림)

UI를 열어도 **데이터는 단일 테넌트**(owner 것). 승인 사용자가 "자기 데이터/자기 자동화"를 쓰려면
**멀티테넌트 격리(Phase 3)** 필요 — 사용자별 데이터 분리, 사용자별 local-agent, 사용자별 세션.
이 단계는 "승인 사용자가 화면에 안전하게 접근"까지.

---

## 7. 결정 필요

- 먼저 **3-1(로컬 미들웨어 보안 강화)** 부터 — 운영 무관, 안전. 완료·검증 후 운영 nginx 해제는 별도 승인.
- 또는 멀티테넌트(Phase 3)부터 설계할지 — UI 접근보다 데이터 격리가 더 본질일 수 있음.
