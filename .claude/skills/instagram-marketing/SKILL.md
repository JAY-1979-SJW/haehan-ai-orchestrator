# 인스타그램 마케팅 스킬 (big.sun2024 · 반딧불 전파사)

네이버 블로그 스킬(`naver-blog-publish`)과 같은 구조 — 이미지 소스에서 다음
시공사례를 고르고, 실제 사업자 정보로 캡션을 만들어 캐러셀로 발행한다.

## ⭐ 표준 워크플로 — 정보성 캐러셀 (2026-08-19 확립, 이 방식을 기본으로 쓴다)

단순 시공사진 나열은 반응이 없다. **장마다 다른 정보를 이미지에 얹은
정보성 캐러셀**이 저장(북마크)을 만들고, 저장은 노출 가중치에 직결된다.

```
1) 사례 선정   scripts/instagram/cases.py::next_case('시공사례', kind='photo')
2) 슬라이드    scripts/instagram/overlay.py::render_slide()
               → 원본 사진 + 배지/제목/본문 합성 (4:5, 1080x1350)
3) 호스팅      haehan-ai/public/ig/{폴더}/ 에 저장 → 커밋·푸시 → 배포(약 1분 20초)
               → https://haehan-ai.kr/ig/{폴더}/NN.jpg
               ※ Instagram API는 로컬 경로 불가, 공개 URL만 받는다
4) 발행        scripts/instagram/api_publish.py::create_carousel(urls, caption)
               → 사용자 확인 → publish(container_id)
```

### 콘텐츠 원칙 (타겟: 주부·셀프인테리어 관심층)
- **전문용어 금지.** "이지라인 메타 매입 라인 조명" ❌ → "천장 안으로 쏙 들어가는 조명" ✅
- 자격증·관급공사 실적은 주부에게 안 통한다. "20년 현장 경력" 한 줄로 충분.
- **메인 셀링포인트: AI 조명 인테리어 디자인 + 3D 공간뷰 무료 제공.**
  "조명은 한번 달면 바꾸기 어렵다 → 3D로 미리 보고 결정하세요"가 핵심 훅.
- **실제 소비자 불만을 선제 해소**한다(웹 조사 근거, 2026-08-19):
  ① 전구 나가면 교체가 어렵다(가장 많은 불만) ② 6500K는 눈부시고 눈이 피로하다
  ③ 라인조명만으론 어둡다(매입등 병행 필요) ④ 너무 밝으면 그림자가 세져 답답해 보임(8~10W/m 적정)
- **셀프로 하려는 사람도 도와준다.** 퍼주는 콘텐츠가 팔로워를 모으고 결국 문의로 온다.
- 해시태그는 지역+주부 검색어 중심: `#남양주인테리어 #다산동 #셀프인테리어
  #신혼집인테리어 #거실조명 #조명추천` (전국구 `#조명` 은 묻힌다)

### 인기 게시물 실조사 결과 (2026-08-19, `#조명인테리어` 상위 게시물 분석)

반응 좋은 계정들의 공통 패턴 — **이걸 따라야 한다**:

1. **단지명 + 평수를 제목에 박는다** ⭐ 가장 강력
   `"대전) 호반써밋유성 30py대 실링팬, 조명"` `"서산 중흥 84㎡ A타입"` `"우장산 힐스테이트 33평"`
   → 그 단지 입주민이 직접 검색해서 들어온다. 상세는 [[apartment-lighting-plan]] 스킬.
2. **시공 내역을 구체적 숫자로 나열**
   `"거실 팬앤코 실링팬 52″ 상시전원 / 2,3인치 다운라이트 20여개 / 커튼박스 간접조명"`
   → 전문성이 보이고 검색에도 걸린다. 추상적 설명("깔끔하게 시공")은 약하다.
3. **도발적 훅** — `"✨ 아직도 거실등 하나만 달고 계신가요?"`
4. **비교형 콘텐츠** — `"3인치 다운라이트, 기본형 VS 움푹형"`
   저장률이 가장 높은 포맷. 신규 계정에 특히 유리하다.
   결론을 반드시 제시하고("답은 같이 쓰세요"), 실패 케이스도 적는다
   ("라인만 → 어둡다 / 다운만 → 삭막하다").
