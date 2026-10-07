---
name: product-reel-shorts-publish
description: 실제 제품 사진(공급사 허가 필요) + PIL 텍스트 오버레이로 세로형(9:16) 판매 릴스/쇼츠를 만들고 Instagram Graph API + YouTube Data API로 발행하는 전체 파이프라인. "릴스 만들어줘", "쇼츠 만들어서 올려줘", "제품 홍보 영상 만들자" 같은 요청에 사용. 2026-08-25/26 루씨에어 코타라 CTC로 실전 발행 검증 완료(인스타 릴스 1편 + 유튜브 쇼츠 3편). AI 이미지 생성 없이 실제 제품 사진만 쓰고, 발행 인프라(공개 URL 호스팅·오디오 포맷)의 함정을 이미 다 해결해뒀으므로 탐색 없이 아래 순서만 따르면 된다.
---

# 제품 릴스/쇼츠 제작 + 발행 파이프라인

**이 스킬의 목적은 토큰 절약이다.** 2026-08-25/26에 이 파이프라인을
만드느라 Instagram Graph API 발행 실패 원인(nginx IP 차단, moov atom
faststart, 24kHz 모노 오디오)을 찾는 데만 많은 시간을 썼다. 이제 다 코드에
반영돼 있으므로, 새 제품 영상을 만들 때 처음부터 다시 헤매지 말 것.

## 0. 이미지 저작권 — 반드시 먼저 확인

제품 사진을 어디서 가져오는지에 따라:
- **사용자 소유/직접 촬영/허가된 공급사(예: [[gonobi-lexium-authorized-supplier]])**
  → 그대로 사용 가능
- **제3자 블로그·쇼핑몰에서 그냥 긁어온 사진** → 저작권 침해 소지, 발행 전
  반드시 사용자에게 출처와 사용 권한을 확인한다. 확인 없이 진행하지 않는다.

AI 이미지 생성으로 대체하지 않는다 — 실제 제품과 다른 이미지가 나가면
소비자 기만 소지가 있다. 부족한 그래픽(가격표, 비교표, 뱃지, 텍스트 카드)은
PIL로 직접 그린다.

## 1. 프레임 렌더링 — 기존 헬퍼 재사용

`scripts/archive/one_off/kotara_ctc_reel.py`가 재사용 가능한 뉴트럴/프리미엄
스타일 헬퍼를 이미 구현해뒀다. 새 제품이라도 이 함수들을 import해서 쓰고
처음부터 다시 만들지 않는다:

| 함수 | 용도 |
|---|---|
| `_cover(img, w, h, focus_y)` | 전체화면 크롭(제품 사진이 잘리지 않게 focus_y로 조절) |
| `_base_frame(name, mode="letterbox")` | 블러 채움 배경 + 선명한 원본 중앙 배치(위아래 여백 방지) |
| `_gradient_band(img, y0, y1, ...)` | 텍스트 가독성용 그라데이션 — **fade to 0 금지**, 최소 alpha 175 이상 유지해야 텍스트가 안 묻힌다(2026-08-25에 겪은 버그) |
| `_phone_pill(draw, cx, y, text)` | 전화번호 CTA 알약 배지 |
| `_location_badge(draw, x, y, text)` | 좌상단 작은 배지(주소·상호 등, 가격 위계를 침범하지 않는 크기로) |
| `build_video(frames, durations, out)` | ffmpeg xfade로 프레임들을 이어붙임 |
| `mux_audio(video, tts, bgm, out)` | **faststart + 48kHz 스테레오**로 오디오 믹싱(아래 3번 참조) |

디자인 원칙(2026-08-25 확정): 뉴트럴/프리미엄 팔레트(화이트·블랙·아이보리 +
제품 고유색에서 뽑은 포인트 컬러), 빨간 폭탄가격표·별모양 스티커·과도한
이모지 금지. **가격이 1순위, 그 다음 제품명/CTA, 화면 텍스트는 하단
그라데이션 밴드에만 배치**(제품 자체를 가리지 않도록).

## 2. 대본 타이밍 — 사용자가 준 대본이 있으면 그대로 지킨다

사용자가 장면별 초 단위 타이밍이 있는 대본을 주면, **화면 길이를 그
타이밍대로 고정**하고 내레이션 TTS 속도를 장면 길이에 맞춰 압축한다(반대
아님). `scripts/archive/one_off/kotara_ctc_shorts.py::_tts_fit()` 패턴을 재사용:

```python
def _tts_fit(text, target_seconds, out_dir, idx):
    # 1) rate=+0%로 기준 길이(d0) 측정
    # 2) d0가 이미 target 이내면 그대로 사용
    # 3) 아니면 필요한 배속을 계산해 재합성 (+N%, 최대 +100%)
    # 4) 그래도 넘치면 ffmpeg -t 로 정확히 target_seconds에 맞춰 트림/패딩
```

