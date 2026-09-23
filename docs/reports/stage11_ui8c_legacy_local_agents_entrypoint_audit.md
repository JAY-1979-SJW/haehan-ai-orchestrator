# Stage 11-UI-8C legacy local-agents entrypoint audit

## 1. 목적

admin-web `/local-agents`를 운영 기준 화면으로 전환하기 위한 legacy 진입점 의존성 감사.
legacy FastAPI admin(`/api/v1/admin/local-agents`)으로 들어가는 링크·문서·라우트 의존성을 분류한다.

---

## 2. 검색 결과 요약

| 검색어 | 주요 파일 | 판정 | 비고 |
|---|---|---|---|
| `/api/v1/admin/local-agents` | `admin-web/README.md`, `docs/ops/admin_web_ops_baseline.md`, `ai_orchestrator/tests/test_admin_ui_capture_screenshot.py`, `docs/reports/stage11_ui8a_admin_web_local_agents_gap_report.md` | KEEP / UNKNOWN | 문서·테스트·보고서 |
| `/orchestrator/admin-web/local-agents` | `ai_orchestrator/routers/admin_ui_router.py`, `admin-web/README.md`, `docs/ops/admin_web_ops_baseline.md` | KEEP | deprecated banner 내 admin-web 링크 안내 |
| `legacy 관리 화면` | `ai_orchestrator/routers/admin_ui_router.py`, `ai_orchestrator/tests/test_admin_ui_capture_screenshot.py` | KEEP | deprecated 안내 문구 |
| `fallback 용도` | `ai_orchestrator/routers/admin_ui_router.py`, `docs/ops/admin_web_ops_baseline.md` | KEEP | fallback 안내 |
| `신규 기능은 admin-web` | `ai_orchestrator/routers/admin_ui_router.py`, `admin-web/README.md`, `docs/ops/admin_web_ops_baseline.md` | KEEP | 운영 정책 안내 |
| `화면 캡처 사전 점검` | `ai_orchestrator/routers/admin_ui_router.py`, `ai_orchestrator/tests/`, `docs/local_agent_capture_policy.md` | KEEP | legacy UI 버튼 레이블 (기능 유지) |
| `실제 1회 화면 캡처 요청` | `ai_orchestrator/routers/admin_ui_router.py`, `ai_orchestrator/tests/`, `docs/local_agent_capture_policy.md` | KEEP | legacy UI 버튼 레이블 (기능 유지) |

---

## 3. KEEP

| 파일 | 위치 | 사유 |
|---|---|---|
| `ai_orchestrator/routers/admin_ui_router.py` | line 146 | `"이 화면은 legacy 관리 화면입니다."` — deprecated 안내 banner |
| `ai_orchestrator/routers/admin_ui_router.py` | line 154–155 | `"fallback 용도"`, `"신규 기능은 admin-web"` 안내 문구 |
| `ai_orchestrator/routers/admin_ui_router.py` | line 148–150 | `/orchestrator/admin-web/local-agents` 링크 포함 — 운영자가 admin-web으로 이동 가능하게 안내 |
| `ai_orchestrator/routers/admin_ui_router.py` | line 488, 496 | `화면 캡처 사전 점검`, `실제 1회 화면 캡처 요청` 버튼 레이블 — fallback 기능 유지 |
| `ai_orchestrator/tests/test_admin_ui_capture_screenshot.py` | line 476–496 | legacy banner 문구 존재 여부 테스트 — deprecated 정책 보장 |
| `admin-web/README.md` | line 646–673 | `## legacy FastAPI admin — deprecated fallback` 섹션 — 운영 정책 문서 |
| `docs/ops/admin_web_ops_baseline.md` | line 324–325 | `"legacy route는 admin-web 장애 시 fallback 용도로 유지"` — 운영 정책 문서 |
| `docs/local_agent_capture_policy.md` | line 37 | 버튼 레이블 정책 문서 |

---

## 4. MIGRATE_CANDIDATE

없음.

legacy URL(`/orchestrator/api/v1/admin/local-agents`)을 주 진입점으로 연결하는 메뉴·버튼·대시보드 코드는 발견되지 않았다.

- `admin-web/src/components/ui/PageShell.tsx`의 메뉴는 `/local-agents`(admin-web)로 연결
- `admin-web/src/app/page.tsx`의 링크도 `/local-agents`(admin-web)로 연결
- legacy URL은 문서·테스트·deprecated banner 참조에만 등장

---

## 5. REMOVE_CANDIDATE

| 파일 | 위치 | 사유 |
|---|---|---|
| `admin-web/README.md` | line 278–280 `### legacy route` 섹션 | "기존 FastAPI admin 화면은 ... 경로로 유지된다" — deprecated 전환 이후 혼선 가능. admin-web 정식 전환 완료 시점에 삭제 또는 deprecated 표기 강화 권장. 현 시점에서는 유지 가능 |

---

## 6. UNKNOWN

| 파일 | 위치 | 확인 필요 사유 |
|---|---|---|
| `docs/ops/admin_web_ops_baseline.md` | line 251, 353–364 | curl 예시에 `/orchestrator/api/v1/admin/local-agents` 직접 사용 — smoke test 목적인지, 여전히 운영자 매뉴얼로 활용되는지 정적 검색만으로 판단 불가 |
| `ai_orchestrator/tests/test_admin_ui_capture_screenshot.py` | line 85, 253 | `client.get("/api/v1/admin/local-agents")` — 테스트에서 legacy route 직접 호출. legacy 삭제 시 테스트 수정 필요 여부는 삭제 판단 단계에서 결정 |

---

## 7. 다음 단계 제안

**판정: WARN**

운영 UI(메뉴·버튼·대시보드)는 모두 admin-web `/local-agents`로 연결되어 있어 **주 진입점 의존성 없음**.
단, 아래 두 항목이 정리 대상 후보로 남아 있다.

1. `docs/ops/admin_web_ops_baseline.md`의 curl smoke test 예시에 legacy URL 사용 (UNKNOWN — 의도적 운영 확인 절차일 수 있음)
2. `admin-web/README.md`의 `### legacy route` 섹션 표현이 운영자에게 "여전히 정상 진입점"으로 오해될 여지 있음 (REMOVE_CANDIDATE)

운영 차단 요소는 없으므로 **WARN**. 다음 단계에서 문서 표현 정리 여부를 판단하면 된다.

---

## 8. 금지 작업 준수 확인

- 코드 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- git push: 없음
- POST 실행: 없음
- secret 출력: 없음
- legacy 삭제: 없음