5. **DM 유도** — `"📩 주문·견적 문의는 DM"`. 전화번호만 적는 것보다 문턱이 낮다.
6. **실제 쓰이는 해시태그**: `#홈스타일링 #거실꾸미기 #거실스타그램
   #신축아파트인테리어 #아파트조명 #조명설치 #셀프인테리어`

### 발행 빈도 (실측 쿼터: 24시간 100개)
기술 한도와 무관하게 **하루 1개**가 최적. 여러 개 올리면 서로 도달을 갉아먹는다.
릴스=신규 유입, 캐러셀/사진=프로필 방문자 신뢰 확보로 역할이 다르다.

## 릴스 (영상) — 표준 워크플로 (2026-08-21 확정, 자막+배경음악 버전)

무음 슬라이드쇼(`reel.py::build_slideshow()` 단독)는 초기 버전이고, 지금은
**장별 훅 자막 + 배경음악**을 넣은 버전을 기본으로 쓴다. 릴스 2개(마그네틱 시공,
거실 와우샷)를 이 파이프라인으로 만들어 발행 완료함(2026-08-21).

```
1) 사례 선정   next_case('시공사례', kind='reel')  ← photo와 kind 분리, 중복 발행 방지
2) 훅 자막     scripts/instagram/reel_overlay.py::render_reel_slide(src, dst, text)
               → 이미지 1장씩 1080x1920 세로로 리사이즈 + 하단 그라데이션 위 자막 합성
               → 첫 장은 반드시 가장 임팩트 있는 컷 + 도발적 훅 문구
                 (예: "이 집, 조명 하나 바꿨을 뿐인데 분위기가 통째로 달라졌어요")
               → 이미지 순서는 원본 파일명 순서를 그대로 안 쓰고, 가장 강한 컷을
                 1번으로 재배치해도 된다 (case.images를 log_no별 seq로 직접 매핑)
3) 영상 합성   scripts/instagram/reel.py::build_slideshow_from_frames(frames, bgm_path, out_path)
               → xfade 크로스페이드 + bgm mp3 믹싱(afade 페이드아웃 + volume=0.5)까지
               한 번에 처리하는 재사용 함수(2026-08-21 신설, 기존엔 스크립트 안에
               매번 인라인으로 짜서 재사용이 안 됐음 — 이제 이 함수 하나로 끝)
4) 배경음악    data/instagram_reels/bgm/candidate.mp3 (Mixkit, 상업적 이용 무료·
               저작자 표시 불필요, 2026-08-21 CDP로 실제 다운로드 확보).
               재사용 우선 — 새로 찾지 말고 이 파일 계속 쓴다. 다른 곡이 필요하면
               Mixkit 페이지(`https://mixkit.co/free-stock-music/`)를 CDP로 열어
               `<audio src>` 태그에서 실제 mp3 URL(assets.mixkit.co/music/{id}/{id}.mp3)을
               읽어 curl로 받는다(Referer: https://mixkit.co/ 필요, preview 경로는 403 남).
5) 호스팅      haehan-ai/public/reels/{영문-슬러그}.mp4 로 저장 → 커밋·푸시 → 배포
               (약 1~2분, 배포 완료는 curl로 파일 크기 일치 확인 후 진행)
               → https://haehan-ai.kr/reels/{영문-슬러그}.mp4
6) 캡션        전화번호·경력·도매가시공비 문구·3D오퍼 4가지 상시 포함(아래 BIZ 참조),
               이름은 빼고 "대표"로. 첫 줄은 훅 문구 그대로 재사용.
7) 발행        scripts/instagram/api_publish.py::publish_reel(video_url, caption, confirmed=True)
               → 발행 후 반드시 mark_posted(case, ig_url=permalink, kind='reel') 호출
