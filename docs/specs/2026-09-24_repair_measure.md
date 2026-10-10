# 정밀 측정 — 구조 정정 (2026-09-24, 읽기 전용)

방법: data/code_map/map.json(edges 2131노드, 내부 import 6073) + tools/hooks/duplicate_code_check.py --json (1432파일 스캔).

## 1. 순환 import (SCC, Tarjan)
- SCC 13개. 크기 분포: 2x3, 3x5, 4, 7, 8, 11, **467**.
- 거대 SCC 467파일: ai_orchestrator/connectors/*_router 포함 서버 전반. 원인은 패키지 __init__.py 재수출 허브(scripts/__init__ 761 importer, ai_orchestrator/__init__ 547) 추정 — 개별 파일 순환이 아니라 __init__ 경유 순환일 가능성이 큼. 확정하려면 __init__ 제외 재측정 필요(미실시).
- 소형 SCC: site_engine 11, local_agent_registry* 8, local_agent/browser 7, naver/shopping 4, browser_tool 3, form 3, ops/selector_health 3, naver/mail/analysis 3, scripts/gate-op_log-__init__ 3, searchad 2, validate_site_policy_config(archive 사본) 2.
- CIRCULAR_IMPORT 게이트 값과의 대조 필요.

## 2. 라우터 SQL 혼입
- 라우터 파일 96개(테스트 제외) 중 SQL 패턴 검출 1건: ai_orchestrator/browser_tool/router.py (1회, 오탐 여부 미확인).
- 실질 문제 거의 없음. 단 정규식 기반이라 문자열 조합 SQL은 누락 가능.

## 3. 도메인 간 직접 import (hiworks/eum/youtube/g2b)
- 실 위반 1쌍: eum -> hiworks 2엣지 (ai_orchestrator/connectors/eum_router.py -> scripts/hiworks/__init__.py, scripts/hiworks/mail.py). 영업메일 발송용으로 보임.
- youtube/g2b 관련 교차 0. 조치: 메일 발송을 공용 mail 커넥터(L3)로 위임하거나 예외 허용 결정 필요.

## 4. 중복 후보 171건 분류 (자동 휴리스틱, 표본 검토 전)
구성: 본문중복 65 + 동일 파일명 106.
| 분류 | 건수 | 비고 |
|---|---|---|
| 동일 파일명 - 관례명 오탐(router, auth, gates, models, _helpers 등) | 15 (파일명 종류, 해당 경로쌍 다수) | 도메인별 병렬 구조, 정상 |
| 동일 파일명 - 통합 검토 | 91 | 바이트동일 0건 -> 즉시 삭제 가능한 사본 없음. writer_pro, cafe writer 같은 이중 경로가 여기 |
| 본문중복 - 짧은 보일러/테스트 가짜객체 | 19 | 오탐 |
| 본문중복 - video 일회성 스크립트 | 10 | 공용 helper로 통합 가능 |
| 본문중복 - 통합필요 일반(ops audit_*, eum registration 등) | 34 | 공용 함수 추출 |
| 본문중복 - cli 배치 | 2 | resolve_topic_image 등, S3 #1과 연동 |
결론: 삭제 가능 확정은 0(바이트동일 없음). 대부분 통합 또는 오탐. 통합검토 91건은 각 쌍 diff 검토가 필요해 S5 착수 전 표본 확인 필수.

## 5. 사용자 결정 필요
1. 관리 기준 "51 vs 282" (기준서 5-1) 및 설계상 layer_violations.json(23시 산출) 이후 S0 통일 결과 반영 여부.
2. L2 라벨 커넥터군 재라벨(권장) vs 코드 순수화.
3. shim 유지 기간(영구/1회 후 제거).
4. 중복 삭제 허용 범위(통합검토 91건 중 원본 지정 기준).
5. eum -> hiworks 직접 import 허용 여부(예외 등록 vs 커넥터 위임).
6. 독립 앱(apps/marketing-standalone 등) 층 규칙 제외 확대 여부.
7. 운영 배포 포함 여부, 병합은 merge_stage.py 경유.
8. 거대 SCC 467: __init__ 재수출 제거를 S3 범위에 넣을지.
