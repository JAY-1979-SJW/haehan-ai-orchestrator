# S2(위치 이동+shim) / S3(역방향 제거) 드라이런 계획 — 2026-09-24 (코드 미수정)

근거: data/code_map/map.json(edges), layer_violations.json. 라벨만 바꾸는 S1 대상(L2 라벨 커넥터군, L1->L2 approval 등)은 제외.
"영향 import"는 map.json 기준 해당 파일을 import하는 파일 수(테스트 포함). 라우트 영향은 데코레이터 라우트 경로 변경 여부.

## S2 이동안 (B: 잘못된 위치)
| # | 파일 | 위반 | 이동/분리안 | shim | 영향 import(테스트) | 라우트 | 예상 -엣지 |
|---|---|---|---|---|---|---|---|
| 1 | scripts/google/workflows.py (L6 조율이 L5 하위모듈에서 역참조) | L5->L6 11 | workflows가 import되는 것이 문제: 하위모듈이 workflows의 공용 상수/함수를 쓰므로 공용부를 scripts/google/_shared.py(L5)로 추출, workflows는 이를 import | workflows에 re-export 유지 | 17(1) | 없음 | -11 |
| 2 | scripts/naver/smartstore/product/description_editor.py | L4->L5 (+_tmp_* 3건) | 사이트 종속 코드를 L5 폴더 유지, L4 쪽 호출자(general_product 등)를 L5로 재라벨 또는 _tmp_* 스크립트 정리(삭제는 allow-delete) | 불필요(경로 유지) | 6(0) | 없음 | -5 |
| 3 | local_agent/runtime/security_program_detector.py | L4->L6 (auto_resume, install_discovery 등 5) | detector를 L6로 재분류(서비스 성격) 또는 순수 판정부만 L2로 분리 | 분리 시 필요 | 4(1) | 없음 | -5 |
| 4 | core/agent_runtime/runtime/result_sanitizer.py 및 safe_write/universal_safe_result | L2/L4->L6 약 9 | sanitizer류는 정책=L2로 재라벨(위치 유지)이 최선. 이동 불요 | 불필요 | 7(2) | 없음 | -9 (라벨성, S1로 이관 권장) |
| 5 | ai_orchestrator/browser_tool/g2b_public_notice_workflow.py | L4->L6, L2->L6 | workflow(L6)를 dryrun_adapter/execution_gate가 import → 어댑터가 쓰는 부분(타입/상수)을 workflow에서 g2b_public_notice_models.py로 추출 | workflow에 re-export | 5(3) | 없음 | -3 |
| 6 | scripts/hanafax/batch.py, hiworks/{mail_batch,workflows}.py, mk_catalog/pipeline.py, naver/cafe/{pipeline,list_background_runner}.py (router L5가 L6 import) | L5->L6 약 10 | 라우터->서비스 방향은 정상이므로 파일을 L6 라벨로 정정(이동 불요). 실제 위반은 라벨 | 불필요 | 각 1~3 | 없음 | -10 (라벨성, S1 이관) |
| 7 | apps/marketing-standalone connectors/core (blog_router가 core/* import) | L5->L6 9 | 독립 앱=규칙 제외 대상으로 이미 분리 여부 확인 후 제외 | 불필요 | 2~3 | 없음 | -9 (제외규칙, S1) |
| 8 | scripts/local_agent/run_* 스모크(L4->L6) | L4->L6 약 10 | 스모크는 L11(tests/smoke) 성격: scripts/local_agent/smoke/ 로 이동 | 불필요(진입점 CLI만, 참조 확인) | 0~1 | 없음 | -10 |
| 9 | scripts/form/orchestrator.py, site_engine/workflow_runner.py | L4->L6, L1->L6 | orchestrator를 L6로 재라벨 | 불필요 | 3 | 없음 | -4 |

S2 합계: 실제 파일 이동/분리 필요는 #1,#3,#5,#8 (4건, shim 3건). 나머지 #2,#4,#6,#7,#9는 재라벨성이라 S1로 이관하면 S2 위험 감소.
예상: 순수 이동 효과 -30~35, 재라벨 이관분 약 -35~40 (기준서 추정 -40과 일치).

## S3 역방향 제거 (C)
| # | 위치 | 위반 | 방안 | shim | 영향 import(테스트) | 라우트 | 예상 -엣지 |
|---|---|---|---|---|---|---|---|
| 1 | scripts/naver/blog/cli/{apply_cta_to_batches,publish_ep_batch,publish_ep_batch_gov2}.py -> ai_orchestrator/connectors/naver_blog_router.py | L6->L8 3 | 라우터가 가진 함수(resolve_topic_image, 발행 헬퍼)를 scripts/naver/blog/core/(L5)로 추출, 라우터·CLI 둘 다 그것을 import | 라우터에 re-export | 8(3) | 함수 이동만, 경로 불변 | -3 (+중복 2건 해소) |
| 2 | local_agent/browser/mixins/{calendar,mail,blog,cafe}_mixin*.py, bootstrap.py, secure_login | L1->L4/L5/L7/L8 약 34 | 실제로는 L1 라벨 오류(mixin은 L4 커넥터). 라벨 정정 우선(S1). 잔여 approval_server(L8)/cdp_session_manager(L7) 참조는 콜백 주입 | 불필요 | 4씩(0) | 없음 | -30 (대부분 라벨성) / 실제 역방향 -4 |
| 3 | scripts/local_agent/{webmail_send,minwon_submit}.py, scripts/browser_agent/free_agent.py -> ai_orchestrator/*_router | L4->L8 약 5 | 라우터 경유 대신 서비스 함수로 호출 (라우터의 로직을 service로 추출) | 라우터 re-export | 1~4(1) | 로직 추출, 경로 불변 | -5 |
| 4 | ai_orchestrator/web_task_approval_service.py -> web_task_router.py; ops_router.py를 domain/models·model_adapters가 import; app_actions->server.py; local_agent_router_schemas->local_agent_router | L2/L1/L6->L8 약 6 | 스키마/모델을 라우터 파일에서 별도 schemas 모듈로 이동, 라우터는 import | 라우터 re-export | 확인 필요 | 서버 라우터 접촉: 등록 라우트 288 유지 검증 필수 | -6 |
| 5 | scripts/module_quality_gate_modules.py -> server/router 다수, agent/action_registry.py 등 | L2->L8/L10 약 10 | 게이트가 문자열 경로 참조인지 실 import인지 확인(경로참조 오탐 가능) | - | - | - | -10 (오탐이면 지도 규칙으로) |
| 6 | admin-web route.ts -> scripts/cdp_client.py (L9->L4) | 1 | 경로 문자열 참조 오탐 가능. 실호출이면 서버 API 경유로 변경 | - | - | 프론트 API 접촉, 사용자 확인 | -1 |
| 7 | *_router.py 5개(google/smartstore/youtube_router가 하위 router.py import) | L5->L8 3 | 래퍼 파일: shim 성격, 라벨 L8 정정 | - | - | 없음 | -3 (라벨성) |

S3 합계: 실 역방향 제거 약 -20~25, 라벨/오탐성 약 -45 (S1 이관 권장). 기준서 추정 -50과 유사하나 대부분이 재라벨.

## 순서/게이트
S1 이관분 먼저 -> S3 #1,#3(저위험) -> S2 #1,#5 -> S3 #4(라우트 288 검증) -> S2 #3,#8.
매 단계 verify_change --head, layer_audit, skeleton_gate, pytest(영향 테스트).
