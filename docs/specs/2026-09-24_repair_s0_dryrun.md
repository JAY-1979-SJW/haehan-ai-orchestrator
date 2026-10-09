# S0 드라이런·결과 — 층간 위반 집계 기준 통일 (2026-09-24)

## 원인 (51 vs 282)
같은 import_edges 를 서로 다른 두 잣대로 센 값이다.
- 282(약 280): classify_path(경로 추측) 층번호 하위→상위 numeric 판정. 파일 183 / 엣지 280 (layer_violations.json 은 생성기 없는 임시 산출물).
- 51: configs/module_registry.json 의 선언 층 + allowed_deps 방향모델 (modules.py '레이어 역전'). 파일 33 / 엣지 51.
- 결론: 51 은 "선언된 층 기준 위반", 280 은 "경로 추측 기준 위반(=라벨 오류 포함)". 51 로 낮춘 건 레이블 정정 효과이고 실제 의존은 그대로.

## 정본
- tools/code_map/layer_count.py → data/code_map/layer_baseline.json (primary_management_metric = 관리 기준, secondary = 레지스트리 기준).
- 신규 파일 1개, 기존 코드 수정 0. 게이트/라우트 영향 없음.

## 기준값 스냅샷 (master 683669cf 기준)
PRIMARY files=183 edges=280 / SECONDARY files=33 edges=51
