# 네이버 카페 자동화 설계서

작성일: 2026-05-20  
작성자: Claude Code (haehan-ai-orchestrator)

---

## 1. 목표 및 범위

사용자(재키리/조명)가 네이버 카페를 업무 플랫폼으로 활용할 수 있도록  
**탐색 → 가입 → 수집 → 분류 → 글쓰기** 전 흐름을 자동화한다.

---

## 2. 기능 목록

### Phase 1 — 완료 (기존 구현)

| 기능 | 파일 | 상태 |
|------|------|------|
| 카페 글쓰기 (SE3 에디터) | `writer.py` | ✅ 완료 |
| 게시글 전수 수집 (90일) | `collector.py` | ✅ 완료 |
| 키워드+형태소 분류 | `classifier.py` | ✅ 완료 |
| 3단계 파이프라인 | `pipeline.py` | ✅ 완료 |
| 군집화+보고서 | `organizer.py` | ✅ 완료 |
| 원시 분석 | `analyzer.py` | ✅ 완료 |

### Phase 2 — 신규 개발 (본 설계서)

| # | 기능명 | 설명 | 우선순위 |
|---|--------|------|---------|
| 2-1 | 카페 검색 | 키워드로 네이버 카페 검색, 결과 목록 반환 | 높음 |
| 2-2 | 카페 탐색 | 카페 홈 구조(게시판 목록, 회원수, 소개) 파악 | 높음 |
| 2-3 | 카페 가입 | 가입 신청 자동화 (가입조건 확인 포함) | 중간 |
| 2-4 | 내 카페 목록 | 현재 가입된 카페 목록 조회 | ✅ 완료(조회) |
| 2-5 | 다중 카페 수집 | 여러 카페 동시/순차 수집 | 높음 |
| 2-6 | 통합 지식베이스 | 여러 카페 수집 결과 통합 분류·저장 | 높음 |
| 2-7 | 게시판별 타겟 글쓰기 | 카페+게시판 지정 글쓰기 | 중간 |

---

## 3. 기능별 상세 설계

### 2-1. 카페 검색 (`searcher.py`)

```
입력: 검색 키워드, 정렬(관련순/최신순), 최대 결과 수
출력: [{ name, url, member_count, category, description }]

URL 패턴:
  https://cafe.naver.com/SectionCafeListView.nhn?searchType=cafe&query={keyword}&page={n}
  또는 section.cafe.naver.com 검색 API

주요 함수:
  search_cafes(page, keyword, max_results=20) -> list[dict]
  _parse_search_results(page) -> list[dict]
```

### 2-2. 카페 탐색 (`explorer.py`)

```
입력: 카페 URL (예: cafe.naver.com/0moo)
출력: {
    cafe_id, cafe_name, clubid, member_count,
    boards: [{ name, menu_id, article_count }],
    description, grade, created_at
}

주요 함수:
  explore_cafe(page, cafe_url) -> dict
  get_board_list(page, clubid) -> list[dict]
  get_cafe_info(page, clubid) -> dict
```

### 2-3. 카페 가입 (`joiner.py`)

```
입력: 카페 URL, 가입 인사말(선택)
출력: { ok, reason }  # 성공/실패/이미가입/승인대기

흐름:
  1. 카페 가입 조건 확인 (자동승인 vs 관리자 승인)
  2. 가입 버튼 클릭
  3. 가입 인사말 작성 (필요 시)
  4. 제출 → 결과 확인

보안: 외부 공개 가입 신청 → 매번 사용자 재확인 필수
```

### 2-5. 다중 카페 수집 (`multi_collector.py`)

```
입력: [{ cafe_url, days, max_detail }]
출력: 카페별 raw_articles_*.json 개별 저장 + 통합 목록

흐름:
  for each cafe:
      collect_articles(page, cafe_url, days, ...)
      save to data/cafe/{cafe_id}/raw_articles_{ts}.json
  save manifest: data/cafe/multi_collect_manifest_{ts}.json

주요 함수:
  collect_multi(page, cafe_list) -> dict
```

### 2-6. 통합 지식베이스 (`kb_merger.py`)

