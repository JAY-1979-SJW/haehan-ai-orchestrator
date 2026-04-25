# 영상 편집 큐 PoC (F-4S-11)

## 목적

F-4S-8 녹화 결과, F-4S-9 subtitle queue, F-4S-10 TTS queue를 연결해
최종 영상 편집 작업 큐(JSON/MD)를 생성한다.

실제 ffmpeg 실행, 영상 합성, 음성 합성, 업로드는 하지 않는다.

---

## 녹화/자막/TTS 큐와의 관계

```
F-4S-8 recording metadata
  └─ video_path   (.webm 실제 파일)
  └─ duration_seconds

F-4S-9 subtitle queue
  └─ subtitle_items[*].srt_path
  └─ subtitle_items[*].vtt_path
  └─ subtitle_items[*].duration_seconds

F-4S-10 TTS queue
  └─ tts_items[*].expected_audio_path  (.wav 계획 경로)
  └─ tts_items[*].voice_profile

→ edit_queue JSON
  └─ edit_items[*].timeline[]         (video/subtitle/voiceover 레이어)
  └─ edit_items[*].edit_steps[]       (계획 단계)
  └─ edit_items[*].output_video_path  (계획 경로 — 파일 미생성)
```

---

## 실제 ffmpeg 실행과의 차이

| 항목 | F-4S-11 PoC | 실제 ffmpeg worker |
|------|-------------|-------------------|
| ffmpeg 실행 | 없음 | subprocess / shell |
| 영상 합성 | 없음 | .mp4 생성 |
| 자막 내장 | 없음 | -vf subtitles= |
| 음성 혼합 | 없음 | -i audio.wav -map |
| 출력 파일 | 계획 경로만 | 실제 .mp4 |

---

## 편집 timeline 구조

```json
[
  {
    "layer": "video",
    "start_seconds": 0,
    "end_seconds": 30,
    "asset": "runs/video/smoke/recordings/.../test.webm",
    "planned_only": false
  },
  {
    "layer": "subtitle",
    "start_seconds": 0,
    "end_seconds": 30,
    "asset": "runs/video/subtitles/subtitle_001.srt",
    "planned_only": false
  },
  {
    "layer": "voiceover",
    "start_seconds": 0,
    "end_seconds": 30,
    "asset": "runs/video/tts/audio/tts_001.wav",
    "planned_only": true
  }
]
```

---

## 허용 / 금지 edit_steps

| 허용 step_type | 설명 |
|----------------|------|
| `validate_assets` | 계획 파일 확인 |
| `compose_video_plan` | 레이어 합성 계획 생성 |
| `attach_subtitles` | SRT/VTT 자막 레이어 계획 |
| `attach_voiceover_plan` | TTS 음성 레이어 계획 (planned_only) |
| `export_plan` | 출력 경로/포맷 계획 |

| 금지 step_type |
|---------------|
| `ffmpeg_run` / `render_video` / `upload` / `publish` / `delete` / `oauth` / `browser` |

---

## CLI 사용 예시

```bash
# fixture 기반 (전체 파이프라인 내부 생성)
python scripts/build_video_edit_queue.py \
  --fixture samples/content_research_fixture.json \
  --max-items 3 --json

# subtitle queue + tts queue 직접 입력
python scripts/build_video_edit_queue.py \
  --subtitle-queue runs/video/subtitles/subtitle_queue_YYYYMMDD.json \
  --tts-queue runs/video/tts/tts_queue_YYYYMMDD.json \
  --json

# recording metadata 포함
python scripts/build_video_edit_queue.py \
  --subtitle-queue runs/video/subtitles/subtitle_queue_YYYYMMDD.json \
  --tts-queue runs/video/tts/tts_queue_YYYYMMDD.json \
  --metadata runs/video/smoke/recordings/.../metadata.json \
  --json
```

---

## 향후 확장

1. **실제 ffmpeg worker** — edit_queue의 timeline을 읽어 subprocess로 ffmpeg 실행 (사람 검수 후 별도 단계)
2. **TTS 음성 파일 연결** — `expected_audio_path`에 실제 .wav 생성 후 voiceover 레이어 연결
3. **LTX 생성 영상 혼합** — AI 생성 영상 + 내부 웹 녹화 영상 혼합 편집 계획
4. **YouTube 업로드** — OAuth + 사람 검수 승인 후 별도 단계로 분리
