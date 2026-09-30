# 블로그 자동 작성 자동화 (오케스트레이터 앱) — 기준서 v2

- 날짜: 2026-09-30 / 상태: **v2 — A단계 구현 완료(2026-09-30, `scripts/naver/blog/automation/{rules,gates}.py` + 테스트 111개), B단계 승인 대기**
- A단계 구현 시 확인·추가한 것: 조명 계정 `skyjwshin` 은 README 상 "발행 전 사람 검수 필요"라 **승인이 있어도 자동 발행 불가**(`AUTO_PUBLISH_BLOG_IDS={"skyjwsin"}`로 코드 강제), 리서치 파일은 계정별(`data/blog_topic_research_latest.json` / `_lighting_latest.json`), 규칙 `id` 는 파일 이름이라 경로 문자 거부, 예정 시각 뒤 10분 창 안에서만 실행(따라잡지 않음), `management/schedule.py` 는 네이버 예약 발행 DB 큐라 재사용 대상 아님.
- 이전 판(v1/v1.1)은 `docs/specs/naver_blog_content_standard.md`·`scripts/naver/blog/` 를 읽지 않고 써서 여러 곳이 틀렸다(§10 정정 이력, git 이력 `8cc9a409`·`30653ffe`).
- 사용자 결정(2026-09-30): ① 대상 = **오케스트레이터 앱**(Haehan AI 데스크 앱 `/naver/blog`, 소유자 블로그 `skyjwsin`) ② 글쓰기 엔진 = **Claude 연동**(`claude -p` 텍스트 생성만) ③ 주제 = **사용자 목록 + 리서치 결과 함께** ④ 발행 = **사용자가 승인한 규칙 안에서 자동 발행**.
- 작성 기준은 `docs/specs/naver_blog_content_standard.md`(이하 "기준서")를 그대로 따른다. 코드가 기준서와 어긋나면 코드가 틀린 것이라는 기준서 원칙(첫머리)을 이 문서도 따른다.

## 1. 현황 (실측 — 코드를 직접 읽고 확인)

**이미 있는 것: 주제→이미지→본문→발행→대기 전체 흐름** (`scripts/naver/blog/cli/blog_ai_batch_20.py::run`). 자동화는 이 흐름에 "규칙·예약·안전장치"를 씌우는 일이다.

| 부품 | 위치 | 자동화에서의 쓰임 |
|---|---|---|
| 주제 리서치 3중 검증 | `cli/research_blog_topics.py` → `data/blog_topic_research_latest.json` (필드: `keyword`, `cafe_freq`, `total_search`, `competition`, 지식iN 질문 `question_title`/`question_description`) | 주제 출처 ② |
| 주제 선정·중복 | `marketing/topics.py`: `get_researched_topics()`(30일 유효), `generate_topics()`, `is_duplicate()`, 캐시 `data/blog_topic_cache*.json`(계정별) | 재사용 |
| 본문·제목·SEO | `marketing/content.py`: `generate_post()`(프롬프트=기준서 6단), `seo_check()`, `split_body()`, `_CTA_BLOCK` | 프롬프트·검사 재사용 |
| 이미지 | `marketing/images.py`: `fetch_unsplash_images`, `pick_3_images` | 재사용 |
| 발행 | `marketing/publish.py::publish_one` → `core/writer.py::write_post` | 재사용 (옵션 `save_draft_only`·`require_approval`·`schedule_at`·`visibility`) |
| 계정 | `accounts.py`(다계정: `skyjwsin` 건설 / `skyjwshin` 조명), `TARGET_BLOG_ID="skyjwsin"` | 규칙의 대상 계정 |
| 서버 API | `ai_orchestrator/connectors/naver_blog_router.py`: `compose`(로컬 초안), `drafts`, `write-to-naver`, `seo` | 화면·API 접점 |
| 화면 | `admin-web/src/app/naver/blog/page.tsx` = AI 채팅 + 작업 기록 패널뿐 | 규칙 탭 추가 |
| 스케줄러 패턴 | `server.py` lifespan 의 `asyncio.create_task(<x>_schedule_loop())` (gonobi·community·naver_search) | 등록·취소·`to_thread` 패턴만 재사용 |

