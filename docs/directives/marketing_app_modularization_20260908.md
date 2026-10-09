# 마케팅 자동화 독립 앱 모듈화 — 기준서 (2026-09-08)

## 0. 목적

네이버 블로그 자동발행 + 인스타그램 자동발행 + (2차) 유튜브·카페참여/리서치를
**별도 로컬 프로그램으로 배포**하기 위해, 이 저장소 안에서 먼저 의존성을
끊고 독립 모듈로 분리한다. 기존 코드는 그대로 두고(코드 보존 원칙), 신규
경로에 **사본을 이식**하는 방식으로 진행한다 — 기존 운영 중인 블로그/인스타
자동화가 이 작업으로 깨지면 안 된다.

## 1. 배치 위치 (레이어 기준)

```
apps/marketing-standalone/          ← 신규 최상위 디렉터리 (신규 도메인, 기존 L1~L12와 별개 트리)
├── core/                           # L1 순수 로직 — 외부 미의존
│   ├── content_rules.py           # seo_check, 기승전결 검증
│   └── topic_dedup.py             # 중복발행 캐시 로직
├── connectors/                     # L3 외부 클라이언트
│   ├── naver_blog_cdp.py          # writer.py + blog_publish_manual.py 사본
│   ├── instagram_graph_api.py     # api_publish.py 사본 (원본 그대로 무의존)
│   ├── naver_kin_client.py        # [Phase 2] ai_orchestrator에서 사본 분리
│   └── youtube_data_api.py        # [Phase 3] oauth.py + upload 사본
├── site_modules/                   # L5 라우터
├── workflows/                      # L6 오케스트레이션
└── README.md                       # 원본 대비 무엇을 뺐는지/의존관계 명시
```

`apps/`는 기존 L1~L12 디렉터리 구조와 겹치지 않는 신규 트리이므로
`codebase_layer_audit.py`의 기존 규칙에 신규 예외 등록이 필요할 수 있다
(감사 실행 후 FORBIDDEN_IMPORT 발생 시 별도 보고).

## 2. 실행 순서 (Phase — 각자 별도 승인)

| Phase | 범위 | 근거 |
|---|---|---|
| **Phase 1 (이번 작업)** | 블로그 핵심 발행 경로 + 인스타 Graph API | 둘 다 `ai_orchestrator` 무의존 확인됨(실측) — 위험 최소 |
| Phase 2 | 지식iN 리서치(`naver_kin_client`) + 카페참여(`blog_explorer`, `targeted_engage`) | `ai_orchestrator.connectors.naver_kin_client`, `scripts.browser.agent.agent` 사본 분리 필요 |
| Phase 3 | 유튜브 OAuth 업로드 | 고객별 GCP 프로젝트/OAuth 클라이언트 이슈 별도 검토 필요 |

이번 지시("현재 코드에서 먼저 분리해서 모듈화")는 **Phase 1**을 우선
실행하고, Phase 2·3은 Phase 1 완료·검증 후 순차 진행한다.

## 3. Phase 1 상세 — 이식 대상 파일

| 원본 | 사본 위치 | 변경 여부 |
|---|---|---|
| `scripts/naver/blog/marketing/content.py` (seo_check, split_body) | `apps/marketing-standalone/core/content_rules.py` | import 경로만 수정 |
| `scripts/naver/blog/cli/blog_publish_manual.py` | `apps/marketing-standalone/site_modules/blog_router.py` | import 경로 수정, CLI 인자 유지 |
| `scripts/naver/blog/marketing/images.py` | `apps/marketing-standalone/connectors/blog_images.py` | 그대로 |
| `scripts/naver/blog/accounts.py` | `apps/marketing-standalone/connectors/blog_accounts.py` | 계정 목록은 신규 앱 전용 config로 교체(고객 계정은 다름) |
| `scripts/instagram/api_publish.py` | `apps/marketing-standalone/connectors/instagram_graph_api.py` | 그대로(이미 무의존) |
| `scripts/browser/cdp/cdp_helper.py` | `apps/marketing-standalone/connectors/cdp_helper.py` | 그대로 |

**뺄 것 (Phase 1 범위 아님)**: `research_blog_topics*.py`, `blog_explorer.py`,
`targeted_engage.py`, `blog_scraper.py`, `apply_cta_to_batches.py`,
`publish_ep_batch*.py` — 전부 `ai_orchestrator` 의존.

## 4. 영향 파일 / 보안 / DB 영향

- **영향 파일**: 신규 파일만 생성(`apps/marketing-standalone/` 하위). 기존
  `scripts/naver/blog/`, `scripts/instagram/` 파일은 **읽기만**, 수정 없음.
- **DB 영향**: 없음. 신규 앱은 자체 로컬 캐시(JSON)로 시작, 기존 운영 DB
  미접근.
- **보안 영향**: 없음. secret/token은 신규 앱도 `.env` 패턴 유지, 원문 로그
  출력 금지 동일 적용.
- **회귀 위험**: 없음(원본 미변경) — 단, 사본이 원본과 갈라진 뒤 원본에
  버그 수정이 생기면 사본에 수동 반영해야 하는 유지보수 부담 발생(README에
  명시 예정).

## 5. 완료 후 실행할 게이트

```bash
python tools/repo_gates/codebase_layer_audit.py
pytest tests/test_codebase_layer_audit.py -q
python tools/quality/quality_gate.py --staged --enforce --allow-existing-code-change
python tools/hooks/duplicate_code_check.py   # 사본이 "중복 구현"으로 오탐되는지 확인
```

`duplicate_code_check.py`가 사본을 중복으로 잡을 가능성이 높음 — 오탐이면
allowlist에 `apps/marketing-standalone/`를 의도적 사본으로 등록.
