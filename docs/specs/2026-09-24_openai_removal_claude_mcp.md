# OpenAI(GPT) 코드 완전 삭제 — AI 역할은 Claude Code(MCP)로 (2026-09-24)

## 결정 (사용자 지시 2026-09-24)
"클로드를 mcp로 연결해서 open ai 삭제해"
- 앱 안에서 GPT 를 부르는 모든 경로를 없앤다. 앱 런타임의 유료 AI API 호출 = 0.
- AI(판단·글쓰기·에이전트)는 **Claude Code 가 MCP 로 앱에 붙어서** 한다.
  앱은 도구·데이터만 제공: `ai_orchestrator/server/mcp_server.py`(`.mcp.json` 의 `haehan-orchestrator`) — 전용 도구 + `list_api_endpoints`/`call_api`(앱 API 전체).
- 앱 경계 원칙(`app_llm.py`/`tests/test_app_llm_boundary.py`: 앱 런타임에서 Anthropic 호출 금지)은 그대로 — Claude 는 앱 밖(MCP 클라이언트)에서만.

## 범위
| 구분 | 처리 |
|---|---|
| 채팅 API `/agent-ai/chat`·`/agent-ai/health`·`/agent-ai/task/{id}` (routers/agent_ai_proxy_router.py) | 삭제 — 채팅은 Claude Code 가 대체 |
| openai_proxy_caller.py, gpt_planner.py, scripts/browser_agent/{agent,free_agent}.py | 삭제 |
| openai_client.py | MOCK 경로가 있는 함수는 OpenAI 분기만 제거(호출자 유지), 순수 OpenAI 는 삭제 |
| app_llm.py | 제공자 상수를 "none(앱 런타임 AI 없음 — Claude Code/MCP)"로 정리, 경계 테스트 유지 |
| 도메인 GPT 작성기(gpt_writer, gpt_description_writer, review_reply, mail body_pipeline_v2, community/analyzer, grant_radar/report, naver automation ai_responder) | GPT 분기 삭제 → 템플릿/빌더/초안 없음으로. 파일 전체가 GPT 전용이면 삭제하고 호출처를 정리 |
| mcp_server.py `generate_description` | model=gpt 제거, builder 만. 설명에 "문구는 Claude 가 쓰고 render_description/save_template 사용" |
| local_agent/ OpenAI 채팅·키 저장(openai_chat_client, openai_key_store, server_proxy_chat_client, ai_chat_adapter) | 삭제(데스크톱 앱은 이미 삭제됨) |
| 위 대상 전용 테스트·감사 스크립트(audit_openai_*, audit_agent_ai_chat_*) | 삭제 |
| config.py OPENAI_* 설정, config_router 노출 | 제거 |

## 제외 (건드리지 않음)
- `tools/hooks/guard_openai_call.py` 훅, CLAUDE.md 승인제 규칙, `ai_orchestrator/openai_guard.py` — 재유입 방지 장치
- `apps/marketing-standalone/**` — 판매 준비 중인 별도 제품 + 미커밋 작업 중(사용자 결정 필요 시 별도)
- 미커밋 WIP 파일(.githooks/commit_checklist.py, scripts/ops/office/ai_check_a4.py[2026-10-08 삭제됨: 실행 불가 유료 OpenAI 호출 코드, docs/deleted_code_index.md] 등) — 커밋 후 별도 정리
- `.env` 의 키 값(파일은 손대지 않음)

## 절차 (검증 파이프라인)
태그 `pre-openai-removal` → 브랜치 `stage/openai-removal`(별도 worktree) → 구현(Sonnet) →
`verify_change --base master --head stage/openai-removal` → 별도 리뷰 → ff 병합 → `verified/openai-removal` 태그.
판정 예외: 라우트 수는 채팅 3개만큼 **줄어드는 것이 정상**(291 → 288 예상), 삭제된 테스트의 실패 감소는 정상.
삭제 파일은 docs/deleted_code_index.md 에 복원 명령과 함께 추가. 커밋 메시지 `[allow-delete]`.

## 롤백
`git revert` 또는 태그 `pre-openai-removal` 에서 파일 복원.

## 범위 확장 (2026-09-24 사용자 승인 "네") — Anthropic 유료 API 경로도 삭제, 앱 런타임 유료 AI 0
| 대상 | 처리 |
|---|---|
| ai_orchestrator/connectors/ai_reply_caller.py (카카오 스킬 webhook 이 키만 있으면 자동 호출) | 삭제 — kakao_skill_router 는 규칙 분류 + 카테고리별 고정 안내 문구만 |
| scripts/naver/smartstore/product/ai_description_writer.py (description_mode="claude") | API 호출 제거 — generate() 가 app_ai_disabled + 표준 프롬프트 반환, finalize() 로 Claude Code 작성 본문 마감 |
| scripts/naver/automation/integration/ai_responder.py (provider="anthropic" opt-in) | 제공자 분기 제거 — 항상 app_ai_disabled |
검증: tests/test_app_llm_boundary.py 전체 통과(기존 master 에서 실패하던 test_no_anthropic_calls_outside_boundary 포함), tests/test_kakao_webhooks.py 28 통과(master 동일).
