# haehan.2026 Instagram 계정 → Meta 앱 연결 전체 기록 (2026-09-11)

> 목적: 향후 "AI 에이전트로 인스타/Meta 계정 연결을 자동화해주는 상품"을
> 만들 때 재사용할 실전 절차 기록. 실제로 겪은 함정·해결 순서 그대로 남김.

## 배경

기존에는 big.sun2024(조명 판매 계정)만 Meta Graph API에 연결돼 있었다.
"해한 AI" 콘텐츠 전용 계정 haehan.2026을 신규로 만들어 같은 Meta 앱
(Banditbul Publisher, App ID 1677156466691808)에 두 번째 Instagram
계정으로 연결하는 전 과정.

## 1단계 — Instagram 계정 준비

1. haehan.2026 계정을 **Creator(크리에이터) 프로페셔널 계정**으로 전환
   (카테고리: 개인 블로그). 비즈니스/크리에이터 전환 없이는 Graph API 자체가
   불가능하다(개인 계정은 API 대상이 아님).

## 2단계 — Meta 개발자 콘솔에서 테스터로 추가

1. `developers.facebook.com/apps/{APP_ID}/instagram-business/api-setup/`
   접속 → 기존 앱(Banditbul Publisher)의 Instagram API 설정 화면
2. "2. 액세스 토큰 생성" 섹션 → "계정 추가" → haehan.2026 아이디 입력 →
   Instagram 테스터로 초대 발송
3. **계정 소유자(=haehan.2026 본인)가 직접 수락해야 한다** — 앱이 아닌
   계정 쪽에서: `instagram.com/accounts/manage_access/` → "테스터 초대"
   탭 → 수락. (이 수락 없이는 다음 단계에서 계정이 목록에 안 뜬다.)

## 3단계 — 토큰 발급 시도와 실패한 경로 (중요한 함정)

개발자 콘솔 "토큰 생성" 버튼으로 얻은 토큰은:
- `/me` 같은 기본 Graph API 호출에는 **정상 작동**한다 (짧은 테스트용으로는 충분)
- 하지만 `ig_exchange_token`(장기 토큰 교환)에는 **호환되지 않는다** —
  계속 `Invalid OAuth 2.0 Access Token`(코드 190) 오류가 남.
  시크릿이 틀려서가 아니라 **발급 경로 자체가 다른 종류의 토큰**이기 때문.

➡ **결론: 콘솔의 수동 "토큰 생성" 버튼은 장기 연결용으로 쓰면 안 된다.**
정식 OAuth 인가 플로우(아래 4단계)로만 안정적으로 연결된다.

## 4단계 — 정식 OAuth 인가 플로우로 연결 (실제 성공한 경로)

이 프로젝트엔 이미 `ai_orchestrator/connectors/instagram/instagram_dm_router.py`에
운영 서버용 OAuth 라우트가 구현돼 있다 (big.sun2024가 이 경로로 연결됨):

```
POST /api/v1/instagram-dm/oauth/start
  → { auth_url, state }  (auth_url은 instagram.com/oauth/authorize)

브라우저에서 auth_url 열기 → 해당 계정으로 로그인 상태에서 "허용" 클릭
  → https://haehan-ai.kr/.../oauth/callback?code=...&state=... 로 리다이렉트

GET /api/v1/instagram-dm/oauth/callback?code=...&state=...
  → 서버가 code→단기토큰→장기토큰 교환을 전부 수행하고 DB에 암호화 저장
  → { account_id, username, status: "connected" }
```

**운영 API는 nginx에서 owner IP만 허용**하므로 외부에서 직접 curl 불가.
SSH로 서버에 들어가 `curl http://127.0.0.1:8400/...`처럼 **컨테이너
localhost로 직접 호출**하면 IP 제한을 우회해서 호출할 수 있다(관리자 본인
작업이므로 문제 없음).

## 5단계 — 발견한 버그와 수정 (재발 방지)

