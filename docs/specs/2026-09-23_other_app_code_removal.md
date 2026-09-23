# 타 앱 연결 코드 삭제 기록 (2026-09-23)

사용자 지시: "현재 AI 에이전트 관련사항만 남기고 타 앱과 연결된 거는 모두 찾아서 삭제". 선택 범위 4개 + CAD 잔재.

## 삭제

| 범주 | 대상 | 비고 |
|---|---|---|
| Excel·한컴 PC앱 | `agent/excel/**`, `agent/hancom/**`, `agent/connectors/{excel_com,excel,hwp_com}_connector.py`, `agent/task_executor.py`(Excel·CAD·HWP COM 실행기, 모듈 최상단 CAD import 로 이미 import 불가), `agent/local_agent.py`(삭제된 실행기 의존, 사용처 0), 관련 테스트 | `agent/app.py` 의 Excel 분기 124줄 제거 |
| PC 파일정리·인벤토리 | `agent/local_inventory/**`, `scripts/file-map/**`, `services/file_map_executor/**`(스키마 포함), admin-web `api/file-map`·`components/file-map`·`server/file-map`·`lib/file-map`·`lib/fileMap*.ts`, 관련 테스트 | `docker-compose.yml` file-map-executor 서비스·admin-web 의존 제거, `docker/file-map-executor.Dockerfile` 삭제 |
| admin-web (legacy) | `admin-web/src/app/(legacy)/**` 60 파일 + 그로 인해 고아가 된 lib 4·컴포넌트 2 | 메뉴(`lib/nav.ts`)는 이미 naver·assistant 만 링크 |
| CAD 잔재 | `agent/action_registry.py`·`policy.py` CAD 액션, `desktop/local_server.py`·`local_agent_service.py` CAD 브리지, `local_agent/actions.py` CAD 액션, `mcp_server/server.py` local CAD adapter 도구, CAD 테스트 | CAD 는 03.cad-program 으로 이전(f110f84a) |

## 스키마 영향

- `services/file_map_executor/schemas.py` 삭제 — 서비스 자체 삭제. 다른 서비스가 이 스키마를 import 하지 않음(코드맵 확인).
- 응답 변경: desktop 로컬 서버 preflight/health 에서 `optional_status.cad`·`health.cad_bridge`·`CAD_API_BRIDGE_NOT_READY` 제거. admin-web 에 해당 키 사용처 없음(grep 확인).

## 검증 (삭제 전 → 후)

| 항목 | 전 | 후 |
|---|---|---|
| pytest 수집 오류 | 12 | 7 (신규 0) |
| 수집 테스트 수 | 12,300 | 12,411 |
| LIVE 모듈 import 실패 | 43 | 36 (신규 0) |
| 서버 라우트 | 291 | 291 |
| admin-web tsc 오류 | 1 | 1 |

## 배포 주의

운영 서버에는 기존 `haehan-ai-orchestrator-file-map-executor` 컨테이너가 남는다. 다음 배포 시 compose 에서 빠졌으므로 수동 정리(`docker rm -f`) 또는 `--remove-orphans` 필요 — 운영 서버 작업이라 별도 승인.

## 2차 삭제 (사용자 지시 "타앱과 연결된거는 다 지워")

- `mcp_server/`(cad-backend 프록시 MCP), `desktop/`(구세대 데스크톱 앱·자체 SPA), `backend/compat/legacy_5050`(이행 호환 계층), `agent/` 중 `__init__`·`action_registry`·`models` 외 전부(PC앱 런타임·local_software_manager), `HaehanAI-Desktop.spec`·`HaehanAI-Agent.spec`.
- 이들 전용 테스트·감사/스모크 스크립트 105개 삭제, 혼합 파일 22개는 해당 부분만 제거. 모듈 게이트에서 `desktop_security_boundary`·`ui_residue_contract` 검사 제거(검사 대상 전부 삭제됨).
- 검증: pytest 수집 오류 7→7(신규 0), 수집 12,411→10,163(삭제된 전용 테스트분), LIVE import 실패 36→36(신규 0), 서버 라우트 291 동일.
- 남김: 5050 레거시 특성화 테스트(backend/compat 미의존, 통과), desktop 이름의 인증·버전 분리 게이트(삭제 패키지 미의존).
