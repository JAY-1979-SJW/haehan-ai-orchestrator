# Haehan AI 웹 서비스 설계서

작성일: 2026-05-19  
작성 기준: autowork.haehan-ai.kr 직접 접속 탐색 결과

---

## 1. 도메인 구조

| 도메인 | 역할 | 상태 |
|--------|------|------|
| `haehan-ai.kr` | 메인 (1.201.176.236) | DNS 연결됨 |
| `www.haehan-ai.kr` | 메인 리다이렉트 | DNS 연결됨 |
| `app.haehan-ai.kr` | 앱 서버 | DNS 연결됨 |
| `api.haehan-ai.kr` | REST API 서버 | /orchestrator/api/v1/ → 404 (nginx 미설정 추정) |
| `autowork.haehan-ai.kr` | **Admin 관리 대시보드 (Next.js)** | ✅ 정상 운영 중 |

---

## 2. autowork.haehan-ai.kr — 서비스 구조

### 네비게이션 (공통)

```
홈(/)  |  로컬 에이전트(/local-agents)  |  CAD(/cad)  |  파일 지도(/file-map)  |  브라우저 승인(/browser-approvals)
```

추가 진입 경로:
- `/ops` — 운영 대시보드
- `/external-tasks` — 외부 웹 업무 현황

---

## 3. 페이지별 상세

### / (홈 — 관리 대시보드)

**목적:** AI 오케스트레이터 전체 현황 한눈에 파악

**섹션:**
| 섹션 | 내용 |
|------|------|
| 시스템 현황 | 로컬 에이전트 3대 온라인, 태스크 7건 대기, 완료 24건, 승인 대기 2건 |
| 승인 대기 | APR-001 히웍스 공지 자동 게시, APR-002 G2B 투찰 참여 여부 |
| 실행 게이트 | FORBIDDEN_IMPORT:PASS / SECURITY_PATTERN:PASS / CIRCULAR_IMPORT:PASS / QUALITY_GATE:WARN |
| 작업 공정표 | 진행 중 7개 작업 항목 |
| 업무 창고 | EUM 22개, G2B 154개, 히웍스 8개, YouTube 5개 |
| 운영 메뉴 | 5개 주요 메뉴 바로가기 |

---

### /ops (운영 대시보드)

**목적:** 웹 작업·승인·에이전트·감사 통합 운영

**섹션:**
| 섹션 | 내용 |
|------|------|
| 안전 정책 | 서버 자동 로그인 금지, 제출/결제/서명 사용자 직접 승인 필수, 승인 토큰 30분 TTL |
| 운영 통계 | 전체 작업 12건, 승인 대기 2건, 실행 중 3건, 실패/경고 1건 |
| 승인 대기 | hiworks/developer_apply (high), naver/app_register (high) |
| 공종 관리 | 웹 업무 실행 엔진, 로컬 에이전트 연결, CAD/HWPX/Excel 연동 |
| 웹 업무 목록 | hiworks/developer_apply, naver/app_register, google/oauth_submit, naver/blog_write, google/gmail_read |
| 로컬 에이전트 | local-agent-01 온라인, desktop-app-01 대기 중 |
| 연동 현황 | Naver 검색 연결됨, Naver 로컬 미연결, Google OAuth 미연결, Telegram 연결됨 |
| 감사 이벤트 | 최근 4건 로그 |

**확인된 API 경로:**
```
/api/v1/external/naver/*
```

---

### /local-agents (로컬 에이전트 관리)

**목적:** 로컬 PC 에이전트 연결 상태 및 작업 관리

**섹션:**
| 섹션 | 내용 |
|------|------|
| 에이전트 현황 | 전체/대기/작업중/오프라인 카운터, 자동 새로고침 |
| 에이전트 목록 | Agent ID, Host, OS, Version, 상태, 활성작업, 현재작업, 최근확인, Actions |
| 작업 목록 | 필터(전체/대기승인/실행중/완료/실패/취소), Task ID·Action·Status·Risk·생성일 |
| 데스크톱 등록 | 등록코드 발급 (평문 1회 표시), code_id·label·status·allowed_actions·만료일 |

**현재 상태:** 데이터 로딩 중 (서버 연결 필요)

---

### /browser-approvals (브라우저 승인)

**목적:** 브라우저 자동화 액션 승인 워크플로우 관리

**핵심 보안 정책:**
- Approval ID와 URL Hash는 공개 정보
- `safe_to_execute` 파라미터는 승인 여부와 무관하게 항상 `false` 유지 → 무단 실행 방지
- 실제 실행은 별도 승인 게이트 통과 필요

**현재 상태:** API에서 승인 요청 로딩 중

---

### /file-map (AI 파일 지도)

**목적:** 로컬 파일 지도 스캔 및 정리 계획

**기능:**
- 파일맵 리포트 생성
- 정리 계획 테이블
- 정리 미리보기
- 실행 / 승인 요청 / 실행 패키지
- 사전 점검 및 실행

