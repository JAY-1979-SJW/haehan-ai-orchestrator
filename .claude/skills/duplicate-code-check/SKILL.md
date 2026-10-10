---
name: duplicate-code-check
description: 코드 중복 구현(복붙 함수, 병렬 모듈) 탐지. "중복 구현 확인해줘", "이 기능 이미 있나 전체 스캔해줘" 같은 요청, 또는 신규 코드 작성 전/대규모 작업 후 점검용. tools/hooks/duplicate_code_check.py 실전 검증 완료(2026-08-26).
---

# 코드 중복 검사 (duplicate_code_check.py)

CLAUDE.md의 "기존 구현 확인 의무"를 사후에 검증하는 도구.
`python tools/hooks/capability_check.py <키워드>` 는 신규 작업 **전에** 기존
구현을 찾는 도구이고, 이 스킬은 **이미 짜여진 코드 전체**에서 중복이
남아있는지 사후 스캔한다. 둘은 상호보완적이다.

## 실행

```bash
python tools/hooks/duplicate_code_check.py                       # scripts/ + ai_orchestrator/ 전체
python tools/hooks/duplicate_code_check.py --path scripts/naver   # 범위 좁혀서
python tools/hooks/duplicate_code_check.py --min-lines 10         # 짧은 보일러플레이트 제외
python tools/hooks/duplicate_code_check.py --json                 # 자동화 파이프라인용
```

## 잡아내는 것 2가지

1. **본문 복붙 중복(body_duplicates)** — 서로 다른 파일의 함수/클래스 본문이
   공백·주석 제거 후 완전히 동일. `min_lines`(기본 6) 미만인 작은 함수는
   흔한 보일러플레이트(예: `def noop(): pass`)라 제외한다.
   ⚠️ **v1 한계**: 완전 복붙만 잡는다. 변수명만 바꾼 사실상 동일 로직은
   못 잡는다(해시가 달라짐) — 이건 의도된 스코프 축소다, AST 정규화까지
   가면 오탐이 늘어나서 1차 버전에서는 정확도를 우선했다.
2. **동일 파일명 병렬 모듈(basename_duplicates)** — 서로 다른 디렉터리에
   같은 파일명(`actions.py`, `auth.py` 등)이 존재. **주의: 이 프로젝트는
   사이트별 커넥터 구조라 `scripts/{site}/auth.py` 처럼 "같은 이름, 다른
   사이트" 패턴이 의도된 설계다.** 이 신호는 "전수조사 후보 목록"이지
   전부 문제라는 뜻이 아니다 — 실제 기능이 겹치는지는 사람이 열어봐야 한다.

## 실전 발견 사례 (2026-08-26 최초 실행)

`scripts/eum/deregistration.py` 와 `scripts/eum/registration.py` 에
`_analyzed_field_selectors`(19줄), `_selector_from_field`(13줄) 가 완전히
동일한 본문으로 각각 존재 — 등록/철회 두 워크플로우를 만들면서 셀렉터
파싱 헬퍼를 복붙한 것으로 보인다. 공통 모듈로 뽑아낼 후보.

## 사용 시점

- 신규 기능 작업 마무리 후, 방금 만든 게 기존 것과 겹치지 않는지 최종 확인
- 대규모 리팩터링/정리 작업 전, 통합 대상 후보 파악
- 사용자가 "여기저기 비슷한 코드 있는지 봐줘" 라고 물어볼 때
- 이미 CLAUDE.md 게이트 의무(layer audit, quality gate)와 함께 커밋 전
  점검 루틴에 추가해도 좋다(현재는 자동 게이트에 편입되지 않은 수동 도구)

## 테스트

`tests/quality_gates/test_duplicate_code_check.py` — 8개 케이스(정확 복붙 탐지, 같은
파일 내 반복 무시, min_lines 필터, 변수명만 다른 경우 미탐지 확인, 서로
다른 함수 오탐 없음, 병렬 모듈 탐지, `__init__.py` 제외, 실제 저장소
스모크 테스트). `python -m pytest tests/quality_gates/test_duplicate_code_check.py -q`

관련: [[feedback_check_existing_before_building]]
