# subtitle queue PoC (F-4S-9)

## 목적

F-4S-6 video queue의 `scene_plan` / `subtitle_points` / `hook`과
F-4S-8 recording metadata의 `duration_seconds`를 연결해
영상별 SRT/VTT 자막 초안을 자동 생성한다.

실제 STT/TTS/영상 편집/업로드는 하지 않는다.

---

## 입력 파일 관계

```
F-4S-6 video_queue JSON
  └─ queue[*].scene_plan[].caption / narration
  └─ queue[*].subtitle_points[]
  └─ queue[*].hook
  └─ queue[*].duration_type  ("short"=30s / "long"=60s / "medium"=45s)

F-4S-8 recording metadata JSON  (선택)
  └─ duration_seconds  (실제 녹화 길이 → segment 시간 보정)
  └─ recording_id       (video queue item 과 연결)

→ subtitle_queue JSON  (segment 목록 + review 플래그)
→ subtitle_001.srt / subtitle_001.vtt
→ subtitle_queue_YYYYMMDD_HHMMSS.md
```

---

## SRT/VTT 출력 구조

### SRT 예시

```
1
00:00:00,000 --> 00:00:04,500
소방공사 견적을 받기 전에 반드시
확인해야 하는 5가지 항목과 비용 산정…

2
00:00:04,500 --> 00:00:09,000
소방공사 현황
```

### VTT 예시

```
WEBVTT

00:00:00.000 --> 00:00:04.500
소방공사 견적을 받기 전에 반드시
확인해야 하는 5가지 항목과 비용 산정…
```

---

## segment 시간 배분 원칙

- `duration_type` → 총 길이: `short`=30s, `long`=60s, `medium`=45s
- recording metadata의 `duration_seconds`가 있으면 우선 적용
- 텍스트 수에 따라 균등 분배: 최소 2.5초 / 최대 4.5초 per segment
- 마지막 segment 는 총 길이 끝까지

---

## review_required 조건

다음 키워드가 segment 텍스트에 포함되면 `review_required=true`:

- 법령, 단가, 안전기준, 법적, 기준치, 규정, 조항, 시행령
- 고시, 허가, 인증, 보장, 확정, 반드시, 절대

---

## 실제 STT/TTS와의 차이

| 항목 | F-4S-9 PoC | 실제 STT/TTS |
|------|-----------|-------------|
| 자막 텍스트 출처 | scene_plan / subtitle_points | 실제 음성 → Whisper 등 |
| 타이밍 | 균등 분배 추정 | 실제 음성 구간 |
| 파일 생성 | SRT/VTT 초안 | 싱크된 SRT/VTT |
| 비용 | 없음 | STT API 비용 |

---

## CLI 사용 예시

```bash
# fixture 기반 (video queue 없어도 동작)
python scripts/build_subtitle_queue.py \
  --fixture samples/content_research_fixture.json \
  --max-items 3 --language ko --json

# video queue 기반
python scripts/build_subtitle_queue.py \
  --video-queue runs/video/video_queue_YYYYMMDD_HHMMSS.json \
  --max-items 5 --json

# recording metadata 보강
python scripts/build_subtitle_queue.py \
  --video-queue runs/video/video_queue_YYYYMMDD_HHMMSS.json \
  --worker-result runs/video/worker/web_recording_worker_YYYYMMDD_HHMMSS.json \
  --json
```

---

## 향후 확장

1. **TTS 큐 연결** — segment 텍스트 → TTS API → 음성 파일 생성 (별도 승인 단계)
2. **영상 합성/편집 큐** — 녹화 영상 + TTS 음성 + SRT → 편집 큐 생성
3. **YouTube 업로드** — OAuth + 사람 검수 승인 후 별도 단계로 분리
4. **STT 싱크** — 실제 녹화 음성 → Whisper → segment 타이밍 보정
