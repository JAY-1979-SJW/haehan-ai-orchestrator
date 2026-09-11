# Instagram 댓글 → DM 자동발송 (데스크톱 앱)

댓글에 특정 키워드가 달리면 자동으로 비공개 답장(DM)을 보내는 로컬 실행 프로그램.
서버 없음 — 이 프로그램이 켜져 있는 동안에만 폴링이 동작한다.

## 동작 방식
- 웹훅이 아니라 **폴링**: 설정한 간격(분)마다 최근 게시물의 댓글을 조회
- DM 은 Instagram 공식 **Private Reply API**(`POST /{ig-user-id}/messages`, `recipient.comment_id`) 사용
  → **댓글 작성 후 7일 이내에만 응답 가능**(Meta 정책)
- 이미 DM 보낸 댓글은 로컬 SQLite(`data/processed_comments.db`)에 기록해 중복 발송 방지
- 액세스 토큰은 OS 자격증명 저장소(Windows DPAPI, `keyring`)에 암호화 저장

## API 방식: Instagram API with Instagram Login (중요)
이 앱은 최신 방식("Instagram API with Instagram Login")을 기준으로 만들어졌다. 구버전
(Facebook 로그인 기반 Graph API, `instagram_basic` 등)과 아래가 다르므로 혼동하지 말 것.

| 구분 | 이 앱이 쓰는 방식 (신규) | 구버전 방식 |
|---|---|---|
| API 호스트 | `graph.instagram.com` | `graph.facebook.com` |
| 필요 권한 | `instagram_business_basic`, `instagram_business_manage_comments`, `instagram_business_manage_messages` | `instagram_basic`, `instagram_manage_comments`, `instagram_manage_messages` |
| 계정 ID | Instagram-scoped 사용자 ID (`graph.instagram.com/me` 로 조회) | Facebook 페이지에 연결된 IG 비즈니스 계정 ID |
| 토큰 발급 위치 | 앱 대시보드 → 이용 사례 → 맞춤 설정 → "Instagram 로그인이 포함된 API" → 2. 액세스 토큰 생성 | Graph API Explorer |
| 토큰 형식 | `IGAA...` 로 시작 | `EAA...` 로 시작(Facebook 사용자/페이지 토큰) |

## Meta 앱 만들고 토큰 발급받기 (처음이라면 여기부터)

이 앱은 서버·웹훅이 필요 없어서(폴링 방식) Meta 앱 설정도 훨씬 간단하다. 아래 순서대로
그대로 따라 하면 된다. 전부 무료다.

1. **Instagram 계정을 비즈니스/크리에이터 계정으로 전환** (개인 계정은 API 사용 불가)
   인스타그램 앱 → 설정 → 계정 종류 및 도구 → 프로페셔널 계정으로 전환
2. **Meta 개발자 계정 만들기**: https://developers.facebook.com → 우측 상단 로그인(페이스북 계정으로) → 가입
3. **앱 만들기**: 내 앱 → "앱 만들기" → 유형은 아무거나(예: 비즈니스) 선택 → 앱 이름 입력 → 생성
4. **Instagram 제품 추가**: 왼쪽 메뉴에서 "제품 추가" → "Instagram" 찾아서 설정
5. **이용 사례 설정**: 왼쪽 메뉴 "이용 사례" → "Instagram에서 메시지 및 콘텐츠 관리" 맞춤 설정
   → "권한 및 기능"에서 아래 3개 권한 추가:
   - `instagram_business_basic`
   - `instagram_business_manage_comments`
   - `instagram_business_manage_messages`
6. **Instagram 테스터로 내 계정 등록**: 같은 화면(이용 사례 > Instagram 로그인이 포함된 API)에서
   "액세스 토큰 생성" 섹션 → 대상 Instagram 계정 추가 → 초대 발송
7. **초대 수락**: 인스타그램 앱(모바일) 또는 instagram.com → 설정 → 앱 및 웹사이트 → 초대된 앱 목록에서 수락
   (계정 소유자 본인이 직접 해야 함 — 타인이 대신 할 수 없음)
