# 구조 정정 기준서 (진단+드라이런, 코드 미수정) — 2026-09-24

## 1. 실측 (data/code_map 산출물, 2026-09-24 기준)
- py 2128파일, 내부 import 6073. UNREACHED 2(scripts/_tmp_html_consts2.py, scripts/video/_cdp_tab.py).
- 층간 위반: layer_violations.json = 150파일/282엣지 (커밋 메시지의 "51"은 다른 집계 기준 — 사용자 확인 필요).
  유형: L2->L4 50, L5->L6 37, L1->L4 34, L4->L5 25, L4->L6 23, L2->L5 22, L1->L2 16, L7->L5 13.
- 거대 파일(>1500줄, 테스트 제외): local_agent/actions.py 1566, scripts/naver/blog/cli/blog_cad_draft_posts.py 1517, tools/repo_gates/codebase_layer_audit.py 1512.
- 중복 후보: duplicate_code_check 171건 (예: scripts/naver/blog/core/writer_pro.py vs blog/writer_pro.py, cafe/write/writer.py vs cafe/writer.py).
- 데코레이터 라우트 ai_orchestrator 내 112개 집계(전체 288은 미재측정, 기준값 유지 검증 필요).

## 2. 원인 분류
- A 라벨오류: scripts/cdp_client·credentials·login_detector·web_connector·realtime_audit (L2로 라벨, 실제 L4 커넥터) → 약 24엣지 / L1->L2 16(approval.py, server/*_policy.py) / local_agent_registry·site_registry 미해결 라벨.
- B 잘못된 위치: google/workflows.py(L5->L6 11), smartstore description_editor(L4->L5), ai_orchestrator/local_agent/security_program_detector(L4->L6).
- C 역방향: naver_blog_router.py(L6->L8), local_agent/browser/mixins/*(L1->L4), admin-web route.ts -> scripts/cdp_client.py(L9->L4).
- D 거대·혼합: local_agent/actions.py, blog_cad_draft_posts.py, cdp_popup_manager.py, general_product.py.

## 3. 핵심 문제 Top10
1 L2 라벨 오류 커넥터군(scripts/entry/cdp_cli.py 외 4, L2->L4 50엣지)
2 scripts/google/workflows.py L5->L6 11건
3 ai_orchestrator/connectors/naver_blog_router.py L6->L8 3건(라우터를 서비스가 import)
4 L1->L4 34: local_agent/browser/mixins/{calendar,mail}_mixin.py
5 L1->L2 16: approval.py, server/execution_location_guard.py, server_egress_policy.py
6 local_agent/actions.py 1566줄 단일 파일
7 블로그/카페 writer 이중 경로(중복 171건 중 대표)
8 security_program_detector L4->L6
9 smartstore description_editor L4->L5
10 admin-web route.ts가 python 모듈 참조(경로참조 오탐 가능성 — 확인 필요)
(파일:줄 근거는 layer_violations.json 엣지 목록에서 특정; 줄번호는 S0에서 확정)

## 4. 단계 계획 (모두 verify_change --head, 라우트 288 유지 확인 후 진행)
- S0 준비: 집계 기준(51 vs 282) 통일, 라벨 규칙 파일 확인. diff 0.
- S1 라벨 정정(A): classify 규칙/헤더 라벨만 수정. 예상 -90~110엣지, diff 소, 위험 낮음, 라우트 영향 없음.
- S2 위치 이동(B): 파일 이동+shim(re-export) 유지로 import 경로 보존. 예상 -40, diff 중, 위험 중.
- S3 역방향 제거(C): 인터페이스/콜백 주입으로 방향 뒤집기. 예상 -50, 위험 중~상(서버 라우터 접촉).
- S4 거대 파일 분할(D): 함수 그룹별 모듈 분리, 원본은 re-export. 위반 수 무변화, 위험 중.
- S5 중복 정리: 진짜 중복 확인 후 한쪽 shim화. 삭제는 백업 후(allow-delete).
- 드라이런 추정: 282 -> 약 60~100 (S1~S3), 잔여는 결정 항목. 검증: verify_change 7항목, layer_audit, skeleton_gate, pytest.

## 5. 사용자 결정 필요
1) "51"과 "282" 중 관리 기준 어느 것인가.
2) L2 라벨 커넥터군을 L4로 재라벨(권장) vs 코드를 L2 순수화.
3) 파일 이동 시 shim 유지 기간(영구/1회 후 제거).
4) 중복(writer_pro 등) 삭제 허용 범위.
5) 운영 배포 포함 여부, 병합은 merge_stage.py 경유 확인.
