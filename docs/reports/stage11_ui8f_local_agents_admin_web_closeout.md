# Stage 11-UI-8F local-agents admin-web closeout

## 1. 마감 범위

- Stage 11-UI-7E: legacy FastAPI admin deprecated banner 적용 및 서버 반영 (`7b1f28d`)
- Stage 11-UI-8A: admin-web `/local-agents` ↔ legacy FastAPI admin 기능 정합성 감사 보고서 (`44bcfb6`)
- Stage 11-UI-8B: 8A 보고서 커밋 origin push (`44bcfb6` → origin 반영)
- Stage 11-UI-8C: legacy 진입점/링크 의존성 감사 보고서 (`94ef4c1`)
- Stage 11-UI-8D: 문서 혼선 최소 정리 — README legacy route 섹션, ops 문서 curl 예시 목적 명확화 (`8033938`)

---

## 2. 최종 운영 기준

| 항목 | 최종 기준 | 판정 |
|---|---|---|
| 운영 화면 | admin-web `/orchestrator/admin-web/local-agents` | PASS |
| legacy FastAPI 화면 | `/orchestrator/api/v1/admin/local-agents` — deprecated fallback | PASS |
| 신규 기능 추가 위치 | admin-web only | PASS |
| legacy 삭제 여부 | 삭제하지 않음 — 별도 Stage 판단 | PASS |
| 서버 반영 필요 여부 | 8D 이후 불필요 (문서 변경만) | PASS |
| 운영 메뉴·버튼 연결 | 모두 admin-web `/local-agents`로 연결 | PASS |

---

## 3. 커밋 요약

| 단계 | 커밋 | 내용 | 서버 반영 필요 |
|---|---|---|---|
| 11-UI-7E | `7b1f28d` | legacy deprecated banner 적용 (`admin_ui_router.py` + `README` + 테스트 + ops 문서) | 완료 (서버 반영됨) |
| 11-UI-8A | `44bcfb6` | admin-web local-agents parity 감사 보고서 | 불필요 (문서) |
| 11-UI-8B | — | 8A 커밋 push만 수행 (별도 커밋 없음) | — |
| 11-UI-8C | `94ef4c1` | legacy 진입점 의존성 감사 보고서 | 불필요 (문서) |
| 11-UI-8D | `8033938` | README legacy route 섹션 + ops 문서 curl 목적 명확화 + 정리 보고서 | 불필요 (문서) |

---

## 4. 검증 요약

- legacy route smoke: 8D까지 ops 문서 기준으로 `GET /orchestrator/api/v1/admin/local-agents` → 200 확인 (deprecated fallback smoke 전용, POST 미포함)
- admin-web `/local-agents` smoke: 운영 주 검증 경로 — `GET /orchestrator/admin-web/local-agents` → 200
- Local Agent API: `GET /api/v1/local-agents`, `GET /api/v1/local-agents/{id}/tasks`, `POST /api/v1/local-agents/{id}/capture-screenshot`, `POST /api/v1/local-agents/{id}/tasks/{id}/cancel` — admin-web에서 모두 참조 확인 (8A 보고서)
- POST 미수행: 8A~8D 전 단계에서 POST 실행 없음
- secret 노출 없음: 전 단계 준수
- 금지 명령 미사용: ssh, docker, push --force, rebase, merge commit 없음

---

## 5. 남은 정책

- legacy route(`/orchestrator/api/v1/admin/local-agents`)는 admin-web 장애 시 fallback smoke 대상으로 유지
- 신규 UI/기능은 admin-web에만 추가
- FastAPI HTML 화면(`admin_ui_router.py`) 기능 확장 중단
- 관리자 UI는 admin-web 기준 Next.js/Tailwind CSS로 통일
- legacy route 삭제 판단은 별도 Stage에서 결정

---

## 6. 다음 큰 단계 제안

| 우선순위 | 단계 | 내용 |
|---|---|---|
| 1 | Stage 11-UI-9 | admin-web 전체 메뉴/레이아웃 정리 — 현재 `/local-agents` 외 화면 구성 보완 |
| 2 | Stage 12 | local-agent 실제 제어 기능 안정화 — WebSocket 연결 상태, 태스크 생명주기 검증 |
| 3 | Stage 13 | 승인/권한/감사로그 운영 통제 고도화 — Telegram 승인 게이트 + 역할별 접근 제어 강화 |

권장 순서: Stage 11-UI-9 → Stage 12 → Stage 13

---

## 7. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- rebuild: 없음
- POST 실행: 없음
- legacy 삭제: 없음
- secret 출력: 없음

---

## 8. 최종 판정

**PASS**

admin-web `/local-agents`가 운영 기준 화면으로 확립되었다.
legacy FastAPI admin은 deprecated fallback으로 명확히 분류·문서화되었고,
운영 메뉴·버튼·API 연동은 모두 admin-web 기준으로 정렬되어 있다.
8D 이후 추가 서버 반영은 불필요하다.