**이 흐름을 그대로 무인 자동화에 쓸 수 없는 이유 (코드로 확인한 결함·위험)**

| # | 사실 | 결과 | 대응 |
|---|---|---|---|
| F1 | `generate_post()`·`generate_topics()` 의 LLM 호출이 `AIResponder._call` — 이 앱에서는 "앱 런타임 AI 없음, Claude Code가 작성" 스텁(`ok` 아님) | 앱 안에서 본문 생성이 항상 `None` | LLM 호출부만 `claude -p` 텍스트 생성으로 교체할 수 있는 이음새 추가(§5) |
| F2 | **리서치 파일이 2026-08-24 생성 → 오늘 37일 경과, 유효 30일 초과** → `get_researched_topics()` 가 빈 목록 | 그대로 돌리면 `generate_topics()` 가 **AI 보충 생성**으로 빠짐 = 기준서 §1 "AI가 주제를 지어내지 않는다" 위반 | 자동 실행에서 AI 보충 경로를 **금지**하고, 리서치가 낡으면 실행을 멈추고 재실행을 안내 |
| F3 | **`connect_and_ensure_login()` 은 계정이 다르면 `nidlogin.logout` 으로 이동해 로그아웃 후 강제 재로그인**(`# session-ok` 표기, 2026-08-24 오판 사고 이력) | 무인 실행 시 사용자 로그인 세션을 파기할 수 있음 = 프로젝트 "로그인 세션 보존" 원칙 위반 | 자동 실행은 이 함수를 **쓰지 않는다.** 읽기 전용으로 (요소 기준 로그인 판정 `in`) + (블로그 공개 주소가 대상 계정과 일치) 를 확인하고, 아니면 중단·알림 |
| F4 | `publish_one` 은 `visibility="public"`, `require_approval=False`(즉시 공개 발행). `record_success` 는 **발행 성공 뒤에만** 캐시 기록 | 발행 직후 프로세스가 죽으면 다음 회차가 같은 주제를 다시 발행 — 기준서 §5.2 의 2026-08-17 이중 발행 사고 원인과 같음 | 발행 **시도 전에** 예약 기록을 남기고 성공 시 확정, 실패·중단은 기록에 표시 |
| F5 | `generate_post()` 는 모든 글에 같은 `_CTA_BLOCK`(적산 실측치 CTA)을 붙임 | 기준서 §4 "표준 CTA를 아무 글에나 붙이지 않는다, 검증된 기능이 없는 주제는 정직한 포지셔닝 문구로 주제마다 새로 쓴다" 위반 | 자동 실행은 주제 성격(`is_product_related`)에 따라 CTA를 고른다(§4 단계 5) |
| F6 | `write-to-naver` 라우트: `BlogWriter.open(auto_login=True)`(세션 무효 시 스스로 로그인 시도), `get_page()`(사용자가 쓰던 활성 탭 사용) | 사용자가 브라우저를 쓰는 중 탭이 가로채지고, 자동 로그인이 켜져 있음 | 자동 실행 경로는 이 라우트가 아니라 `write_post` 를 전용 새 탭에서 호출. 라우트를 바꿔야 하면 `auto_login`·전용 탭 필드를 **추가만**(기본값 유지) |
| F7 | 스케줄러는 고정 간격 sleep 루프, 마지막 실행 기록 없음 | 요일·시각·한도·재시작 후 중복 방지 표현 불가 | 1분마다 "지금 실행할 규칙이 있나"만 판단하는 루프 + 실행 기록(`state`) 신규 |
| F8 | 문서·코드 값 불일치: 태그 최소 5(문서)/15(코드), 본문 최소 1,200(문서)/2,500(코드) | 게이트 기준 모호 | **코드 값**을 게이트로 쓰고 문서 정정은 별도 과제 |