`_app_id()` 함수가 `META_APP_ID`(일반 Meta 앱 ID)를 `IG_APP_ID`
(Instagram 전용 앱 ID)보다 우선 사용하고 있었다:

```python
# 수정 전 (버그)
def _app_id() -> str:
    return os.environ.get("META_APP_ID", os.environ.get("IG_APP_ID", "")).strip()

# 수정 후
def _app_id() -> str:
    return os.environ.get("IG_APP_ID", os.environ.get("META_APP_ID", "")).strip()
```

Instagram Login OAuth는 **인가 URL 발급과 코드 교환에 반드시 동일한
app_id**를 써야 한다. 인가는 Instagram 전용 앱 ID로 이루어지는데 서버가
교환 시 Meta 앱 ID를 쓰면 `Invalid platform app` 오류가 난다.

추가로 운영 서버 `.env`의 `IG_APP_ID` 값 자체가 `META_APP_ID`와 동일하게
(잘못) 설정돼 있었다 — 실제 Instagram 전용 앱 ID(`1551851412717730`)로
정정하고 컨테이너 재기동.

**배포 데몬(`ai-orchestrator-deploy-trigger.service`)이 또 꺼져 있어서**
`git push`만으로는 반영 안 됨 → SSH로 직접 `git fetch && git merge
--ff-only` + `docker compose up -d --build`로 수동 배포.

## 6단계 — 자동화 활성화

```
POST /api/v1/instagram-dm/accounts/{account_id}/automation  {"enabled": true}
POST /api/v1/instagram-dm/rules  {계정ID, 키워드, 답장 메시지 등}
```

haehan.2026에는 "가격/문의/방법/제작/자동화" 키워드 → AI 에이전트 제작
안내 DM 규칙을 신규로 등록했다. 규칙이 0개면 automation_enabled=true여도
실제로는 아무 반응도 안 한다(주의).

## 7단계 — 콘텐츠 게시 (릴스)

- 보유하고 있던 콘텐츠는 유튜브용 16:9 풀영상(4분2초)뿐이라 그대로는
  릴스에 못 올린다 (9:16 필요, 길이도 90초 내외 제한).
- 훅(0~41초) + 데모(179~202초) + CTA 앞부분(202~214초) 세 구간만 잘라
  이어붙이고, `gblur` 배경으로 9:16 세로 캔버스에 맞춤(ffmpeg
  `split`+`scale`+`gblur`+`overlay` 필터 조합).
- Graph API의 `video_url`은 **공개 접근 가능한 URL**이어야 해서, 홈페이지
  정적 파일 경로(`haehan-ai` 저장소 `public/reels/`)에 넣고 git push →
  GitHub Actions 자동 배포로 공개 URL 확보.
- `scripts/instagram/api_publish.py`의 `publish_reel()`로 컨테이너
  생성(`confirmed=False`) → 처리 완료 대기 → 사용자 승인 후 `publish()`로
  실제 게시.

## 핵심 교훈 요약 (다음에 새 계정 연결할 때 이 순서로)

1. 계정을 Creator/Business 전환
2. 기존 앱에 Instagram 테스터로 추가 → 계정 소유자가 직접 수락
3. **콘솔 "토큰 생성" 버튼 쓰지 말 것** — `/oauth/start` → 브라우저 동의 →
   `/oauth/callback` 정식 플로우만 사용
4. `IG_APP_ID`(Instagram 전용)와 `META_APP_ID`(일반)를 혼동하지 말 것 —
   Instagram Login 플로우는 항상 IG_APP_ID를 써야 함
5. 운영 API는 owner IP 잠금이라 SSH 후 localhost로 호출
6. 배포 데몬이 죽어있을 수 있으니 서버 HEAD 커밋을 확인하고 필요시 수동 배포
7. 자동화는 automation_enabled 토글 + 최소 1개 이상의 rule 등록까지 해야 실제로 동작
8. 릴스 게시는 9:16·90초 내외로 재편집 + 공개 URL 호스팅 필요

관련: [[instagram-comment-dm-automation]], [[instagram-api-app-setup]], [[channel-instagram-worklog]]
