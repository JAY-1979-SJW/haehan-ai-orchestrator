---
name: youtube-video-analyze
description: YouTube 영상 URL/ID 하나를 심층 분석(전사·키프레임·리포트)할 때 사용. "영상 분석해", "이 영상 분석해줘", "유튜브 영상 봐줘" 같은 요청에 사용. WebFetch/oEmbed로는 제목·채널만 나오고 내용 분석이 안 되므로, 자막/음성 전사와 화면 프레임 판독까지 필요하면 이 도구(apps/youtube-analyzer-standalone)를 우선 사용하고 새로 짜지 않는다.
---

# YouTube 영상 심층 분석

## 언제 쓰는가
사용자가 특정 영상 URL을 주고 "분석해줘"라고 하면, WebFetch(oEmbed)로는
제목/채널명만 얻을 수 있고 실제 내용 분석은 불가능하다. 이럴 때 매번 새
스크립트를 짜지 말고 `apps/youtube-analyzer-standalone`(전사+키프레임+리포트
파이프라인, 기 구현·검증됨)을 사용한다.

키워드 검색으로 여러 영상을 스크리닝하는 것도 같은 도구의 1단계 기능
(`search`)이므로 함께 사용 가능.

## 실행 순서

```bash
cd apps/youtube-analyzer-standalone

# 1) 전사 + 키프레임 추출을 한 번에
python cli.py analyze <video_id_or_url>
# 내부적으로 transcribe + frames 를 순차 실행함
# 결과: data/transcripts/<id>.json, data/frames/<id>/frame_*.jpg
```

2. **Claude가 각 프레임을 Read 도구로 직접 본다** — 유료 비전 API를 쓰지
   않는다(프로젝트 정책: 외부 유료 AI API는 사용자 사전 승인 필요, GPT
   비전 관련 CLAUDE.md 조항 참조). 각 프레임을 보고
   `data/frames/<id>/descriptions.json` 에 `{"0": "설명", "1": "설명", ...}`
   형태로 작성한다.

3. **리포트 생성**
```bash
python cli.py report <video_id> --descriptions data/frames/<video_id>/descriptions.json
# → data/reports/<video_id>.md
```

4. **"왜 잘 됐는가" 섹션은 리포트 생성 후 Claude가 수동으로 채운다** —
   재실행 시 이 섹션은 플레이스홀더로 초기화되므로, 최종 분석 결과는
   사용자에게 직접 요약해서 전달하거나 별도 보관한다.

## URL 입력 지원
`transcribe`/`frames`/`report`/`analyze` 모두 video_id 뿐 아니라 YouTube
URL(watch/youtu.be/shorts)을 그대로 받는다 (`core/url_parser.py`). URL에서
ID를 미리 뽑아낼 필요 없음.

## 알려진 한계 (재확인 없이 신뢰)
- 게시 30일 초과 영상이 섞이면 VPH가 왜곡되어 자동으로 조회수 정렬 전환
- 배경음악이 강하면 Whisper VAD가 음성을 걸러 전사가 비거나 품질 저하
  (자막 있는 영상 우선 선택 권장)
- 장면전환 감지 실패 시 시간 균등 6분할 샘플링으로 폴백

## 설치 확인 (최초 1회)
```bash
cd apps/youtube-analyzer-standalone
pip install -r requirements.txt
# .env 에 YOUTUBE_API_KEY 필요 (Google Cloud Console 발급) — search 명령에만 필수
```

## 관련
- `apps/youtube-analyzer-standalone/README.md` — 전체 단계 설명
- `data/reports/*.md` — 기존 분석 리포트 예시 (형식 참고)
- [[channel-youtube-worklog]] — 유튜브 채널 운영 작업기록과는 별개(이건 "타 영상 리서치·분석" 용도)
