# 웹 자동녹화 worker dry-run (F-4S-8a)

## 목적

F-4S-7에서 생성한 `web_recording_queue` JSON을 실제 녹화 worker가 처리할 수 있는
구조로 만든다. **이번 단계(F-4S-8a)는 dry-run 전용이다.**

- recording queue 로드 및 구조 검증
- 허용/금지 step 분류
- 실행계획(execution plan) JSON + Markdown 리포트 생성
- 출력 파일 경로(video/metadata) 는 계획 문자열만 기록 — 실제 파일 생성 없음

실제 브라우저 실행, 화면 녹화, mp4 생성은 다음 단계(F-4S-8b)로 분리되어 있다.

---

## F-4S-7 recording queue와의 관계

| 단계 | 역할 |
|------|------|
| F-4S-7 (`recording_queue.py`, `build_web_recording_queue.py`) | recording queue JSON 생성 (지시서 큐) |
| **F-4S-8a (`recording_worker.py`, `run_web_recording_worker.py`)** | **queue 검증 + dry-run execution plan 생성** |
| F-4S-8b (미구현) | 실제 브라우저 실행 + 화면 녹화 |

F-4S-8a는 F-4S-7의 output을 그대로 입력으로 받는다.

---

## 이번 단계가 dry-run인 이유

- 실제 브라우저 실행은 승인 없이 수행하면 외부 사이트 접근이나 의도치 않은 상호작용이 발생할 수 있다.
- dry-run 단계에서 forbidden step 검출, target_url 누락, 외부 플랫폼 경고를 먼저 확인해야 한다.
- 사람이 execution plan을 검수한 후 F-4S-8b에서 실제 녹화를 수행한다.
- `dry_run=False`를 호출하면 `NotImplementedError`가 발생한다.

---

## 허용 step / 금지 step

**허용 step:**
- `open_url` — 대상 URL 열기 (계획만 기록, 실제 goto 없음)
- `wait` — 로드 대기
- `capture_scene` — 화면 캡처 계획
- `scroll_plan` — 스크롤 계획
- `overlay_caption` — 자막 오버레이 계획

**금지 step (blocked_steps에 기록):**
- `click`, `fill`, `type`, `press` — 자동 입력
- `submit`, `upload`, `download` — 데이터 전송
- `login`, `purchase`, `comment`, `post` — 인증/거래/게시 행위
- `hover`, `drag`, `select_option`, `set_storage`, `set_cookie` — 기타 상호작용

---

## 출력 JSON 구조

### execution plan (runs/video/worker/web_recording_worker_YYYYMMDD_HHMMSS.json)

```json
{
  "generated_at": "2026-04-26T00:00:00Z",
  "dry_run": true,
  "output_dir": "runs/video/worker",
  "queue_errors": [],
  "total_items": 5,
  "validated_count": 3,
  "blocked_count": 2,
  "warning_count": 2,
  "allowed_step_types": ["open_url", "wait", "capture_scene", "scroll_plan", "overlay_caption"],
  "forbidden_step_types": ["click", "fill", "type", "press", "submit", "upload", ...],
  "items": [
    {
      "recording_id": "recording_001",
      "source_queue_id": "video_001",
      "title": "...",
      "status": "validated",
      "would_open_url": "http://localhost:3000",
      "would_record_seconds": 30,
      "viewport": {"name": "desktop", "width": 1440, "height": 900},
      "steps_count": 6,
      "allowed_steps": [{"step_no": 1, "type": "open_url"}, ...],
      "blocked_steps": [],
      "output_video_path": "runs/video/worker/recordings/recording_001.mp4",
      "output_metadata_path": "runs/video/worker/recordings/recording_001.json",
      "warnings": [],
      "errors": [],
      "dry_run": true
    }
  ],
  "notes": [...]
}
```

### item status 분류

| status | 조건 |
|--------|------|
| `validated` | target_url 존재 + forbidden step 없음 + errors 없음 |
| `blocked` | target_url 누락, 또는 forbidden step 있음, 또는 구조 오류 |

### warnings 종류

| warning | 의미 |
|---------|------|
| `target_url_missing` | target_url이 비어 있음 → blocked |
| `target_url_invalid` | URL 형식 이상 |
| `external_target_review_required` | youtube.com, naver.com 등 외부 플랫폼 → 수동 검수 필요 |

---

## CLI 사용 예시

**기본 (dry-run, 전체 items):**
```bash
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --dry-run
```

**JSON 요약 출력:**
```bash
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --dry-run --json
```

**최대 3개 items만 처리:**
```bash
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --dry-run --max-items 3 --out-dir runs/video/worker
```

**F-4S-7 queue를 먼저 생성하고 worker 실행:**
```bash
# 1. queue 생성
python scripts/build_web_recording_queue.py \
  --fixture samples/content_research_fixture.json \
  --base-url http://localhost:3000 \
  --max-items 3 --viewport desktop --json

# 2. worker dry-run
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --dry-run --json
```

**결과 파일 위치:**
```
runs/video/worker/web_recording_worker_YYYYMMDD_HHMMSS.json
runs/video/worker/web_recording_worker_YYYYMMDD_HHMMSS.md
```

---

## 다음 단계 F-4S-8b에서 실제 브라우저 실행을 분리하는 이유

F-4S-8a의 dry-run은 계획 검증이고, 실제 실행은 별도 승인 절차가 필요하다.

- 실수로 외부 사이트에 접속하거나 자동 입력이 실행되는 것을 방지
- dry-run 리포트를 사람이 먼저 검수한 후, validated item만 선별하여 실행
- `dry_run=False` 경로는 F-4S-8b에서만 구현

---

## 실제 녹화 단계의 승인 조건

F-4S-8b로 진행하기 위해서는 아래 조건을 모두 충족해야 한다:

1. **내부 URL 우선** — `http://localhost` 또는 대표님이 직접 제작한 웹페이지 URL
2. **로그인 불필요 화면 우선** — 인증 없이 열 수 있는 공개 페이지
3. **click/fill/type 없음** — recording_steps에 forbidden step이 포함되지 않음
4. **저장 경로 고정** — `runs/video/recordings/` 이하 지정 경로
5. **사람이 결과 검수** — dry-run 리포트를 확인하고 명시적으로 승인

---

## 보안 원칙

- Playwright / Selenium import 없음 (lazy placeholder도 실제 실행 금지)
- `page.goto`, `browser.launch`, `context.new_page` 코드 없음
- API key / client_secret / cookie / session / storage_state 접근/기록 금지
- `.env` 파일 커밋 금지
- 실제 mp4 파일 생성 없음 — output_video_path는 계획 문자열