8. **액세스 토큰 생성**: 다시 개발자센터로 돌아와 같은 화면에서 계정 옆 "토큰 생성" 클릭
   → `IGAA...`로 시작하는 토큰이 발급됨. 이걸 복사해서 앱의 "액세스 토큰" 칸에 붙여넣으면 끝.

> ⚠️ **자주 헷갈리는 함정**: 앱 대시보드에는 "앱 설정 > 기본 설정"의 일반 "앱 시크릿 코드"와
> "이용 사례 > Instagram 로그인이 포함된 API" 탭의 **별도 "Instagram 앱 시크릿 코드"**가
> 따로 있다. 이 앱(폴링 방식)은 시크릿 코드 자체를 쓰지 않지만, 혹시 이 코드를 웹훅 방식으로
> 확장한다면 반드시 후자(Instagram 전용 시크릿)를 써야 서명 검증이 통과한다.

## 필요 권한 (Meta for Developers)
- `instagram_business_basic`, `instagram_business_manage_comments`, `instagram_business_manage_messages`
- 대상 계정은 Instagram **비즈니스/크리에이터 계정**이어야 함
- 앱을 "개발 모드" 그대로 두고 써도 된다 — Instagram 테스터로 등록한 본인 계정에는 심사(App Review) 없이 바로 동작함.
  다른 사람 계정까지 지원하려면 Meta의 App Review(고급 액세스) 통과가 필요하다.

## ⚠️ 스팸 정책 주의
동일 사용자에게 무차별적으로 DM을 보내면 Meta 스팸 정책 위반으로 계정 제한/앱 심사 반려 사유가 될 수 있음.
이 앱은 "댓글 1건당 DM 1회"만 보내도록 설계되어 있으나, 키워드를 너무 광범위하게(예: 자음 하나) 설정하지 말 것.

## 설치 및 실행
```bash
cd apps/ig-comment-dm-bot
pip install -r requirements.txt
python main.py
```

## exe 패키징
```bash
pip install -r requirements-dev.txt
pyinstaller build.spec
# dist/ig-comment-dm-bot.exe 생성
```
exe로 패키징해도 설정(계정 ID/키워드/DM메시지)과 중복발송 방지 기록은 **exe 파일이 있는 폴더의
`data/` 하위**에 저장된다(임시 압축해제 폴더가 아님 — 매 실행마다 초기화되지 않음).

## 설정 저장
- 액세스 토큰: OS 자격증명 저장소(keyring) — 별도 파일로 노출되지 않음
- 그 외 설정(계정 ID, 키워드 규칙, DM 메시지, 폴링 간격): `data/settings.json`
- 중복 발송 방지 기록: `data/processed_comments.db`
- "시작" 버튼을 누르거나 키워드를 추가/삭제할 때마다 자동 저장되며, 다음 실행 시 자동으로 불러온다.

## 사용 순서
1. 앱 실행 → "계정 설정"에 Instagram 비즈니스 계정 ID, 액세스 토큰 입력 → "연결 테스트 + 저장"
2. "키워드 설정"에서 반응할 키워드와 매칭 방식(부분포함/정확일치) 등록
3. "DM 메시지"에 자동발송할 내용 입력
4. 폴링 간격, 확인할 게시물 수 설정 후 "시작"
5. 로그 창에서 실시간 진행 상황 확인, 필요시 "중지"로 종료

## 라이선스
MIT — `LICENSE` 파일 참고. 자유롭게 수정·배포·상업적 사용 가능.

## 면책
이 앱은 Meta의 공식 API만 사용하며 비공식 스크래핑을 하지 않는다. 다만 과도하게 넓은
키워드 설정이나 대량 발송은 Meta 스팸 정책 위반으로 계정 제한을 유발할 수 있으며, 그 책임은
전적으로 사용자에게 있다.
