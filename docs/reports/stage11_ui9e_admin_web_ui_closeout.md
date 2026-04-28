# Stage 11-UI-9E admin-web UI closeout

## 1. 마감 범위

| 단계 | 커밋 | 내용 | 판정 |
|---|---|---|---|
| 11-UI-9A | 297f133 | admin-web layout audit (레이아웃 구조 감사, WARN 항목 식별) | WARN |
| 11-UI-9B | 47858f9 | sidebar/menu reference UI alignment (PageShell·nav.ts 정렬) | PASS |
| 11-UI-9C | 68fadfe | home dashboard cleanup (stale Stage 제거, 운영 대시보드 재구성) | PASS |
| 11-UI-9D | 68fadfe 서버 반영 | admin-web rebuild/up + smoke (home 200, local-agents 200 확인) | PASS |

## 2. 최종 운영 UI 기준

| 항목 | 기준 | 판정 |
|---|---|---|
| 운영 관리자 UI | admin-web | PASS |
| 홈 화면 | 운영 대시보드 기준 — 운영 카드·현재 운영 기준 테이블·다음 작업 방향 | PASS |
| local-agents 화면 | admin-web 운영 기준 | PASS |
| sidebar/menu | 지정 UI 참조 폴더 기준 (orange accent, active 상태, NAV_ITEMS) | PASS |
| legacy FastAPI admin | deprecated fallback — 운영 기준 테이블에 명시, 링크 없음 | PASS |

## 3. 참조 UI 기준

- 참조 폴더:
  `C:\Users\skyjw\OneDrive\03. PYTHON\31. construction-attendance`

- 참조 파일:
  - `components/admin/AdminSidebar.tsx`
  - `components/admin/AdminLayoutWrapper.tsx`
  - `components/admin/ui/PageShell.tsx`
  - `components/admin/ui/StatusBadge.tsx`
  - `components/admin/ui/KpiCard.tsx`
  - `app/globals.css`

## 4. 서버 반영 결과

| 항목 | 결과 |
|---|---|
| 운영 repo 경로 | `/home/ubuntu/apps/haehan-ai-orchestrator/` |
| 서버 HEAD | `68fadfe` |
| admin-web build | PASS (image sha `2814d923`) |
| admin-web up | PASS (`--no-deps --force-recreate admin-web`) |
| home route | 200 (컨테이너 직접 확인 `http://172.18.0.12:3000/`) |
| local-agents route | 200 |
| stale Stage 문구 | 제거 확인 (Stage 11-UI-1A, Stage 11-UI-2 없음) |
| POST 위험 액션 | 미수행 |
| secret 출력 | 없음 |

## 5. 운영 경로 기준선

다음 기준을 고정한다.

- compose 운영 경로는 `/home/ubuntu/apps/haehan-ai-orchestrator/`
- admin-web 반영은 이 경로에서만 수행
- `/home/ubuntu/apps/haehan-ai-orchestrator-api/` 는 compose 운영 경로가 아니므로 향후 pull/build 대상에서 제외
- 서버 작업 시 운영 compose 경로 외 git pull 금지

**주의 기록:**
Stage 11-UI-9D 중 `/home/ubuntu/apps/haehan-ai-orchestrator-api/` 에도 `git pull --ff-only`가 수행되었다.
해당 경로는 compose 운영과 무관하며 서비스에 영향 없음이 확인되었으나, 다음 작업부터는 운영 compose 경로 외 pull을 금지한다.

## 6. 남은 후속 단계

권장 다음 단계:

1. Stage 12 — local-agent 실제 제어 기능 안정화 (태스크 생성·취소·상태 폴링)
2. Stage 13 — 승인/권한/감사로그 운영 통제 고도화
3. Stage 14 — 실제 업무 자동화 연결

권장 순서: Stage 12 → Stage 13 → Stage 14

## 7. 금지 작업 준수 확인

- 코드 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- rebuild: 없음
- smoke 재실행: 없음
- legacy 삭제: 없음
- API 경로 변경: 없음
- secret 출력: 없음

## 8. 최종 판정

PASS
