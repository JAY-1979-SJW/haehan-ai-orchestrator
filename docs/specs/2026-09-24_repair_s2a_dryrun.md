# repair S2a 드라이런 (레지스트리 선언층 정정)
범위: A 선언층 오류만. 정본=configs/module_registry.json + overrides. 코드 변경 없음.
예상: layer_count 레지스트리 기준 61(map.json, 미추적 파일 포함) -> 34. 변경 선언 15건.

| 파일 | 전 -> 후 | 근거 |
|---|---|---|
| scripts/naver/cafe/cafe_mixin_article.py | L5 -> L4 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/g2b/discover_valid_public_notice_urls.py | L5 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/g2b/run_readonly_local_e2e.py | L5 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/sites/local_cli_router.py | L4 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| tools/smoke/run_playwright_smoke.py | L4 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| tools/smoke/run_universal_ai_real_site_smoke.py | L4 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/module_quality_gate.py | L2 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/naver/automation/error_recovery.py | L7 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/naver/blog/management/post_cache.py | L7 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/naver/smartstore/product/bulk.py | L7 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/popup_monitor.py | L7 -> L4 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/run_page_builder.py | L4 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/site_registry.py | L1 -> L5 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/temp_oauth_revoke.py | L2 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |
| scripts/yt_upload/step1_navigate.py | L2 -> L6 | 실행 스크립트/러너(업무흐름 조립) 또는 실체 확인 |

## 보류(선언 바꾸면 신규 위반 발생 -> 사용자 결정)
site_access.py, local_agent.py(L6 승격 시 L4/L5 임포터 다수가 역전), site_engine/action_planner.py(L1 validators가 임포트),
management/schedule.py, youtube/research_search.py, g2b/run_public_notice_readonly_live_suite.py(임포터 L5 라우터/shim 존재).
approval_server(L8) 호출 스크립트 2건, naver_blog_router(L8, APIRouter 실존) 3엣지: L6 선언해도 L6->L8 불허 -> 사용자 결정.
master 미추적 7개 파일(_tmp_*, hanafax send_kras_* 2, video 2)은 레지스트리에 없어 이번 범위 밖.
D(eum->hiworks): 예외 등록 위치 미확인 -> 아래 별도 확인.
