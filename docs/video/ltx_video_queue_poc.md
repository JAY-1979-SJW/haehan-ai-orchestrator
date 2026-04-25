# F-4S-6 — LTX 영상 제작 큐 PoC

## 1. 목적

F-4S-5 에서 생성한 콘텐츠 조사 리포트(`ltx_video_briefs`) 또는 fixture 분석 결과를 입력으로 받아,
LTX 영상 제작 지시서(큐) 를 JSON / Markdown 형태로 생성한다.

이번 단계는 **지시서 생성까지만** 수행한다.

명시적 비-수행 항목:
- 실제 LTX API 호출
- 실제 영상 생성 / 렌더링 / 업로드
- 브라우저 자동화 / Playwright / requests 신규 호출
- OAuth / 쿠키 / 세션 접근
- 네이버 / 유튜브 write 액션 (댓글 / 가입 / 글쓰기 / 업로드 / 수정 / 삭제)
- API key / client_secret 의 큐/리포트/로그 노출

## 2. 입력 데이터

다음 두 가지 입력 중 하나를 선택한다.

### 2.1 content report JSON
- F-4S-5 `scripts/research_content.py` 가 생성한 리포트 JSON.
- 최상위 키 `ltx_video_briefs` 가 사용된다.
- 기타 키(`items`, `analysis`, `summary` 등)는 무시한다.

### 2.2 fixture JSON
- `samples/content_research_fixture.json` 등.
- F-4S-5 `report_builder.load_fixture_items` + `build_ltx_video_briefs` 로 brief 를 우선 생성한 뒤
  큐 빌더가 이 brief 리스트를 사용한다.

`--content-report` 와 `--fixture` 는 동시에 사용할 수 없다.
둘 다 누락되면 CLI 는 즉시 실패한다.

## 3. 출력 구조

### 3.1 큐 item JSON 스키마

```json
{
  "queue_id": "video_001",
  "status": "draft",
  "title": "...",
  "hook": "...",
  "duration_type": "short|long",
  "target_platform": "youtube_short|youtube_long|naver_blog|cafe_post",
  "scene_plan": [
    {
      "scene_no": 1,
      "purpose": "문제 제기",
      "visual_direction": "...",
      "caption": "...",
      "narration": "..."
    }
  ],
  "subtitle_points": ["..."],
  "source_basis": [
    {"platform": "...", "source_type": "...", "url": "...", "title": "..."}
  ],
  "ltx_prompt": "(영상 제작 지시서 텍스트)",
  "risk_notes": ["..."],
  "review_required": true,
  "score": 0.0
}
```

### 3.2 출력 파일

`runs/video/` 디렉토리(또는 `--out-dir` 지정 경로)에 다음 두 파일을 생성한다.

- `video_queue_YYYYMMDD_HHMMSS.json` — 큐 전체 + 메타.
- `video_queue_YYYYMMDD_HHMMSS.md` — 사람이 검토하기 쉬운 Markdown 리포트.

## 4. CLI 사용 예시

```bash
# fixture 기반 smoke
python scripts/build_video_queue.py \
    --fixture samples/content_research_fixture.json \
    --max-items 5 \
    --duration short \
    --json

# 실제 F-4S-5 리포트 기반
python scripts/build_video_queue.py \
    --content-report runs/content/content_research_20260420_120000.json \
    --max-items 3 \
    --duration long
```

stdout 출력 형태(`--json` 미사용 시):

```
source: fixture:content_research_fixture.json
queue_items_count: 5
max_items: 5
default_duration_type: short
review_required_count: 5
  - <title 1>
  - <title 2>
  ...
json: runs/video/video_queue_YYYYMMDD_HHMMSS.json
md:   runs/video/video_queue_YYYYMMDD_HHMMSS.md
```

## 5. LTX 실제 호출과의 차이

이 PoC 는 **지시서 텍스트(`ltx_prompt`) 까지만 작성** 하며, 다음을 절대 포함/실행하지 않는다.

- LTX REST/SDK 호출
- LTX 영상 다운로드 / 저장 / 렌더링
- 영상 업로드 (YouTube / 네이버 / 카페)
- 자동 댓글 / 가입 / 글쓰기

`ltx_prompt` 는 사람이 읽고 LTX 콘솔/별도 도구에서 수동 활용하거나,
후속 PoC(승인형 단계)에서 LTX 키 등록 후 별도 호출 단계로 넘어가는 입력 자료다.

## 6. 검수 필요 항목

큐 item 의 `review_required=True` 는 PoC 단계에서 **항상 True** 로 설정된다.
다음 신호가 감지되면 `risk_notes` 에 명시적 검수 사유가 추가된다.

- 법령 / 단가 / 안전 키워드 (`법`, `법령`, `기준`, `규정`, `시행령`, `비용`, `견적`, `단가`, `안전`, ...)
  → "법령/단가/안전 표현 감지 — 최종 검수 필요"
- 광고/비방/단정 표현 (`최고`, `100%`, `보장`, `사기`, `최악`, ...)
  → "과장/비방 표현 후보 감지 — 표현 순화 필요"
- 출처 누락 / URL 누락
  → "출처 누락 — 인용 reference 확보 후 사용 권장"

`review_required=False` 로 강제 변경하는 자동 흐름은 제공하지 않는다.
영상화/렌더링은 사람이 직접 큐 item 을 검토 → 외부에서 진행한다.

## 7. 향후 확장

- LTX API 연결 (별도 승인 + 키 등록 후 별도 PoC)
- 웹 자동녹화 / 화면 녹화 큐 연결
- 자막 생성기(STT 기반) 연결
- 영상 업로드는 모든 단계가 사람의 명시적 승인을 거쳐야 함 (자동 업로드 금지)
- 본 큐 item 의 `status` 필드 워크플로 (`draft → ready_for_render → rendered → reviewed → archived`)
