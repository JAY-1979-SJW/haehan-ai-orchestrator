# 렌더 계획 PoC (F-4S-12)

## 목적

F-4S-11 edit_queue JSON을 입력받아 ffmpeg 실행 계획(render_plan JSON/MD)을 생성한다.

실제 ffmpeg 실행, 영상 합성, 파일 변환, 업로드는 하지 않는다.

---

## F-4S-11 edit_queue와의 관계

```
F-4S-11 edit_queue
  └─ edit_items[*].source_video_path
  └─ edit_items[*].subtitle_srt_path
  └─ edit_items[*].tts_expected_audio_path
  └─ edit_items[*].output_video_path

→ render_plan JSON
  └─ render_items[*].command_plan      (ffmpeg 명령 계획 — 실행 금지)
  └─ render_items[*].status            (planned | blocked)
  └─ render_items[*].assets            (파일 존재 여부)
```

---

## 실제 ffmpeg worker와의 차이

| 항목 | F-4S-12 PoC | 실제 ffmpeg worker |
|------|-------------|-------------------|
| ffmpeg 실행 | 없음 (shutil.which 확인만) | subprocess 실행 |
| 영상 합성 | 없음 | .mp4 생성 |
| 자막 내장 | 없음 | -vf subtitles= |
| 음성 혼합 | 없음 | -i audio.wav -map |
| shell=True | 금지 | 금지 |
| 출력 파일 | 계획만 | 실제 .mp4 |

---

## command_plan 구조

```json
{
  "program": "ffmpeg",
  "args": ["-i", "input.webm", "-vf", "subtitles=sub.srt", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", "output.mp4"],
  "display": "ffmpeg -i input.webm ...",
  "shell": false,
  "planned_only": true,
  "warnings": []
}
```

---

## 렌더 상태

| status | 조건 |
|--------|------|
| `planned` | 기본 상태 (자산 누락 허용) |
| `blocked` | `--require-assets` 옵션 사용 + 자산 누락 |

---

## CLI 사용 예시

```bash
# edit_queue 파일 직접 입력
python scripts/build_render_plan.py \
  --edit-queue runs/video/edits/video_edit_queue_YYYYMMDD.json \
  --json

# 자산 누락 시 blocked 처리
python scripts/build_render_plan.py \
  --edit-queue runs/video/edits/video_edit_queue_YYYYMMDD.json \
  --require-assets --json

# 최대 2개만 처리
python scripts/build_render_plan.py \
  --edit-queue runs/video/edits/video_edit_queue_YYYYMMDD.json \
  --max-items 2
```

---

## 향후 확장

1. **F-4S-13 restricted ffmpeg worker** — 사람 검수 승인 후 render_plan의 command_plan을 읽어 실제 subprocess ffmpeg 실행
2. **자산 연결** — 실제 .webm 녹화 + .wav TTS 생성 후 assets 상태 업데이트
3. **YouTube 업로드** — OAuth + 사람 검수 승인 후 별도 단계로 분리