```
입력: data/cafe/*/classified_*.json 여러 파일
출력: data/cafe/unified_kb_{ts}.json + unified_report_{ts}.txt

기능:
  - 카페별 분류 결과 병합
  - 중복 제거 (동일 article_id)
  - 카테고리별 통합 군집화
  - 카페 출처 태그 유지

주요 함수:
  merge_knowledge_bases(input_paths) -> dict
```

### 2-7. 게시판 타겟 글쓰기 (writer.py 확장)

```
기존 write_post()에 board_name 파라미터 추가:
  write_post(page, cafe_url, board_name, title, content, ...)

게시판 선택 로직:
  - board_name 으로 좌측 메뉴에서 해당 게시판 클릭
  - 없으면 기본 게시판(전체글보기) 사용

보안: 외부 공개 게시 → 매번 사용자 재확인 필수
```

---

## 4. 파일 구조 (전체)

```
scripts/naver/cafe/
├── __init__.py
├── _runner.py          # CLI 진입점 (서브커맨드 라우팅)
│
├── [Phase 1 — 완료]
├── collector.py        # 게시글 수집
├── classifier.py       # 분류 (키워드+KoNLPy)
├── pipeline.py         # 3단계 파이프라인
├── organizer.py        # 군집화+보고서
├── analyzer.py         # 원시 분석
├── writer.py           # 글쓰기
│
└── [Phase 2 — 신규]
    ├── searcher.py     # 카페 검색
    ├── explorer.py     # 카페 탐색
    ├── joiner.py       # 카페 가입
    ├── multi_collector.py  # 다중 카페 수집
    └── kb_merger.py    # 통합 지식베이스

data/cafe/
├── {cafe_id}/                  # 카페별 폴더 (다중 카페 시)
│   ├── raw_articles_*.json
│   ├── classified_*.json
│   └── knowledge_base_*.json
├── multi_collect_manifest_*.json
├── unified_kb_*.json
└── unified_report_*.txt
```

---

## 5. CLI 서브커맨드 설계 (`_runner.py` 확장)

```bash
# 기존
python -m scripts.naver.cafe.writer write --cafe 0moo --board 자유게시판 --title "제목" --content "내용"

# 신규
python -m scripts.naver.cafe search --keyword "건설" --max 20
python -m scripts.naver.cafe explore --cafe cafe.naver.com/0moo
python -m scripts.naver.cafe join --cafe cafe.naver.com/0moo
python -m scripts.naver.cafe collect-multi --cafes 0moo,shop07,revitbim --days 90
python -m scripts.naver.cafe merge-kb --input data/cafe/*/classified_*.json
```

---

## 6. 데이터 흐름

```
[검색/탐색]
  searcher.py → 카페 후보 목록
  explorer.py → 카페 상세 구조 파악
        ↓
[가입]
  joiner.py → 가입 신청 (사용자 승인 후)
        ↓
[수집]
  collector.py / multi_collector.py → raw_articles_*.json
        ↓
[분류·가공]
  pipeline.py (classifier + TF-IDF) → classified_*.json
        ↓
[통합]
  kb_merger.py → unified_kb_*.json
        ↓
[분석·보고]
  organizer.py → organized_report_*.txt
  Claude Code 직접 분석 → 보고 (AI API 호출 금지)
        ↓
[글쓰기]
  writer.py → 카페 게시판 게시 (사용자 승인 후)
```

---

## 7. 보안·운영 원칙

| 항목 | 규칙 |
|------|------|
| 카페 가입 신청 | 매번 사용자 재확인 필수 |
| 게시글 게시 | 매번 사용자 재확인 필수 |
| AI API 호출 | 분류·분석 시 외부 AI API 호출 금지. Claude Code 직접 분석 |
| 쿠키/세션 | 추출·저장·출력 금지 |
| 수집 속도 | 상세 방문 간 2.5초 대기 (서버 부하 방지) |
| 데이터 저장 | data/cafe/ 이하 로컬만. 외부 전송 금지 |

---

## 8. 개발 순서 (권장)

1. `searcher.py` — 카페 검색 (독립 기능, 빠른 개발)
2. `explorer.py` — 카페 탐색 (수집 전 구조 파악용)
3. `multi_collector.py` — 다중 수집 (기존 collector.py 재사용)
4. `kb_merger.py` — 통합 지식베이스
5. `writer.py` 확장 — 게시판 타겟 글쓰기
6. `joiner.py` — 카페 가입 (보안 민감, 마지막 개발)