```
- **무음 AAC 오디오 트랙 필수**(anullsrc, 배경음악 안 쓸 때). 오디오 트랙 자체가
  없으면 Instagram이 거부한다.
- 릴스 탭 노출 조건: 9:16 · 5~90초 · H.264.
- CDP/Playwright 작업 시 지켜야 할 것은 [[cdp-browser-automation]] 스킬 4번 참조.

## 3채널 동시 발행 (인스타 릴스 + 네이버 클립 + 유튜브 쇼츠, 2026-08-21 확정)

위에서 만든 같은 mp4 파일을 3곳에 그대로 올린다. 순서: 인스타 → 클립 → 쇼츠.

**네이버 클립**
- 채널: `banditbul_light` (clip.naver.com/@banditbul_light), skyjwsin 네이버
  계정으로 로그인된 CDP 세션에서 이미 프로필 생성 완료(2026-08-19).
- 업로드: `clipcreators.naver.com/web/upload` → 파일 선택 → `/web/draft/{id}`로
  이동 → 설명(300자 제한, IG 캡션 축약본) + 커버(훅 프레임 선택) +
  **카테고리는 매번 다시 선택**(`리빙, 홈` > `인테리어, DIY` — 드래프트마다 리셋됨,
  [[cdp-browser-automation]] 참조) → 전체공개 → 등록.
- 장소 태그는 반딧불 전파사가 네이버 스마트플레이스에 미등록이라 아직 못 씀
  (별도 등록 작업 필요, 미완료).

**유튜브 쇼츠**
- 채널: "반딧불 전파사" (`UCJQ7WUOXjJUqTd82TsASrUg`, @반딧불전파사) —
  skyjwshin@gmail.com 계정 아래 신규 브랜드 채널로 생성(2026-08-21). 기존
  "해한 AI" 채널과는 별개 — 절대 혼동하지 말 것.
- 전용 OAuth 토큰: `ai_orchestrator/storage/secrets/youtube_oauth_banditbul.json`
  (.env의 `YOUTUBE_OAUTH_TOKEN_FILE_BANDITBUL`). 기존 `YOUTUBE_OAUTH_TOKEN_FILE`은
  "해한 AI" 채널용이니 절대 덮어쓰지 않는다.
- 업로드는 `googleapiclient.discovery.build('youtube','v3', credentials=creds)` +
  `MediaFileUpload(..., resumable=True)` + `videos().insert(part='snippet,status', ...)`.
  `categoryId: '26'`(Howto&Style), `privacyStatus: 'public'`, 제목 끝에 `#Shorts` 필수
  (9:16·60초 이하 영상이 쇼츠 탭에 뜨는 조건).
- 채널 새로 만들거나 재인가할 때는 [[cdp-browser-automation]] 4번의 OAuth 관련
  항목(redirect_uri, 403 무시하고 code 추출 등)을 그대로 따른다.

## 구버전(CDP 클릭) — 참고용

`scripts/instagram/publish.py`, `scripts/instagram/ig_batch.py` 는 CDP로 웹 UI를
클릭하는 방식. **캐러셀 다중 업로드가 안 되고**(input이 non-multiple) 릴스
업로드 진입도 불안정해서, 정식 API 방식으로 대체했다. 단일 사진 발행 용도로만 남긴다.

```bash
python scripts/instagram/ig_batch.py --dry-run       # 다음 후보 + 캡션 미리보기만
python scripts/instagram/ig_batch.py --confirmed     # 실제 발행(단일 사진)
```

## 승인 절차 (매번 필수)

- 외부 공개 발행 = 매번 재확인 원칙(CLAUDE.md). `--confirmed` 실행은
  `scripts/instagram/guard_instagram_publish.py` PreToolUse 훅이 강제로 사용자
  확인을 받는다(`.claude/settings.json` 등록됨) — bypassPermissions 모드여도
  우회 안 됨.
- 캡션은 발행 전 사용자에게 반드시 미리보기로 보여주고 승인받는다.

## 사업자 정보 (BIZ, `scripts/instagram/caption.py`)

- 브랜드: 반딧불 전파사 (실제 사업자 = 승민전력, 신재우 대표 — 목적에 따라
  간판만 다르게 사용, 2026-08-19 사용자 확인)
- 대표: 신재우 / **010-7387-6635** (2026-08-19 확정 — 이 번호로 고정)
- **캡션에 대표 실명은 노출하지 않는다(2026-08-21 확정)** — 브랜드명("반딧불 전파사")과
  전화번호만 쓰고, "신재우" 이름은 캡션 본문에서 뺀다. `caption.py`의 `credentials`/
  `문의` 줄이 이미 이렇게 수정됨.
