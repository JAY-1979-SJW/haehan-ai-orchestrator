# 시험 격리 결함 수정 기준서 — `auth`·`local_agent_router` reload (2026-10-04, 승인 대기)

## 1. 문제
`ai_orchestrator/tests/` 의 여러 시험 fixture 가 시험마다 `importlib.reload(gates.auth)` 와 `reload(local_agent_router)` 를 한다.
reload 하면 `get_current_user` 가 새 함수 객체가 되지만, `local_agent_router` 가 포함하는 하위 라우터(등록·작업·브라우저 등)는 처음 import 된 옛 객체에 묶여 있다.
시험은 새 객체에 `dependency_overrides` 를 걸므로 **두 번째 시험부터 override 가 안 먹혀** 인증이 실제로 동작(401) → `POST /local-agents/register` 응답에 `agent_id` 가 없어 `KeyError: 'agent_id'`.
시험 한 개씩 단독 실행하면 통과하고 파일 전체·묶음 실행에서만 실패한다. 운영 코드는 정상이다.

영향: 영향 테스트 묶음에서 63건 실패(수정 없는 HEAD 에서도 동일). 편집 훅(`post_edit_fast_gate`)이 묶음 실패를 HEAD 단독 실행과 비교해 "새 실패"로 오판해 `local_agent/actions.py` 등 편집을 막는다.

## 2. 실측 (14개 reload 파일, 파일 전체 실행)
| 파일 | 결과(수정 전) | 처리 |
|---|---|---|
| test_web_task_templates / test_web_task_registry / test_sites_endpoints / test_local_agent / test_auth_enforcement / test_approval_execution_flow | 전부 통과(skip 포함) | **변경 없음**. 인증 활성 시험은 config·server 까지 의도적으로 reload 하며 이미 정상 |
| test_approval_public_id, test_local_agent_ws | 3건 / 38건 실패 → 이미 수정(미커밋)해 9건 / 60건 통과 | 완료 |
| test_registration_codes | 15건 실패 | 수정(동일 블록) |
| test_capture_screenshot_telegram | 2건 실패 | 수정(동일 블록) |
| test_capture_screenshot_request_api | 20건 실패 | 수정(동일 블록) |
| test_capture_screenshot_dry_run | 7건 실패 | 수정(동일 블록) |
| test_capture_screenshot_approval | 14건 실패 | 수정(동일 블록) |
| test_admin_ui_capture_screenshot | 5건 실패 | 수정(auth·lar reload 제거, `admin_ui_router` reload 는 환경변수 반영용이라 유지) |
| test_fetch_web_page / test_approval_read_api | 10건 / 17건 실패 | **범위 밖**. 원인이 다르다(`token_id` 가 None, 라우트 404) — 격리 결함이 아니라 별개 결함, 별도 조사 |

## 3. 변경
수정 대상 6개 파일(추가), fixture 의 아래 두 줄과 그 직전 import 만 제거(`importlib` 은 `admin_ui` 에서만 계속 사용):
```
import tools.gates.auth as _auth      # 제거
importlib.reload(_auth)                         # 제거
import ai_orchestrator.agent_hub.router.root as _lar   # 제거
importlib.reload(_lar)                          # 제거
```
이유 주석 3줄을 남긴다. 운영 코드·공통 conftest·훅은 건드리지 않는다. (공통 헬퍼는 불필요 — 필요한 파일은 이미 통과하고 필요 없는 파일은 줄 제거로 충분)

## 4. 불변·검증
- 운영 코드, API, DB, 정책 변경 없음. 시험 코드 6개 파일만.
- 검증: 6개 파일 각각 전체 실행 0건 실패, 린트 신규 오류 0, 영향 테스트 묶음 재실행 시 실패 목록이 줄기만 하고 늘지 않음, 훅 검사(`_check_python`) 재실행.
- 범위 밖 2개 파일(별개 결함)은 별도 보고.

## 후속 (2026-10-05): 낡은 시험 두 파일 정리 — 시험만 수정, 앱·정책 불변
- `test_capture_screenshot_dry_run.py` 3건 해소(13건 통과): 서버가 `running` 보고 없이 `delivered → completed` 를 거부하므로 시험이 `running` 을 먼저 보내게 했고, 액션 결과 키가 `screenshot_file` → `file_basename` 으로 바뀐 것을 반영(전체 경로 비노출 단언은 오히려 강화).
- `test_fetch_web_page.py` 10건: `POST /api/v1/tasks` 가 `POST_TASKS_DRY_RUN_ENABLED=True`(정책 잠금, 여러 시험이 True 를 단언)라 토큰을 발급하지 않는다. 플래그가 켜져 있을 때만 사유와 함께 skip, 꺼졌는데 토큰이 없으면 실패(`_approval_token`). 18건 통과·10건 skip. **플래그와 앱은 건드리지 않았다.** 플래그를 끄고 확인하니 승인 응답에 `executed` 키가 없어 8건이 추가로 실패한다 — 정책 결정 뒤 별도 정리 필요.
