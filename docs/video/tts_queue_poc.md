# TTS 큐 PoC (F-4S-10)

## 목적

F-4S-9 subtitle queue의 segment 텍스트를 기반으로
TTS 음성 생성 계획 큐(JSON/MD)를 만든다.

실제 TTS API 호출이나 음성 파일 생성은 하지 않는다.
어떤 문장을 어떤 목소리/속도/톤/구간으로 읽을지 정의하는 큐 생성까지만 수행한다.

---

## subtitle queue와 TTS queue 관계

```
F-4S-9 subtitle queue JSON
  └─ subtitle_items[*].segments[*].text       → TTS 읽을 텍스트
  └─ subtitle_items[*].segments[*].start/end  → 음성 시작/끝 (초)
  └─ subtitle_items[*].segments[*].source     → tone 결정
  └─ subtitle_items[*].review_required        → 검수 플래그 전파

→ tts_queue JSON
  └─ tts_items[*].segments[*].text            (normalize_tts_text 처리)
  └─ tts_items[*].segments[*].voice_profile
  └─ tts_items[*].segments[*].speed
  └─ tts_items[*].segments[*].tone
  └─ tts_items[*].expected_audio_path         (계획 경로 — 파일 미생성)
```

---

## 실제 TTS 호출과의 차이

| 항목 | F-4S-10 PoC | 실제 TTS |
|------|-------------|---------|
| API 호출 | 없음 | ElevenLabs / Google TTS 등 |
| 음성 파일 | 미생성 (계획 경로만) | .wav / .mp3 생성 |
| 비용 | 없음 | 문자당/초당 과금 |
| 싱크 | subtitle 시간 기준 추정 | 실제 음성 길이 |

---

## voice_profile 정의

| 프로필 | 설명 |
|--------|------|
| `ko_male_neutral` | 한국어 남성, 중립 톤 (기본값) |
| `ko_female_neutral` | 한국어 여성, 중립 톤 |
| `ko_male_energetic` | 한국어 남성, 활기찬 톤 |
| `ko_female_friendly` | 한국어 여성, 친근한 톤 |

---

## tone 결정 규칙

| segment source | tone |
|---------------|------|
| hook | informative |
| scene_caption | calm |
| subtitle_point | calm |
| narration_point | informative |
| (기타) | calm |

---

## 출력 JSON 구조

```json
{
  "tts_id": "tts_001",
  "subtitle_id": "subtitle_001",
  "title": "소방공사 비용 5가지 핵심 체크리스트",
  "voice_profile": "ko_male_neutral",
  "segments_count": 4,
  "expected_audio_path": "runs/video/tts/audio/tts_001.wav",
  "review_required": true,
  "segments": [
    {
      "segment_id": "tts_001_001",
      "start_seconds": 0.0,
      "end_seconds": 4.5,
      "text": "소방공사 견적을 받기 전에 반드시 확인해야 하는 5가지 항목과 비용 산정.",
      "voice_profile": "ko_male_neutral",
      "speed": 1.0,
      "tone": "informative",
      "review_required": true
    }
  ]
}
```

---

## 검수 필요 항목

`review_required=true` 조건:
- 법령 / 단가 / 안전기준 / 규정 / 시행령 / 고시 / 허가 / 인증
- 보장 / 확정 / 반드시 / 절대

`warnings` 표시 조건:
- 과장 광고: 100%, 무조건, 완전히, 보장됩니다 등
- secret-like 키워드: api_key, secret, password, token 등

---

## CLI 사용 예시

```bash
# fixture 기반
python scripts/build_tts_queue.py \
  --fixture samples/content_research_fixture.json \
  --voice-profile ko_male_neutral --max-items 3 --json

# subtitle queue 기반
python scripts/build_tts_queue.py \
  --subtitle-queue runs/video/subtitles/subtitle_queue_YYYYMMDD_HHMMSS.json \
  --voice-profile ko_female_neutral --json

# SRT 단독
python scripts/build_tts_queue.py \
  --srt runs/video/subtitles/subtitle_001.srt --json

# VTT 단독
python scripts/build_tts_queue.py \
  --vtt runs/video/subtitles/subtitle_001.vtt --json
```

---

## 향후 확장

1. **실제 TTS API 연동** — 사람 검수 승인 후 ElevenLabs / Google TTS 등 호출 (별도 단계)
2. **음성 파일 생성** — `expected_audio_path`에 실제 .wav 저장
3. **영상 편집 큐 연결** — 녹화 영상 + TTS 음성 + SRT → 편집 큐 생성
4. **자막 싱크 보정** — 실제 음성 길이 → SRT/VTT 타이밍 재조정
5. **YouTube 업로드** — OAuth + 사람 검수 승인 후 별도 단계로 분리
