# 블로그 모듈 (`scripts/naver/blog/`)

네이버 블로그 마케팅 관련 코드는 **전부 이 폴더 안에** 있다.
2026-08-24에 4곳에 흩어져 있던 것을 여기로 모았다.

## 계정 (2026-08-24 다중화)

`accounts.py`에 등록된 계정 2개를 관리한다. 계정마다 발행 이력 캐시가
**분리**돼 있다(`data/blog_topic_cache_{계정}.json`) — 섞으면 중복 발행
방지 로직이 오작동한다.

| 계정 | 도메인 | 주소 | 상태 |
|---|---|---|---|
| `skyjwsin` (기본) | 건설공무 | blog.naver.com/skyjwsin | 리서치·발행 파이프라인 완성 |
| `skyjwshin` | 조명인테리어 | blog.naver.com/beautiful-light | 계정만 등록, **주제 리서치 미착수** |

`skyjwshin`으로 발행하려면 먼저 조명 도메인 리서치(카페/검색량/실질문
3중 검증 — `research_blog_topics.py`가 건설용으로 하는 것과 같은 과정)가
필요하다. 검증 안 된 조명 키워드를 지어내 자동 분류하지 않는다
(`topics.py::classify_account()` 참조 — 매칭 안 되면 사람 판단으로 넘긴다).

CLI 대부분은 `--account skyjwsin|skyjwshin` 인자를 받는다(기본값 skyjwsin).

## 구조

```
scripts/naver/blog/
├── marketing/     주제 선정 → 본문 생성 → 이미지 → 발행 (파이프라인 본체)
├── core/          네이버 에디터 자동화 (writer.py = 실제 글 쓰는 엔진)
├── management/    발행글 캐시·통계·댓글·시리즈·이웃
├── community/     타 블로그 탐색·교류
├── seo/           SEO 점검
├── utilities/     스크래핑 유틸
└── cli/           커맨드라인 진입점 (원래 scripts/ops/ 에 있던 것)
```

## 자주 쓰는 명령

```bash
# 주제 리서치 (카페 빈도 + 검색광고 실검색량 + 지식iN 3중 검증)
python -m scripts.naver.blog.cli.research_blog_topics

# 원고 점검 → 발행
python -m scripts.naver.blog.cli.blog_publish_manual draft.json --check
python -m scripts.naver.blog.cli.blog_publish_manual draft.json --publish

# 성과 분석 (유입경로·조회수 순위)
python -m scripts.naver.blog.cli.blog_analytics_report

# 분리 가능성 점검
python -m scripts.naver.blog.cli.check_blog_separability
```

## 왜 한 폴더로 모았나

분리 경계를 **손으로 관리하는 목록**으로 유지하려니 계속 낡았다. 2026-08-18에
적어둔 목록이 6일 만에 어긋나서(필수 파일 3개 누락, 못 쓰는 파일 1개 포함)
`check_blog_separability.py` 라는 점검 도구까지 만들어야 했다.

폴더 하나로 모으니 그 목록 자체가 없어졌다. 이제 점검 도구의 대상은
`scripts/naver/blog` 한 줄이고, **이 폴더 안에 새 파일을 만들면 자동으로
검사 대상**이 된다. 목록이 낡을 수가 없다.

## 규칙

- **타 업무 도메인 import 금지** — EUM·g2b·스마트스토어·하이웍스 등.
  `check_blog_separability.py` 가 이걸 검사한다(현재 0건).
- **앱 본체(`ai_orchestrator`) 의존은 최소화** — 현재 7건 있고, 분리할 때
  손봐야 할 목록이다. 새 코드에서 늘리지 않는다.
- **import ≠ 실행** — 발행처럼 외부에 영향을 주는 스크립트는 반드시
  `if __name__ == "__main__":` 가드를 둔다. `blog_cad_draft_posts.py` 는
  이 가드가 없어서 import만으로 글 19편 작성이 시작된 적이 있다(2026-08-24).

## 관련 문서

- `docs/specs/naver_blog_content_standard.md` — 콘텐츠 기준서 (무엇을 어떻게 쓰는가)
- `.claude/skills/naver-blog-publish/` — 발행 스킬