**현재 상태:** 데이터 로딩 중

---

### /cad (AI CAD 워크스페이스)

**목적:** AutoCAD 자연어 제어 인터페이스

**기능:**
| 기능 | 설명 |
|------|------|
| 에이전트 현황 | 온라인/실행중/완료/실패 카운터, 10초 자동 새로고침 |
| 빠른 액션 9개 | AutoCAD 감지, 도면 파일 조회, 레이어 관리, 요소 통계, 텍스트 추출, 블록 참조, 치수 조회, 선/원/호 조회, 전체 데이터 수집 |
| AI CAD 어시스턴트 | 자연어로 도면 데이터 질의 (에이전트 선택 후 자유 질문) |

---

### /external-tasks (외부 웹 업무 현황)

**목적:** 외부 서비스(Naver, Google) 연동 상태 및 실행 가능 여부 분류

**서비스별 분류:**

| 서비스 | 작업 | 실행 위치 | 상태 |
|--------|------|-----------|------|
| Naver | 블로그/쇼핑 검색 (읽기) | 서버 | 완전 조회 가능 |
| Naver | 블로그 게시, 카페 게시 (쓰기) | 로컬 에이전트 필요 | 에이전트 대기 |
| Naver | 메일 발송 | 사용자 직접 | 차단 |
| Naver | 앱 등록 | 승인 필요 | 승인 대기 |
| Google | Gmail, Calendar, Drive | OAuth/API 설정 필요 | 미연결 |
| Google | 브라우저 로그인 자동화 | — | 차단 |

**보안 원칙:**  
이 페이지는 실제 외부 API 호출·게시·메일·파일 수정을 수행하지 않음.  
실행 가능 항목도 승인 게이트 통과 필수.

---

## 4. 아키텍처 추정 구조

```
클라이언트 (브라우저 / 데스크 앱)
        │
        ▼
nginx (haehan-webdb — 1.201.177.67)
        │
        ├── autowork.haehan-ai.kr  →  Next.js (admin-web, 포트 3000)
        │       ├── /                  홈 대시보드
        │       ├── /ops               운영 현황
        │       ├── /local-agents      에이전트 관리
        │       ├── /browser-approvals 브라우저 승인
        │       ├── /file-map          파일 지도
        │       ├── /cad               CAD 워크스페이스
        │       └── /external-tasks    외부 업무 현황
        │
        └── api.haehan-ai.kr       →  FastAPI (haehan-mcp, 포트 8000) — 미설정
                └── /orchestrator/api/v1/   REST + WebSocket
                        └── /ws/desktop     데스크 앱 Push WS
```

---

## 5. 데스크 앱 ↔ 웹 연결 현황

| 연결 | 경로 | 상태 |
|------|------|------|
| 데스크 앱 → admin-web | iframe (localhost:3000) | ⚠️ 로컬 실행 시에만 가능 |
| 데스크 앱 → admin-web (원격) | iframe (autowork.haehan-ai.kr) | 변경 필요 |
| 데스크 앱 → API WebSocket | wss://api.haehan-ai.kr/ws/desktop | ❌ nginx 미설정 |
| admin-web → API | 내부 API 호출 | ✅ 서버 내부 통신 (정상) |

### 데스크 앱 IframePanel 수정 필요

현재 `App.tsx`:
```typescript
const ADMIN_BASE = 'http://localhost:3000'  // ← 로컬 전용
```

변경 목표:
```typescript
const ADMIN_BASE = 'https://autowork.haehan-ai.kr'  // ← 원격 도메인
```

---

## 6. 미완료 / 보류 항목

| 항목 | 내용 | 우선순위 |
|------|------|----------|
| API WebSocket | `wss://api.haehan-ai.kr/ws/desktop` nginx 설정 미완 | 높음 |
| 데스크 앱 ADMIN_BASE | localhost:3000 → autowork.haehan-ai.kr 변경 필요 | 높음 |
| api.haehan-ai.kr | /orchestrator/api/v1/ → 404 (nginx 라우팅 추가 필요) | 높음 |
| 로컬 에이전트 연결 | /local-agents 데이터 비어있음 (서버 연결 대기) | 중간 |
| Google OAuth | Gmail·Calendar·Drive 미연결 | 중간 |
| Naver 로컬 | browser_session 미연결 | 중간 |

---

## 7. 운영 보안 정책 (웹에서 확인된 내용)

1. 서버에서 금융/정부 사이트 자동 로그인 금지
2. 제출·결제·전자서명은 사용자 직접 승인 필수
3. 인증정보(secret/token/password) API 응답에서 제외
4. 승인 토큰 30분 TTL — 만료 후 자동 거부
5. `safe_to_execute` 항상 false — 승인과 무관하게 실행 차단
6. 실행 가능 항목도 승인 게이트 필수 통과
