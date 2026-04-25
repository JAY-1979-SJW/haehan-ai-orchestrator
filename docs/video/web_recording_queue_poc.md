# F-4S-7 — 웹 자동녹화 큐 PoC

## 1. 목적

F-4S-6 의 LTX 영상 제작 큐(`video_queue.json`) 를 입력으로 받아,
대표님이 만든 웹 화면 / 내부 대시보드를 자동녹화하기 위한 **녹화 지시서 큐(recording queue)** 를
JSON / Markdown 형태로 생성한다.

이번 단계는 **지시서 생성까지만** 수행한다.

명시적 비-수행 항목:
- 실제 브라우저 실행 (Playwright / Selenium / Puppeteer 등)
- 실제 화면 녹화 / 비디오 캡처
- 실제 사이트 로그인
- click / fill / type / press / submit / upload 등 자동 입력 액션
- cookie / session / storage_state 접근
- 네이버 / 유튜브 업로드, 댓글, 가입, 글쓰기
- LTX API 호출
- OAuth 구현
- API key / client_secret 의 큐/리포트/로그 노출

## 2. LTX 영상 큐와의 관계

```
[F-4S-5 content research]
   └─▶ ltx_video_briefs
          └─▶ [F-4S-6 video_queue]   ← LTX 제작 지시서 (장면/자막/대본 수준)
                 └─▶ [F-4S-7 recording_queue]   ← 웹 화면 녹화 지시서 (이번 단계)
                        └─▶ (미래) Playwright 녹화 worker → LTX 영상 생성 → 사람 검수 → 업로드
```

`video_queue` 는 "어떤 메시지를 어떤 장면 구성으로 영상화할지" 를 담는 **영상 제작 지시서** 다.
`recording_queue` 는 그 중에서 **"어떤 웹 화면을 어떤 viewport / 어떤 순서로 녹화할지"** 를
담는 **녹화 작업 지시서** 다.

## 3. 이번 단계에서 실제 녹화를 하지 않는 이유

- 실제 녹화 = 브라우저 자동 실행 = 인증/세션/쿠키/스토리지 접근 + 외부 사이트 트래픽 발생.
- F-4S 시리즈 안전 원칙(read-only, 사람 검수, 업로드/댓글 금지) 을 보존하기 위해
  **녹화 worker 는 별도 승인형 단계**로 분리한다.
- 이번 PoC 는 "큐 항목 형태가 worker 가 실행하기에 충분한가" 를 검증하는 단계다.

## 4. 입력 파일 형식

다음 셋 중 하나만 사용 (동시 사용 불가).

### 4.1 `--video-queue <path>`
- F-4S-6 `scripts/build_video_queue.py` 가 생성한 video_queue JSON.
- 최상위 `queue` 키(또는 `ltx_video_briefs`)를 후보로 사용.

### 4.2 `--content-report <path>`
- F-4S-5 `scripts/research_content.py` 가 생성한 content research 리포트 JSON.
- 내부에서 F-4S-6 `build_video_queue` 를 한 번 호출해 video queue 로 변환한 뒤 사용.

### 4.3 `--fixture <path>`
- `samples/content_research_fixture.json` 같은 fixture.
- 내부에서 F-4S-5 분석 → F-4S-6 video queue → F-4S-7 recording queue 순으로 흐름.

## 5. 출력 구조

### 5.1 recording queue item JSON 스키마

```json
{
  "recording_id": "recording_001",
  "source_queue_id": "video_001",
  "status": "draft",
  "title": "...",
  "target_url": "https://internal.example/page-a",
  "source_basis_url": "https://example.com/blog/x",
  "viewport": {"name": "desktop", "width": 1440, "height": 900},
  "duration_seconds": 30,
  "duration_type": "short",
  "recording_steps": [
    {"step_no": 1, "type": "open_url", "description": "...", "url": "...", "wait_seconds": 3},
    {"step_no": 2, "type": "wait", "description": "...", "wait_seconds": 2},
    {"step_no": 3, "type": "capture_scene", "description": "...", "duration_seconds": 8, "caption": "..."},
    {"step_no": 4, "type": "scroll_plan", "description": "...", "direction": "down", "amount_px": 600, "wait_seconds": 1},
    {"step_no": 5, "type": "overlay_caption", "description": "...", "captions": ["..."]}
  ],
  "subtitle_points": ["..."],
  "narration_points": ["..."],
  "editing_notes": ["..."],
  "risk_notes": ["..."],
  "review_required": true,
  "source_basis": [{"platform": "...", "source_type": "...", "url": "...", "title": "..."}]
}
```

