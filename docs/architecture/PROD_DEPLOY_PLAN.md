# 기준서 — 운영 서버(haehan-ai.kr) 반영: 회원가입·승인 공개

Status: DRAFT (승인 대기 — 실행 전)
작성일: 2026-06-02
작성 근거: 운영 서버 SSH 직접 조사 (읽기 전용) + git dry-run
관련: `docs/architecture/THIN_CLIENT_PLAN.md`, `docs/deploy_troubleshooting.md`

> ⚠️ 이 문서는 **실서비스(haehan-ai.kr)** 변경 계획이다. 어떤 단계도 사용자 명시 승인 전 실행하지 않는다.

---

## 1. 목적

배포 사용자가 **회원가입 → (owner) 승인 → 로그인 사용**을 실제 서비스에서 할 수 있게 한다.
이를 위해 (a) 앱 코드 배포, (b) UI 재빌드, (c) nginx 공개 예외 추가가 필요.

---

## 2. 운영 서버 현재 상태 (실측, 2026-06-02)

### 2-1. 서버/컨테이너
- haehan-ai.kr = **1.201.176.236 (haehan-app)**, 리버스 프록시 = `nginx` 컨테이너
- `haehan-ai-orchestrator-api` (FastAPI, 8400, healthy)
- `haehan-ai-orchestrator-admin-web` (Next.js UI, 3000)
- 코드 repo: `/home/ubuntu/apps/haehan-ai-orchestrator`
- 배포 데몬: `ai-orchestrator-deploy-trigger.service` (`scripts/ops/deploy_trigger_daemon.py`)

### 2-2. ⚠️ 배포 파이프라인이 이미 멈춰 있음 (기존 문제)
| 위치 | 커밋 |
|------|------|
| 로컬 master | `ebfa86a` (내 작업 포함) |
| origin/master | `e671515` (로컬보다 5 뒤) |
| **운영 HEAD** | **`530a88b` — origin보다 23커밋 뒤** |

→ 운영 서버는 origin/master조차 23커밋 따라가지 못한 상태. (commit `e671515` 메시지: "push·webhook 정상인데 프로덕션 미반영" — **이미 알려진 미해결 문제**)
→ **내 코드를 push해도 운영에 자동 반영 안 됨.** 배포 파이프라인 복구가 선행 과제.

### 2-3. nginx 라우팅 (실측)
| 경로 | 접근 | 비고 |
|------|------|------|
| `/orchestrator/api/` (전체) | **owner IP 잠금** (`allow 220.79.246.190; deny all`) | signup/login 포함 전부 잠김 |
| `/orchestrator/api/v1/local-agents/register-with-code` | 공개 | 예외 |
| `/orchestrator/api/v1/local-agents/ws` | 공개 | 예외 |
| `/orchestrator/admin-web/` | owner IP 잠금 | 관리 UI |

→ **`/users/signup`·`/users/login` 이 owner IP에 잠겨 있어 배포 사용자 가입 불가.** 공개 예외 추가 필요.

### 2-4. ⚠️ 멀티테넌트 데이터 격리 미확인
현재 앱은 사실상 단일 사용자(owner) 데이터 모델. "여러 사용자가 각자 자기 데이터" (모델 B)는 사용자별 격리가 필요하나 **현 구현에 없음** → 별도 설계 과제(Phase 3). 이번 배포는 "가입·승인·로그인 게이트"까지만.

---

## 3. 변경 범위 (운영 반영에 필요한 4가지)

| # | 변경 | 위치 | 위험 |
|---|------|------|------|
| A | 앱 코드 push → origin | 로컬→GitHub | 낮음 (코드만) |
| B | **배포 파이프라인 복구** (운영이 origin pull+rebuild) | 운영 서버 | **높음** (기존 고장) |
| C | nginx 공개 예외 추가 (signup/login) | `nginx` 컨테이너 conf | **높음** (오설정 시 사이트 다운) |
| D | admin-web(UI) + api 컨테이너 재빌드 | 운영 서버 | 중간 |

---

## 4. 단계별 드라이런 (실제 미적용)