## 2. 사용자에게 보이는 기능
1. **규칙 만들기**(`/naver/blog` "자동 작성" 탭): 대상 계정, 주제 출처(직접 입력 목록 / 리서치 결과), 요일·시각, 하루·주 최대 편수, 금칙어, 공개 범위, 모드(`draft_only`/`auto_publish`).
2. **승인**: 규칙 저장 시 "이 범위에서 자동 발행합니다" 요약을 보여주고 사용자가 승인해야 `auto_publish` 가 켜진다. 승인 전·규칙 수정 후에는 `draft_only`.
3. **관리**: 일시정지/재개, 지금 1회 실행(발행 없는 시험 실행), 실행 이력(성공·건너뜀·중단 이유), 리서치 신선도 표시(마지막 갱신일·30일 초과 경고).

## 3. 규칙 모델 (파일 `data/blog_automation/rules/<id>.json` — DB 스키마 변경 없음)
`id, name, blog_id(기본 skyjwsin), topics{user_list[], use_research}, schedule{days,times,tz}, limits{per_day,per_week,gap_seconds(기본 90)}, forbidden_words[], visibility, mode, approval{approved_by,approved_at,rule_hash}, paused`
- `topics.user_list[]` 항목은 기존 `topic_info` 스키마와 같다: `{topic, keywords[], angle, source_description?}`.
- `rule_hash`: 승인 시점의 규칙 내용 해시. 수정하면 해시가 달라져 승인이 무효가 된다.

## 4. 실행 흐름과 안전장치
```
1분 틱 → 실행할 규칙? → [1 사전 조건] → [2 주제 선정] → [3 글 생성] → [4 품질 검사] → [5 CTA·이미지] → [6 중복 예약] → [7 발행] → 기록·알림·대기
```
| # | 단계 | 규칙 | 실패 시 |
|---|---|---|---|
| 1 | 사전 조건 | 규칙 승인됨·일시정지 아님·한도 여유·허용 시간대 · **리서치 파일 30일 이내**(주제 출처가 리서치일 때) · **로그인 `in`(요소 기준 판정) + 블로그 공개 주소 == 대상 계정 alias**(읽기 전용) · Claude 호출 가능 | 실행 안 함, 이력·알림. **로그아웃·자동 로그인·계정 전환 시도 금지** |
| 2 | 주제 선정 | ① 사용자 목록 ② 리서치 결과(`get_researched_topics`)만. **AI 보충 생성 금지**. 사용자 입력 주제는 리서치 지표(월 검색량 500 이상 = `_MIN_SEARCH_VOLUME`, 지식iN 질문 존재)로 검증 — **미검증 주제는 초안까지만**(자동 발행 제외). `is_duplicate` 통과 | 해당 주제 건너뜀 |
| 3 | 글 생성 | `claude -p --output-format json --max-budget-usd <상한> -- <지시문>` **도구·MCP 없이** 텍스트만. 지시문 = `generate_post` 의 기준서 6단 프롬프트 재사용(주제·`source_description` 주입). 실행 폴더는 저장소 밖 중립 폴더. 파싱: `TITLE:`/본문/`TAGS:` | 재시도 없음(다음 회차) |
| 4 | 품질 검사 | `seo_check` **무경고** + 금칙어 + 태그·본문 하한(코드 값) + 결론 문단 + **검증 필요 수치 경고 0건**. 경고가 있으면 경고 문구를 지시문에 되먹여 **1회 재생성** | 초안으로 남김 + 사유 |
| 5 | CTA·이미지 | CTA: `is_product_related(topic)` 이면 표준 CTA(실측치), 아니면 기준서 §4 의 정직한 포지셔닝 문구를 **주제에 맞게 새로 작성**. 이미지: `pick_3_images`. 브랜드 표기 "해한 AI" | 초안으로 남김 |
| 6 | 중복 예약 | 발행 **시도 전에** 캐시에 `pending` 기록(`is_duplicate` 가 pending 도 중복으로 봄). 성공 시 `log_no` 로 확정, 실패는 `failed` 표시 | 중복이면 건너뜀 |
| 7 | 발행 | 모드가 `draft_only` → `write_post(save_draft_only=True)`, `auto_publish` + 승인 유효 + 게이트 통과 → 발행. 전용 새 탭. 캡차·2단계 인증·모달 감지 시 즉시 중단(입력 시도 금지) | 중단, 초안 보존, 알림 |
- **한도·승인·게이트는 코드가 강제**한다(지시문에 의존하지 않음). 초과분은 무조건 초안.
- 포스트 간 `gap_seconds`(기본 90초) 대기(봇 감지 방지, 기준서 §5.2). 놓친 회차는 **따라잡지 않는다.**
- **킬스위치**: 일시정지 한 번이면 이후 모든 예약이 멈춘다. 연속 실패 3회면 스스로 일시정지.
- 발행 후 수정·삭제는 자동으로 하지 않는다.
- 프로젝트 규칙(외부 공개 발행은 매번 재확인)의 예외는 **사용자가 규칙을 명시 승인한 범위 안**으로 한정한다(기준서 §6 "이미 승인한 배치 흐름 안에서는 sub-step 재확인 안 함"과 일치). 승인 기록(누가·언제·규칙 해시)을 남긴다.
- **네이버 예약 발행(`write_post(schedule_at=…)`) 검토 항목:** 사용자 PC가 꺼져 있어도 정시 발행이 되지만 그 시점의 품질·승인 재검사가 불가능하다. 초기에는 사용하지 않고 D단계 이후 별도 판단.

