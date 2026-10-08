# S1 라벨 정정 드라이런/결과 (2026-09-24)
방법: classify_path 에 LAYER_OVERRIDES 13건 추가(라벨만, 파일 이동·로직 변경 없음). layer_count.py 전/후 실측(동일 map.json).
결과: 관리기준 파일 189→111, 엣지 289→183 (-106). 보조(레지스트리) 61 불변.
정정 근거(실제 역할):
- ai_orchestrator/config.py L8→L1: 환경설정 헬퍼, 22개 파일이 층 무관 사용
- audit_logger.py, scripts/op_log.py, scripts/realtime_audit.py, scripts/cdp_db.py, local_agent/browser/audit_log.py, cdp_audit.py, logging_utils.py L7→L3: 파일명 'audit/op_log/db' 부분문자열로 L7 오분류, 실제는 저수준 로그/IO 래퍼(L3/L4가 호출)
- local_agent/task_protocol.py, safety_policy/secret_redaction.py, result_sanitizer.py, local_agent/desktop_config.py -> L1: DTO/리덕션/설정 헬퍼(L1 정의)
- local_agent/network_bypass.py L10→L3: 저수준 네트워크 IO
사용자 결정(미변경): scripts/google/workflows.py(L6, 11건 피참조: 워크플로 vs 공용 라이브러리), local_agent/web_reader.py, ai_orchestrator/agent_hub/registry/facade.py, external_work_registry.py, external_sites/provider_registry.py, gabia_browser_task.py, playwright_bootstrap/runner.py, common_tool_runtime.py, naver_blog_router.py, gonobi/db.py 등 — 역할 애매 또는 실제 역전(이동 필요, S2).
S2 메모: 남은 183엣지는 L3->L8 connectors가 platform 코드 import(ai_orchestrator/connectors/*), scripts/local_agent 러너(L4)->L8, verify_*.py 루트(L4) 등 실제 방향 역전 다수.