⚠️ **최대 2배속(+100%)까지도 문장이 다 안 들어갈 수 있다.** 특히 가격·
전화번호가 나오는 마무리 장면에서 잘리면 치명적이니, 잘리는 장면이
있으면 반드시 사용자에게 먼저 알리고 확인받는다 — 조용히 잘린 채로
발행하지 않는다. (트레이드오프를 사용자가 선택하게 한다: 화면 연장 /
문장 축약 / 그대로 잘림 감수.)

사용자가 타이밍 없는 대본만 주거나 스스로 만드는 경우엔 반대로 TTS 실측
길이에 화면 길이를 맞춰도 된다(이전 버전 방식, `_probe_duration()` 활용).

## 3. 오디오/컨테이너 요구사항 — Instagram Graph API가 요구하는 조건

`mux_audio()`에 이미 반영됨, 새로 만들 때도 반드시 유지:
- `-movflags +faststart` — moov atom을 파일 앞에 둬야 한다. 없으면
  Graph API가 `status_code=ERROR`로 조용히 실패한다(원인 메시지 없음).
- `-ar 48000 -ac 2` — 48kHz 스테레오로 강제 변환. edge-tts 원본은 24kHz
  모노라서 amix 결과가 이상한 샘플레이트로 나가면 실패한다.
- 무음 트랙 금지 — 릴스에 오디오가 아예 없으면 거부된다.

## 4. 발행 — Instagram Graph API

`scripts/instagram/api_publish.py` 사용(`create_reel_container` →
`wait_ready` → `publish`). `video_url`은 **Meta 서버가 인증 없이 GET/HEAD로
가져갈 수 있는 공개 URL**이어야 한다 — 확정된 경로 2가지:

- **경로 A(추천, 영구 보관)**: `haehan-ai` 홈페이지 저장소의
  `public/reels/{영문파일명}.mp4`에 커밋 후 push → GitHub Actions 자동
  배포(~1분) → `https://haehan-ai.kr/reels/{파일명}.mp4`
- **경로 B(임시 업로드)**: `public_media_router`
  (`POST /api/v1/public-media/upload`) — ⚠️ 서버 컨테이너 재배포 시 파일이
  사라진다(바인드 마운트 아님), 매번 재업로드 필요.

자세한 함정(nginx IP 차단, 정규식 `/v1/` 누락, `{32}` 브레이스 버그 등)은
[[channel-instagram-worklog]] 참조 — 이미 다 고쳐져 있으니 재발이 없는 한
다시 디버깅할 필요 없음.

캡션은 지역 타겟팅이 필요하면 해시태그로(예: `#다산동 #다산신도시`),
"전국 최저가" 같은 단정적 최상급 표현은 표시광고법 리스크로 사용 금지 —
"설치비 포함하면 더 유리합니다" 같은 비교 유도 문구로 대체.

## 5. 발행 — YouTube Data API (Shorts)

`scripts/youtube/uploader.py::prepare_upload_plan()` →
`execute_upload_plan(approved=True, confirm=APPROVAL_PHRASE, dry_run=False)`.

- **공개(public) 업로드는 매번 사용자 승인 필수** — 기본값 private.
- 예약 게시하려면 `values['publish_at']`에 ISO 8601(`+09:00` KST) 지정 —
  자동으로 `privacy`가 `private`로 강제됨(정상 동작, 예약 공개 전까지
  비공개 유지하는 YouTube 정책).
- **영상 파일 자체를 나중에 교체하는 API는 없다.** 내용을 바꾸려면
  `videos().delete(id=...)` 후 재업로드. 메타데이터(제목·설명·태그)만
  바꾸려면 `videos().update()`로 충분.
- 삭제는 `youtube.force-ssl` 스코프로 가능:
  ```python
  from google.oauth2.credentials import Credentials
  from googleapiclient.discovery import build
  creds = Credentials.from_authorized_user_file(
      "ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json",
      scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
  )
  build("youtube", "v3", credentials=creds).videos().delete(id=video_id).execute()
  ```

## 6. 네이버 클립

공식 API 없음(2026-08-25 확인, `capability_check.py naver clip` 결과) —
CDP 브라우저 자동화만 가능. 발행 전 **로그인 계정 확인 필수** — 클립
채널과 블로그 계정이 어긋나 있을 수 있다(예: `banditbul_light` 채널이
skyjwsin 계정으로 잘못 생성된 이력, [[naver-account-split-by-purpose]]
참조). CDP 자동화 코드는 아직 미구현 — 필요 시 `scripts/naver/` 패턴을
참고해 새로 작성.

관련: [[channel-instagram-worklog]] [[channel-youtube-worklog]]
[[gonobi-lexium-authorized-supplier]] [[instagram-marketing]]
