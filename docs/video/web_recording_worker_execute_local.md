# 웹 자동녹화 worker execute 모드 — 내부 URL 전용 (F-4S-8b)

## 개요

F-4S-8a의 dry-run worker를 확장해, **내부/localhost URL에 한해서** 실제 브라우저를
열고 화면 녹화를 수행한다.

- `--execute` 플래그 없으면 항상 dry-run (기본값 유지)
- `--execute` 명시 시: `validate_execute_allowed` 통과 후에만 녹화 시작
- 외부 사이트, 로그인 화면, click/fill/type/press 포함 queue는 실행 전 차단

---

## execute 모드가 허용하는 URL 규칙

### 기본 허용 host (추가 설정 불필요)
- `localhost`
- `127.0.0.1`
- `::1`

### 추가 허용 host (CLI 옵션)
```bash
--allow-host localhost --allow-host 192.168.1.10
```

### 기본 차단 host (변경 불가)
- `naver.com`, `youtube.com`, `youtu.be`
- `google.com`
- `hometax.go.kr`
- `instagram.com`, `facebook.com`, `tiktok.com`
- `kakao.com`, `daum.net`

### 로그인 URL 차단 (URL에 다음 패턴 포함 시 차단)
- `login`, `signin`, `sign-in`, `/auth/`, `/oauth`
- `회원`, `로그인`, `mypage`, `마이페이지`

---

## 금지 동작

execute 모드에서도 다음은 절대 금지:

| 금지 항목 | 이유 |
|-----------|------|
| `page.click / page.fill / page.type / page.press` | 자동 입력 |
| `page.keyboard / page.mouse` | 자동 입력 |
| `page.evaluate` | JS 실행 → 예측 불가 상호작용 |
| `page.route / intercept` | 네트워크 조작 |
| `storage_state / cookies / input_value` | 세션/인증 접근 |
| `download / upload` | 데이터 전송 |
| OAuth / 네이버·유튜브 업로드 / LTX API | 외부 서비스 write |

---

## 허용 브라우저 호출

```python
pw.chromium.launch(headless=True)
browser.new_context(
    viewport={...},
    record_video_dir=str(video_dir),
    record_video_size={...},
)
context.new_page()
page.goto(url, wait_until="networkidle", timeout=30000)
page.wait_for_timeout(ms)
page.screenshot(path=...)   # --screenshot 플래그 시만
context.close()
browser.close()
```

---

## step 실행 매핑 (execute 모드)

| step type | 동작 |
|-----------|------|
| `open_url` | `page.goto(url)` 로 처리 (한 번만) |
| `wait` | `page.wait_for_timeout(wait_seconds * 1000)` |
| `capture_scene` | `page.wait_for_timeout(duration * 1000)` + 선택적 screenshot |
| `scroll_plan` | 실제 스크롤 없음 — `wait_seconds` 만큼 대기 (scroll은 page.evaluate 필요 → 금지) |
| `overlay_caption` | 건너뜀 (post-process 단계) |

---

## 실제 녹화 파일 위치

```
runs/video/worker/recordings/<recording_id>/
  ├── <playwright_generated>.webm   ← Playwright가 생성
  └── <recording_id>_metadata.json  ← 메타데이터
```

metadata JSON 구조:
```json
{
  "recording_id": "recording_001",
  "source_queue_id": "video_001",
  "target_url": "http://localhost:3000",
  "viewport": {"name": "desktop", "width": 1440, "height": 900},
  "steps_executed": ["open_url", "wait", "capture_scene"],
  "video_dir": "runs/video/worker/recordings/recording_001",
  "video_path": "runs/video/worker/recordings/recording_001/xxx.webm",
  "screenshot_paths": [],
  "warnings": [],
  "started_at": "2026-04-26T00:00:00Z",
  "finished_at": "2026-04-26T00:00:30Z",
  "success": true
}
```

---

## CLI 사용 예시

**dry-run (기본, 브라우저 없음):**
```bash
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --dry-run --json
```

**execute — localhost 녹화 (헤드리스, 30초 상한):**
```bash
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --execute --allow-host localhost \
  --headless --max-record-seconds 30 --json
```

**execute — screenshot 포함:**
```bash
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --execute --allow-host localhost \
  --headless --screenshot --max-record-seconds 15
```

**최대 2개 item만 처리:**
```bash
python scripts/run_web_recording_worker.py \
  --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
  --execute --allow-host localhost --max-items 2
```

**결과 파일:**
```
runs/video/worker/web_recording_worker_YYYYMMDD_HHMMSS.json
runs/video/worker/web_recording_worker_YYYYMMDD_HHMMSS.md
runs/video/worker/recordings/<recording_id>/<recording_id>_metadata.json
runs/video/worker/recordings/<recording_id>/<playwright_video>.webm
```

---

## 사람이 검수해야 하는 항목

실제 녹화 실행 후 다음을 반드시 확인:

1. **video_path** — 파일이 실제로 존재하는지, 재생 가능한지
2. **steps_executed** — 의도한 step이 실행되었는지
3. **warnings** — `scroll_plan:actual_scroll_skipped` 등 경고 내용
4. **success** — `true`인지 확인
5. **target_url** — 의도한 내부 URL인지 재확인
6. 녹화 파일 내용이 의도한 페이지인지 시각 검수

---

## 외부 사이트/로그인 화면 처리 정책

- 외부 사이트(youtube.com, naver.com 등)는 `validate_execute_allowed`에서 차단
- 로그인 URL은 URL 패턴 감지로 차단
- `blocked_items`에 이유가 기록되어 사람이 확인 가능
- 외부 사이트 녹화가 필요한 경우 → **별도 승인 설계 완료 후 후속 단계에서 진행**

---

## 보안 원칙

- Playwright는 `execute_recording_item` 내부에서만 lazy import
- `page.click / page.fill / page.type / page.press` 코드 없음
- `page.keyboard / page.mouse / page.evaluate` 코드 없음
- `storage_state / cookies / input_value` 코드 없음
- API key / client_secret / .env 접근 없음
- OAuth / upload / write action 없음
- `.env` 커밋 금지

---

## 다음 단계 (F-4S-8c)

- 실제 localhost 녹화 1회 smoke 실행 및 결과 검수
- 녹화된 .webm을 mp4로 변환하는 후처리 단계 설계
- 자막 오버레이 적용 방법 결정