### 단계 A — push (드라이런 완료 ✅)
```
git push --dry-run origin master
→ e671515..ebfa86a  master -> master  (5커밋)
```
- pre-push AI 검수 훅 동작 확인 (claude_cli 미설치 → PASS)
- 실제 push는 승인 후.

### 단계 B — 배포 파이프라인 복구 (선행 진단 필요)
- `deploy_trigger_daemon.py` 동작/로그 점검 → 왜 23커밋 밀렸는지 원인 규명
- 안전 수동 대안: 운영에서 `git pull origin master` + `docker compose up -d --build` (단, CLAUDE.md "로컬 docker CLI 금지"는 **로컬 PC** 한정 — 운영 서버에서 직접 수행은 허용)
- 드라이런: `git fetch && git log HEAD..origin/master --oneline` 로 반영될 커밋 미리 확인

### 단계 C — nginx 공개 예외 (제안 diff)
`/orchestrator/api/` (owner 잠금) **앞에** 공개 예외 2줄 추가:
```nginx
# 배포 사용자 회원가입/로그인 — 공개 (JWT가 보안 layer)
location = /orchestrator/api/v1/users/signup {
    proxy_pass http://haehan-ai-orchestrator-api:8400/api/v1/users/signup;
    # (공통 proxy_set_header 블록)
}
location = /orchestrator/api/v1/users/login {
    proxy_pass http://haehan-ai-orchestrator-api:8400/api/v1/users/login;
    # (공통 proxy_set_header 블록)
}
```
- **`/users/pending`·`/users/{id}/approve` 는 예외 추가 안 함** → `/orchestrator/api/` catch-all의 owner IP 잠금 유지 (관리자 전용).
- 드라이런: 설정 파일 백업 → `docker exec nginx nginx -t` 로 문법 검증 → 통과 시에만 `nginx -s reload` (restart 아님).
- 롤백: 백업 conf 복원 + reload.

### 단계 D — 컨테이너 재빌드
- `orchestrator-api`: 승인 게이트 코드 반영
- `orchestrator-admin-web`: 가입/로그인/승인 화면 반영 (⚠️ 로컬에서 Next.js 빌드가 cold-cache로 오래 걸림 — 운영 빌드도 동일 주의)
- 드라이런: `docker compose build` 만(up 없이) 먼저 → 이미지 생성 성공 확인 후 `up -d`

---

## 5. 영향 / 안전장치

| 항목 | 영향/대응 |
|------|----------|
| 기존 운영 사용자 | `enabled=1` → 영향 없음. 단 운영 users.db 백업 후 진행 |
| 신규 가입자 | 가입 시 `enabled=0`(대기) — 의도된 변경 |
| 사이트 가용성 | nginx는 reload(무중단), restart 금지. config 백업 필수 |
| DB 스키마 | `enabled` 칸 이미 존재 → 변경 없음 |
| 비가역성 | nginx/컨테이너 모두 롤백 가능. DB는 백업 선행 |

---

## 6. 권장 실행 순서 (승인 후, 단계별 검증)

1. **단계 B 진단 먼저** — 배포 파이프라인이 왜 23커밋 밀렸는지. (이게 안 풀리면 push해도 무의미)
2. push (A)
3. 운영 users.db 백업
4. 컨테이너 재빌드 (D) — build만 → up
5. nginx 공개 예외 (C) — 백업 → nginx -t → reload
6. 실제 가입→승인→로그인 E2E 검증 (외부 IP에서)

---

## 7. 미해결/별도 과제 (이번 범위 밖)

- 멀티테넌트 데이터 격리 (모델 B 본격화) — Phase 3
- 배포 클라이언트 exe 빌드 — Phase 1 (별도)
- 가입 이메일 알림 (현재 화면 안내문은 "이메일로 안내" 문구만 있고 실제 발송 없음)

---

## 결정 필요

- 가장 안전한 첫 단계는 **단계 B 진단(읽기 전용)** — 배포 파이프라인이 왜 멈췄는지 원인부터 규명.
- 운영 변경(C·D)은 사이트 영향이 있어, B 진단 결과 확인 후 각각 개별 승인받아 진행.
