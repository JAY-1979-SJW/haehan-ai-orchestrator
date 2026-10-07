# 사용자 결정 자료 (2026-09-24, master 5e591a24, 읽기 전용 측정)
근거: map.json import_edges + classify_path. "역전 in"=하위층 라벨 파일이 이 파일을 import한 건수(=위반 엣지). 전 11개 라우트 데코레이터 0개(라우트 영향 없음).

| 파일 | 실제 역할 | 층/근거 | 위반(누가->이걸) | A | B | 추천 |
|---|---|---|---|---|---|---|
| scripts/google/workflows.py | 구글 업무 aggregator(실체는 workflows_common 등 leaf 재수출) | L6 (workflows 이름) | L5 leaf 11건이 import | 라벨 L5 변경(1줄, -11, 위험 낮음) | 공용부 _shared.py 추출(파일 신설+shim, -11, 중) | A: 사실상 공용 라이브러리 |
| local_agent/web_reader.py | HTML 문자열 정적 분석(브라우저 조작 없음) | L10 (local_agent 경로) | L4 3건 | 라벨 L4(-3) | scripts/로 이동(중) | A |
| ai_orchestrator/agent_hub/registry/facade.py | 에이전트+작업큐 aggregator, 40곳이 사용 | L8 (registry/서버 경로) | L1 1, L7 3 | 라벨 L6(-4) | 이동은 40 import 영향(큼) | A(L7 3건은 감사스크립트라 라벨 L7 정리 병행) |
| external_work_registry.py | 외부 웹업무 분류 표(데이터/정책) | L8 | L1 1, L2 1, L7 1 | 라벨 L2(-3) | 이동 | A |
| external_sites/provider_registry.py | 외부사이트 공급자 정본 표(583줄) | L8 | L2 1, L7 2 | 라벨 L2(-3) | 이동 | A |
| gabia/gabia_browser_task.py | 가비아 작업 계약+상태머신 | L8 | L2 1, L7 3 | 라벨 L6(-4) | 이동 | A |
| local_agent/playwright_bootstrap.py | Playwright 설치 진단 | L8 | L4 러너 5 | 라벨 L4(-5) | scripts로 이동(shim, 중) | A |
| local_agent/playwright_runner.py | 사용자PC Playwright 조회 실행 | L8 | L4 4 | 라벨 L4(-4) | 동일 | A |
| local_agent/common_tool_runtime.py | 공통 도구 실행 계약 검증 | L8 | L5 2, L7 1, L4 1 | 라벨 L4(-4) | 이동 | A |
| connectors/naver_blog_router.py | 라우트 0개, 실은 블로그 발행/Unsplash 헬퍼 516줄(이름 때문에 L8) | L8 (_router 이름) | L5 CLI 3 | 라벨 L5(-3, 중복 2건은 남음) | 헬퍼를 scripts/naver/blog/core로 추출+re-export(-3, 중) | B(이름이 오해 유발; 저위험이면 A 먼저) |
| naver/blog/gonobi/db.py | gonobi sqlite 저장(자체 표기 L7) | L5 | L4 스크립트 3 | 라벨 L7(-0~3, 상위 L5 호출은 정상화) | 스크립트를 L5 폴더로 | A |
합계 예상: 라벨 A 전부 약 -45. 파일 이동 없음. (파일 자체가 L8이라 서버 구동 무관, 라우트 288 영향 없음)

| 결정 | 무엇을 정하나 | 안 정하면 | 추천 |
|---|---|---|---|
| (a) 정본 기준 | 위반 숫자를 "경로 추측(183)"으로 셀지 "레지스트리(61)"로 셀지 | 보고마다 숫자가 달라 진척 판단 불가 | 경로추측 정본(전수·기계적), 레지스트리는 참고 |
| (b) shim 유지 | 이동 후 옛 경로 임시 연결을 언제까지 둘지 | 옛 import 깨짐 or 영구 잔존 | 1회 배포 후 제거(테스트 통과 확인) |
| (c) 중복 삭제 | 바이트동일 0건이라 즉시 삭제 대상 없음. 오탐34/통합137 중 어디까지 손댈지 | 중복이 계속 누적 | 삭제 0, 통합은 표본 diff 후 video/ops 34건만 |
| (d) eum->hiworks | 영업메일용 2엣지를 예외 허용/공용 메일로 위임 | 게이트 FAIL 잔존 | 예외 등록(2건, 이동비용 대비 효과 작음), 이후 위임 |
| (e) SCC 467 | __init__ 재수출 순환 해소를 이번 범위에 넣을지 | 순환 게이트 값 고정 | 제외, __init__ 제외 재측정 먼저 |
| (f) 운영 배포 | 서버 반영 포함 여부 | 로컬만 바뀜, 서버는 옛 구조 | 이번엔 제외, 라벨성 변경 검증 후 별도 1회 |
| (g) S2 단위 | 파일 1개씩 vs 묶음 | 1개씩=안전·느림, 묶음=빠름·원인추적 어려움 | 라벨성은 묶음 1커밋, 실이동(#1,#3,#5,#8)은 1개씩 |
