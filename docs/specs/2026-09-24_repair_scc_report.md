# 순환 import 최대 덩어리(SCC) 재측정 보고 (2026-09-24, 읽기 전용)
측정: data/code_map/map.json(py 엣지 8396) + 파일별 AST로 "함수 안 지연 import" 판별(자체 스크립트, 추정 오차 소폭 가능).

## ① 조건별 SCC (순환 묶음)
| 조건 | SCC 수 | 최대 크기 | 남은 엣지 |
|---|---|---|---|
| (i) 전체 | 13 | 467 | 8396 |
| (ii) __init__ 재수출(__init__이 내보내는 엣지) 제외 | 4 | 297 | 8057 |
| (iii) 함수 내부 지연 import 제외 | 22 | 35 | 7038 |
| (ii)+(iii) 둘 다 | 5 | 35 | 6777 |
핵심: 지연 import 제외 시 467 -> 35. 즉 덩어리의 대부분은 "함수 안에서 부르는" import가 만든 고리다.

## ② 최대 덩어리(467)의 영역
scripts/naver/automation 30, naver/blog 28, naver/cafe 27, naver/smartstore 23, google/cloud 21, google/workspace 15, naver/mail 12, ai_orchestrator/connectors/smartstore 11, connectors/google 6, google/youtube 6, naver/mail_read 5, connectors/youtube 4, local_agent/browser 4 ...
상위 폴더: scripts/naver 144, scripts/google 89, connectors 41, scripts/ops 27, eum 15, hiworks 10 -> 사실상 네이버+구글 두 영역이 통째로 얽힘.

## ③ 핵심 고리 엣지 (덩어리 내부 1647엣지 중)
- __init__이 보내는 엣지 173(10%), __init__으로 들어오는 엣지 487(30%), 지연 import 348(21%).
- 허브: scripts/naver/__init__.py(들어오는 129), scripts/google/__init__.py(85), scripts/web_connector.py(53), naver/smartstore/__init__(40), cdp_client.py(37).
| # | 엣지 | 유형 |
|---|---|---|
| 1-2 | naver/smartstore, naver/automation `__init__` -> naver/`__init__` | 재수출 |
| 3 | ops/audit_site_work_function_baseline -> naver/`__init__` | 허브 수신 |
| 4-5 | naver/smartstore/product, naver/blog `__init__` -> naver/`__init__` | 재수출 |
| 6-7 | google/router, ops/audit_google_automation_baseline_contract -> google/`__init__` | 허브 수신(7은 지연) |
| 8-20 | naver/router*.py, site_registry, cafe/*, blog/core/ai_writer -> naver/`__init__`; required_quality_gate -> cdp_client, google/tab_logic | 허브 수신 |
20개 중 17개가 __init__ 관련(재수출 발신 6 + 허브 수신 11), 나머지 3개는 일반 파일.

## ④ 실제 위험 근거
- 런타임 ImportError 사고 기록은 못 찾음(추정: 없음). 대신 회피 흔적은 있음: naver/blog/core/__init__.py("순환 회피 위해 개별 import"), local_agent_models.py(늦은 바인딩), module_quality_gate_common.py(지연 import), 테스트 test_backend_router_server_cycle_break_20260516.py.
- 즉 지금은 지연 import로 이미 "터지지 않게" 눌러둔 상태. 위험은 누군가 지연 import를 위로 올릴 때 발생(초기화 순서 오류).

## ⑤ 끊는 방법 후보
| 방법 | 변경 파일(추정) | 라우트 영향 | 위험 | 예상 SCC 효과 |
|---|---|---|---|---|
| A. __init__ 재수출 제거(허브 5개부터) | 허브 5 + 수신 ~300(직접 경로로 교체) | 없음(내부 import만) | 중(임포트 경로 오타 -> 런타임) | 허브 5개 수신 제외 실측: 467->411(작음). 재수출 전부 제거: 467->297 |
| B. 지연 import 위치 유지·정리 | 0~소수 | 없음 | 낮음 | 이미 반영된 상태(467->35 조건은 "지금 상태 유지" 의미) |
| C. 인터페이스 분리(공용 계약/타입 모듈 신설) | 35 덩어리 중심 ~35~60 | 없음 | 중 | 35 -> 소형 SCC 수준(추정) |
게이트가 지연 import를 순환으로 세는지가 관건: 게이트는 이미 일부 예외 처리(codebase_layer_audit.py:622).

## ⑥ 결정 추천
| 선택 | 결과 |
|---|---|
| 이번 범위에 포함 | 수정 파일 300+개, 검증 부담 큼, 효과는 재수출 제거 시 467->297(여전히 큼) |
| 제외(추천) | 실제 사고 근거 없음, 지연 import로 이미 안전. 다음 단계로 "지연 제외 35덩어리"만 별도 정리 |
추천: 제외. 대신 (a) 게이트/지도의 SCC 정의를 "지연 import 제외"로 바꿔 467을 35로 보고, (b) 그 35파일만 후속 과제로. 추정: 측정 스크립트는 from-import 이름 해석이 근사치.