## 5. 변경 대상 (배치·레이어)
| 대상 | 내용 | 비고 |
|---|---|---|
| **신규** `scripts/naver/blog/automation/` | `rules.py`(규칙 모델·승인 해시) · `gates.py`(사전 조건·한도·품질·CTA 선택·중복 예약: **순수 함수**) · `state.py`(실행 기록) · `llm.py`(`claude -p` 텍스트 어댑터) · `runner.py`(1회 실행 오케스트레이션) | **분리 경계 안**(기준서 §0). 타 업무 도메인 import 0건 유지, `check_blog_separability` 통과가 게이트 |
| 수정(추가만) `marketing/content.py` | `generate_post(..., llm=None)` 이음새: 기본값이면 종전 동작(`AIResponder`), 주면 그 함수로 LLM 호출 | 기존 호출자 무영향. CTA 선택은 `cta` 인자 추가만 |
| 수정 안 함 | `topics.generate_topics`(AI 보충 경로는 자동 실행에서 호출하지 않음), `publish.connect_and_ensure_login`(호출하지 않음), `write_post` | |
| **신규** L8 `ai_orchestrator/routers/blog_automation_router.py` | 규칙 CRUD·승인·일시정지·지금 실행·이력·리서치 신선도. 얇게 | `naver_blog_router` 는 건드리지 않음 |
| 스케줄러 등록 | `server.py` lifespan 에 태스크 **한 줄** | `refactor/server-entrypoint-collision`(server.py→asgi.py) 병합 뒤에 등록해 충돌 회피 |
| 화면 L9 | `/naver/blog` "자동 작성" 탭 | |
| 등록 | `configs/module_registry.json`(`registry_sync.py --fix`) | 커밋 게이트 요구 |

## 6. 단계 (각 단계 끝에서 승인·검증)
| 단계 | 내용 | 네이버에 쓰는가 |
|---|---|---|
| **A** | `rules.py`·`gates.py` 순수 함수 + 테스트(한도·시간대·금칙어·승인 해시 무효화·CTA 선택·중복 예약·리서치 신선도·로그인 사전 조건) + 모듈 등록. 서버·화면·발행 변경 없음 | 아니오 |
| **B** | `llm.py` + `runner.py` 1회 실행(로컬 초안까지, 네이버에 안 씀) + `content.generate_post` 이음새 + 규칙 API. **먼저 리서치 재실행 필요**(F2, 외부 키 사용 → 별도 승인) | 아니오 |
| **C** | 스케줄러 + 화면 + 네이버 **임시저장**(`save_draft_only`) 연결 | 임시저장만 |
| **D** | 자동 발행 — 승인 규칙 + 게이트 통과 시에만. 기준서 §7 절차: **라이브 1건 → 실제 페이지에서 반영 확인 → 이후 진행** | **공개 발행(최종 승인 필요)** |