### 5.2 출력 파일

`runs/video/` (또는 `--out-dir` 지정 경로) 에 다음 두 파일을 생성한다.

- `web_recording_queue_YYYYMMDD_HHMMSS.json`
- `web_recording_queue_YYYYMMDD_HHMMSS.md`

## 6. CLI 사용 예시

```bash
# fixture 기반 smoke
python scripts/build_web_recording_queue.py \
    --fixture samples/content_research_fixture.json \
    --base-url http://localhost:3000 \
    --max-items 5 --viewport desktop --json

# F-4S-6 video_queue 기반
python scripts/build_web_recording_queue.py \
    --video-queue runs/video/video_queue_20260420_120000.json \
    --base-url http://localhost:3000 --max-items 3

# F-4S-5 content_report 기반 (F-4S-6 단계 내부 수행 후 녹화 큐 생성)
python scripts/build_web_recording_queue.py \
    --content-report runs/content/content_research_20260420_120000.json \
    --base-url http://localhost:3000
```

## 7. 허용 action / 금지 action

### 7.1 허용 step type

- `open_url` — 대상 URL 열기 안내 (worker 단계에서만 실제 navigation 수행)
- `wait` — 명시적 대기
- `capture_scene` — 화면 캡처/녹화 안내 (worker 단계에서 실행)
- `scroll_plan` — 스크롤 안내 (worker 단계에서 실행)
- `overlay_caption` — 후처리 자막 오버레이 안내

### 7.2 금지 step type (큐에 절대 포함되지 않음)

`click`, `fill`, `type`, `press`, `login`, `submit`, `upload`, `hover`, `drag`,
`select_option`, `set_storage`, `set_cookie` 등.

이는 자동 입력 / 자동 인증 / 자동 업로드 / 자동 폼 제출을 모두 금지하기 위한 정책이다.
필요 시 사람이 사전 인증한 상태에서 worker 를 수동 실행하는 방식만 허용한다.

### 7.3 외부 플랫폼 / 로그인 페이지 처리

- 유튜브, 네이버, 인스타 등 외부 플랫폼 URL 은 자동 녹화 대상에서 제외 권장 →
  `risk_notes` 에 `external_target` 경고 추가.
- URL 에 `login`, `signin`, `auth`, `oauth`, `mypage`, `회원`, `로그인` 등 패턴 포함 시 →
  `risk_notes` 에 `login_required — 수동 인증 필요 또는 자동 녹화 대상에서 제외` 경고 추가.
- `target_url` 결정 불가 → `risk_notes` 에 `target_url_missing — 수동 지정 필요` 경고 추가.

## 8. 검수 필요 항목 (review_required)

PoC 단계에서는 항상 `review_required=True` 로 설정한다. 다음 신호 시 `risk_notes` 에 사유가 추가된다.

- target_url 미지정
- 외부 플랫폼 URL
- 로그인 필수 패턴 URL
- source video queue 의 `review_required=True`

## 9. 향후 확장

- 실제 Playwright (또는 동급) 녹화 worker — 별도 승인 + 키 등록 + 사람 인증 후 실행
- 자막 생성기 (STT / 시점 동기화) 연결
- TTS 내레이션 생성 연결
- LTX 영상 생성 연결 (별도 LTX 키 등록 후)
- YouTube / 네이버 업로드는 OAuth + 사람 검수 + 별도 승인형 단계
- 큐 item 워크플로: `draft → human_reviewed → ready_to_record → recorded → rendered → published`
