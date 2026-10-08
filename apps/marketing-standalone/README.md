# 마케팅 자동화 독립 앱 (Phase 1)

기준서: `docs/directives/marketing_app_modularization_20260908.md`

## 상태 (2026-09-08, Phase 1 완료)

원본 저장소(`scripts/naver/blog/`, `scripts/instagram/`)에서 사본을
이식했다. 원본은 변경하지 않았다 — 이 앱과 기존 운영 자동화는 서로 독립.

| 파일 | 상태 |
|---|---|
| `core/content_rules.py` | 완전 독립 (seo_check, split_body) |
| `core/topic_dedup.py` | 완전 독립 (발행 이력 캐시) |
| `connectors/blog_images.py` | 완전 독립 (Unsplash) |
| `core/blog_accounts.py` | 완전 독립 — **단, 값은 전부 템플릿**. 실제 회사 계정 정보 없음 |
| `connectors/cdp_helper.py` | 완전 독립 |
| `connectors/instagram_graph_api.py` | 완전 독립 (Graph API) |
| `connectors/naver_blog_cdp.py` | ⚠️ **Phase 1b 대상 — 원본 저장소에 브리지됨** |
| `site_modules/blog_router.py` | 위 조각들을 조합하는 CLI |

## 남은 작업 (Phase 1b — 별도 승인 후)

`connectors/naver_blog_cdp.py`가 아직 `scripts.naver.blog.core.writer`
(에디터 DOM 조작, 1,348줄), `scripts.naver.common.auth`(599줄), `scripts.auth.credentials`
(356줄)를 원본 저장소에서 그대로 import한다. 총 2,300줄 넘는 셀렉터
코드라 이번 작업에서 검증 없이 통째로 복사하지 않았다. 실제 배포
전에는 이 세 파일도 포팅하고, 반드시 라이브 발행 1건으로 검증해야 한다.

## Phase 2 / 3 (별도 승인 후)

- Phase 2: 지식iN 리서치(`naver_kin_client`) + 카페참여
  (`blog_explorer.py`, `targeted_engage.py`) — `ai_orchestrator` 사본 분리 필요
- Phase 3: 유튜브 OAuth 업로드 — 고객별 GCP 프로젝트 이슈 별도 검토

## 실행 방법

이 폴더 자체가 sys.path 루트다(하이픈 때문에 `apps.marketing-standalone.*`
dotted import 불가 — 각 파일이 `_bootstrap.py`로 자기 자신을 path에 추가).

```bash
python site_modules/blog_router.py draft.json --check
python site_modules/blog_router.py draft.json --publish
```

`.env`에 `UNSPLASH_ACCESS_KEY`, `IG_ACCESS_TOKEN`, `IG_USER_ID` 필요.
