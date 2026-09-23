# Stage 11-UI-8D legacy docs cleanup report

## 1. 목적

Stage 11-UI-8C에서 WARN으로 분류된 항목 중 **문서 혼선 요소만** 최소 정리한다.
운영 메뉴·버튼은 이미 admin-web `/local-agents`로 연결되어 있으므로, 코드·테스트·서버 반영은 수행하지 않는다.

## 2. 수정 파일

| 파일 | 수정 목적 | 판정 |
|---|---|---|
| `admin-web/README.md` | `### legacy route` 섹션 표현 명확화 (운영 주 진입점 ≠ legacy) | 정리 완료 |
| `docs/ops/admin_web_ops_baseline.md` | legacy URL curl 예시 목적을 "deprecated fallback smoke 전용"으로 명시 | 정리 완료 |
| `docs/reports/stage11_ui8d_legacy_docs_cleanup_report.md` | 본 보고서 신규 작성 | 신규 |

## 3. 정리 내용

| 항목 | 기존 문제 | 정리 방향 | 판정 |
|---|---|---|---|
| README `### legacy route` | "기존 FastAPI admin 화면은 ... 경로로 유지된다" 표현이 운영자에게 정상 진입점으로 오해될 여지 | 제목을 `### legacy route (deprecated fallback)`로 변경. 운영 기준 화면이 admin-web임을 명시하고, legacy는 비상 확인용 fallback이며 신규 기능은 admin-web에만 추가됨을 표기 | OK |
| ops 문서 legacy curl 예시 | curl 예시 목적이 불명확 — 운영 주 검증인지 fallback 확인인지 판단 불가 | 주석으로 "deprecated fallback smoke 전용", "운영 주 검증은 admin-web smoke가 담당", "POST는 포함하지 않음" 명시 | OK |

수정 전후 모두:
- legacy route 자체는 보존
- 코드 예시·실제 API 경로·신규 기능 설명은 변경하지 않음
- 삭제 일정을 단정하지 않고 fallback 유지로 표현

## 4. 수정하지 않은 항목

| 항목 | 사유 |
|---|---|
| `ai_orchestrator/tests/test_admin_ui_capture_screenshot.py` | legacy route 직접 호출 테스트는 fallback route가 deprecated banner 문구·기존 보호 장치(권한·승인 게이트)를 유지하는지 확인하는 smoke 목적의 테스트로 볼 수 있음. 현 단계에서는 테스트 삭제/수정 대상 아님 |
| `ai_orchestrator/routers/admin_ui_router.py` | legacy route 본체 — 이번 단계는 코드 수정 금지 원칙에 따라 손대지 않음. deprecated banner는 이미 Stage 11-UI-7B에서 적용됨 |
| `admin-web/README.md`의 다른 legacy 참조 (line 260, 399, 494, 646~673) | 이미 `deprecated fallback`으로 충분히 명시되어 있어 추가 정리 불필요 |
| `docs/ops/admin_web_ops_baseline.md`의 다른 legacy 참조 (line 309~326 등) | 이미 `deprecated fallback 상태`로 명확히 분류되어 있음 |

## 5. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- POST 실행: 없음
- legacy 삭제: 없음
- secret 출력: 없음

## 6. 다음 단계 제안

**판정: PASS**

8C에서 지적된 두 가지 문서 혼선 요소(README legacy route 섹션 표현, ops 문서 legacy curl 예시 목적)가 모두 정리되었다.
운영 메뉴·버튼은 이미 admin-web으로 연결되어 있고, legacy route는 deprecated fallback임이 문서·banner·테스트 모두에서 일관되게 표현된다.
서버 반영은 불필요하다 (문서 변경만 수행).