## 7. 드라이런 결과 (2026-09-30, 발행 없음) — 참고치
- `claude -p` 텍스트 생성 3편 동시(도구 없음): **34~39초, 편당 약 $0.09(API 환산, 사용자 Claude 사용량에서 차감)**, 본문 2,735~3,167자, 태그 25개, 기존 `seo_check` 1회차 통과 2/3(실패 1건은 핵심 키워드 출현 횟수 미달 하나). 직접 읽은 1편은 6단 구성을 지켰고 불확실한 법령은 "확인이 필요합니다"로 처리했다.
- **한계:** 주제 3개는 제가 임의로 만든 것이라 기준서 §1 입력이 아니다(통과율은 참고치). 표본 3편·1회. `seo_check` 는 사실 정확성·현장 적합성·"[정리하면]이 실제 결론을 내는가"(기준서 §2.4-2)를 보지 못한다 → 초기에는 `draft_only` 로 운영해 사람이 품질을 보는 기간을 둔다.
- 재시도(경고 되먹임) 효과는 아직 시험하지 않았다.

## 8. 테스트·검증
- 단위: 한도(하루/주)·허용 시간대·금칙어·승인 후 규칙 수정 시 발행 차단·일시정지·연속 실패 자동정지·리서치 30일 초과 시 실행 금지·AI 보충 경로 미호출·중복 예약(pending)·CTA 선택·로그인/계정 불일치 시 중단(로그아웃 호출 없음을 검증).
- 변이 시험: 한도 검사·승인 해시 검사·로그인 사전 조건·리서치 신선도 검사 제거가 테스트에 잡히는지.
- 분리 점검: `python -m scripts.naver.blog.cli.check_blog_separability` 통과, `codebase_layer_audit` 새 위반 0.
- 실제 화면: D단계 전까지 **네이버 공개 발행 없음.** D단계는 라이브 1건 후 실제 페이지 확인.

## 9. 위험·한계
- PC와 Claude가 켜져 있어야 실행된다. 꺼져 있으면 그 회차를 건너뛰고 이력에 남긴다(몰아서 발행하지 않음).
- 사용자 Claude 구독 한도에 걸리면 실패로 처리하고 다음 예약 시각에 재시도.
- 네이버 화면·정책 변화로 발행이 깨질 수 있다 → 실패는 초안 보존 + 알림, 자동 재시도 없음.
- 저품질·중복 판정 위험은 한도·중복 예약·기준서 §4.1 로 줄일 뿐 없애지 못한다.
- 자동 발행은 계정의 공개 게시물이라 오발행이 곧 외부 노출이다 → 기본값은 언제나 `draft_only`.
- `is_product_related` 는 소유자 제품 키워드 목록(`PRODUCT_KEYWORDS`) 기반이라 소유자 블로그 전용 판정이다(분리 판매 시 교체 대상).

## 10. 정정 이력 (v1/v1.1 에서 틀렸던 것)
주제를 임의로 만들었다(기준서 §1 위반) · 분리 경계(`scripts/naver/blog/`) 밖에 배치했다 · 이미 있는 부품(중복 검사·SEO·이미지·주제 리서치·발행)을 새로 만들려 했다 · 소유자 CTA 규칙(§4)을 반영하지 못했다 · 대상 앱을 확정하지 않았다(독립 앱 `apps/marketing-standalone` 과 혼동) · 기존 로그인 함수의 로그아웃·강제 재로그인 위험과 리서치 파일 만료를 몰랐다.

## 11. 되돌리기
새 모듈·라우터·화면 탭 삭제 + `content.generate_post` 이음새 인자 revert. 기존 발행·주제·이미지 코드와 서버 라우트는 수정하지 않는다.

## 12. 승인 요청
**A단계**(`scripts/naver/blog/automation/` 의 규칙 모델 + 순수 검사 함수 + 테스트 + 모듈 등록, 네이버 발행·서버·화면 변경 없음)부터 승인을 요청한다. B단계 착수 전에 ① 주제 리서치 재실행(외부 검색광고 키 사용) ② `generate_post` 이음새 추가를 각각 별도로 승인받는다.