- 경력·자격: 전기공사산업기사·소방전기기사, 20년+ 전기·통신·소방 현장
  (경찰청·서울교통공사·각 교육청 등 관급공사 다수, 위례 오벨리스크 326세대·
  동탄 골든아이타워 등 현장소장 경력) — 근거: 회사소개서.pdf
  (`C:\Users\skyjw\OneDrive\01. PROJECT_FILE\3. 개인공유폴더\1. 신재우 대표\회사소개서.pdf`)
- **핵심 셀링포인트(2026-08-21 확정, 모든 캡션에 상시 포함)**:
  1. 조명 자재는 도매처에서 직접 받아와 최대한 저렴하게 공급하고,
     **시공비만 받는다**. 마진을 안 붙이는 구조라는 점을 매번 강조한다.
  2. **설치 공간 3D 이미지 제공** — 사진 몇 장만 보내주면 AI가 조명 배치를
     3D로 미리 보여준다는 오퍼를 매번 넣는다.
- 주소: 경기도 남양주시 다산동 6143외1필지 다산현대프리미어캠퍼스 2층
  에이씨02-043호

정보가 바뀌면 `caption.py`의 `BIZ` 딕셔너리만 수정하면 이후 모든 캡션에
자동 반영된다. `build_caption()`은 이미 `wholesale_offer`·`design_3d_offer` 문구를 캡션
본문에 항상 삽입하도록 되어 있음 — 캡션을 수동으로 새로 쓸 때도 전화번호·
경력·도매가 시공비 문구·3D 설치공간 이미지 제공 문구 4가지는 빠뜨리지 않는다.

## 알려진 함정

- **3채널(릴스·클립·쇼츠) 발행 시 반복되는 CDP/Playwright 오류는
  [[cdp-browser-automation]] 스킬의 "4. Playwright를 쓸 때 반드시 지킬 것" 섹션에
  원인·해결 확정해뒀다(2026-08-21)** — 탭을 여러 Bash 호출에 걸쳐 재사용하지 말 것,
  `page.close()` 습관적으로 넣지 말 것, `page.screenshot()` 폰트로딩 멈춤은
  `inner_text()`로 우회, shadow DOM 입력창은 자동화 대신 사용자에게 요청, 네이버
  클립 카테고리는 드래프트마다 재선택 필요 등. 이 작업을 다시 할 때 반드시 먼저 읽는다.

- **CDP 모바일 에뮬레이션 잔여 설정으로 "게시물이 깨져 보임"(2026-08-19)** —
  릴스 업로드를 시도하며 `Emulation.setDeviceMetricsOverride`(390x844)를 걸었더니
  그 설정이 브라우저에 남아, 정사각형 사진이 확대·잘려 보였다. 게시물 데이터는
  멀쩡한데 화면만 깨진 것. 에뮬레이션을 걸었으면 **반드시
  `Emulation.clearDeviceMetricsOverride`로 해제**할 것.

- **`page.screenshot()` 타임아웃** — 인스타그램 create 플로우 페이지에서
  "waiting for fonts to load" 로 자주 멈춘다(2026-08-19 실측). 상태 확인은
  screenshot 대신 `page.evaluate()` / `inner_text()` 로 한다.
- **`만들기` 텍스트/아이콘 직접 클릭 실패** — 사이드바 축소 상태에서 요소가
  `visible=false` 로 판정돼 클릭이 계속 실패한다. `https://www.instagram.com/create/select/` 로
  **직접 URL 이동**하는 게 훨씬 안정적 — `input[type=file]` 이 즉시 나타난다.
- **캡션 입력창 셀렉터** — `textarea[aria-label="문구를 입력하세요..."]`.
  `div[contenteditable=true]` 로는 잡히지 않을 수 있다.
- **계정 확인 필수** — 발행 전 로그인 계정이 `big.sun2024` 맞는지
  `page.goto('https://www.instagram.com/')` 후 우측 "회원님" 카드 텍스트로
  확인한다(다른 계정 로그인 상태로 오발행 방지).
