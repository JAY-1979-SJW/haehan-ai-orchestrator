# 레지스트리 기준 위반 61엣지 분류 (2026-09-24, 읽기 전용, 미커밋)
재현: layer_count.py secondary = 파일 40 / 엣지 61 (map.json import_edges, 층=레지스트리, 방향=allowed_deps).
분류: A 선언층 오류 53 / B 허용방향 누락 2 / C 실제 역전 6 / D 예외 0 (eum->hiworks는 층 위반 아님, 도메인 금지 게이트 별건).

| 누가 -> 누구 | 선언층 | 엣지 | 분류 | 권장 수정 |
|---|---|---|---|---|
| site_registry -> eum/gabia/google/kakao/naver auth, smartstore live_probe, login_detector | L1->L5/L4 | 7 | A | site_registry 를 L5 로 선언(실체=사이트 레지스트리) |
| site_engine/action_planner -> execution_gate | L1->L2 | 1 | A | planner L2 |
| site_engine/validators -> workflow_runner | L1->L6 | 1 | C | validators 가 runner 를 부름: 의존 반전/공용부 분리 |
| local_agent_models -> local_agent_registry | L1->L4 | 1 | C | 모델이 registry 를 import: 타입 분리 |
| temp_oauth_revoke, yt_upload/step1_navigate -> 브라우저/cdp_helper | L2->L4 | 2 | A | 스크립트 L6 선언(temp_oauth 는 삭제 후보) |
| module_quality_gate -> runner | L2->L6 | 1 | A | gate 드라이버 L6 |
| _tmp_* 3개(->smartstore product) | L4->L5 | 5 | A | 임시 스크립트: L6 선언 또는 삭제 |
| hanafax send_kras_* 2, video 2, run_page_builder, local_agent.py, local_agent/router | L4->L5 | 7 | A | 실행 스크립트 L6 선언 |
| cafe_mixin -> cafe_mixin_article | L4->L5 | 1 | A | article 을 L4 로 |
| blog_mixin_write -> naver/blog writer,selectors | L4->L5 | 2 | C | 엔진이 사이트모듈 의존: 주입/이동 필요 |
| cdp_client -> gabia_login_watch | L4->L5 | 1 | C | 공용 엔진이 사이트 감시를 import: 반전 |
| local_agent.py, site_access, smoke 러너 3종 -> L6 모듈 | L4->L6 | 7 | A | 러너/스크립트 L6(smoke 는 L11) |
| minwon_submit, webmail_send -> approval_server | L4->L8 | 2 | A | 스크립트 L6 선언 |
| g2b 스크립트 4 (-> browser_tool g2b 어댑터/playwright_runner) | L5->L6 | 5 | A | g2b 스크립트 L6 |
| naver blog cli 3 -> connectors/naver_blog_router | L6->L8 | 3 | A | router 를 L6 로 재선언(라우트 0개) — 11개 목록 중 잔존분 |
| browser_approval_db/persistent_store -> browser_approval_verifier | L7->L2 | 2 | B | L7->L2(순수 검증) 허용 추가 검토(C 대안=타입 분리) |
| post_cache, popup_monitor -> cdp_helper/navigator/classifier/watcher | L7->L4 | 4 | A | popup_monitor L4, post_cache L6 |
| error_recovery, post_cache, schedule, bulk 2, research_search | L7->L5 | 7 | A | 업무 스크립트 L6 선언 |
| gonobi/db -> gonobi/classifier | L7->L5 | 1 | C | 저장소가 분류기를 호출: 분류 호출을 상위로 |

## 앞선 11개 파일 대조
- 레지스트리 기준에서도 위반 잔존: naver_blog_router 3엣지(L6->L8)만. gonobi/db 1엣지(L7->L5).
- 나머지(google/workflows, web_reader, local_agent_registry, external_work_registry, provider_registry, gabia_browser_task, playwright_bootstrap/runner*, common_tool_runtime)는 레지스트리에서 이미 하위/동층 선언되어 위반 목록에 없음(playwright_runner 는 L6 선언, 그 호출측 스크립트 L4 선언이 문제 -> 위 A).
- 라벨 A 로 경로 기준 -45 했던 것이 레지스트리 기준에선 이미 반영된 상태.

## 총계
| A | B | C | D | 합 |
|---|---|---|---|---|
| 53 | 2 | 6 | 0 | 61 |
라우트 영향: 전부 0(선언층은 메타, C 조치도 라우트 데코 파일 아님 -- 실제 이동 시 재확인).

## 수정 순서
1. A 53: registry 선언만 수정(파일 ~30개 선언 변경), 예상 61->8. 스크립트/_tmp 는 L6 일괄 선언 1커밋.
2. B 2: allowed_deps L7->L2 허용 여부 결정 후 반영(->6).
3. C 6: 개별 코드 수정(엔진->사이트 주입, 모델/검증기 분리, gonobi 호출 상향), 4건은 한 묶음 가능.
4. D: eum->hiworks 2건은 이 지표 밖; 도메인 예외 등록으로 별도 처리.
