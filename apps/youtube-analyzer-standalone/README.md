# YouTube 영상 분석 프로그램

키워드/카테고리 → 급상승·고조회수 영상 스크리닝 → (예정) 다운로드·전사·프레임 분석 → 리포트

## 참고 오픈소스
- guimatheus92/mcp-video-analyzer (전사/키프레임/OCR MCP 서버) — 2단계 이후 참고
- Xeron2000 계열 viral-shorts (VPH·참여율 스크리닝) — 이 프로젝트의 `core/viral_score.py` 로직 참고
- Ga0512/video-analysis (FFmpeg+Whisper+Vision 멀티모달 요약) — 2~3단계 참고

## 단계
- [x] 1단계: 키워드 검색 → 영상 목록 (VPH/참여율 정렬)
- [x] 2단계: yt-dlp 다운로드 + 자막/음성 전사 (`transcribe <video_id>`)
- [x] 3단계: 키프레임 추출 (`frames <video_id>`) — 이미지 자체의 장면 판독은 유료 비전 API 대신
      Claude Code 가 Read 도구로 프레임을 직접 보고 설명을 작성하는 방식
- [x] 4단계: 종합 마크다운 리포트 (`report <video_id> --descriptions <json>`)

## 리포트 생성 흐름 (4단계)
1. `python cli.py transcribe <video_id>` — 전사
2. `python cli.py frames <video_id>` — 키프레임 추출 (`data/frames/<video_id>/frame_*.jpg`)
3. Claude 가 각 프레임을 Read 로 직접 보고 `{"0": "설명", "1": "설명", ...}` 형태의
   descriptions JSON 작성 (`data/frames/<video_id>/descriptions.json`)
4. `python cli.py report <video_id> --descriptions data/frames/<video_id>/descriptions.json`
   → `data/reports/<video_id>.md` 생성
5. "이 영상이 왜 잘 됐는가" 섹션은 리포트 생성 후 Claude 가 수동으로 채워넣음
   (재실행 시 이 섹션은 플레이스홀더로 초기화되므로 최종본은 별도 보관)

## URL 입력 지원
`transcribe`/`frames`/`report`/`analyze` 는 video_id 뿐 아니라 YouTube URL(watch/youtu.be/shorts)도 받는다
(`core/url_parser.py`). `python cli.py analyze <url_or_id>` 로 transcribe+frames 를 한 번에 실행할 수 있음.

## 알려진 한계
- **VPH 지표**: 게시 30일 초과 영상이 섞이면 누적조회수 기반 VPH가 왜곡되어 자동으로 조회수 정렬로 전환됨.
- **배경음악이 강한 영상의 Whisper 정확도**: 나레이션에 음악/효과음이 크게 섞이면 VAD 가 음성을 걸러내
  전사가 비거나(0개 구간) 품질이 크게 떨어질 수 있음(코드 버그 아님, 모델 한계). 자막이 있는 영상은
  이 문제가 없음 — 가능하면 자막 있는 영상을 우선 선택.
- **장면전환 감지 실패 시 폴백**: 단일 샷 영상 등 `scene` 필터가 프레임을 못 찾으면 시간 균등 6분할
  샘플링으로 대체됨 — 이 경우 실제 장면전환과 무관하게 프레임이 뽑힘.

## 설치
```bash
cd apps/youtube-analyzer-standalone
pip install -r requirements.txt
cp .env.example .env
# .env 에 YOUTUBE_API_KEY 입력 (Google Cloud Console 발급)
```

## 사용법
```bash
python cli.py search "인테리어 조명" --max 20 --days 7
```
