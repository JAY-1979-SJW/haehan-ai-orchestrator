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

토큰 발급 절차: Meta 앱 대시보드에서 대상 Instagram 계정을 **Instagram 테스터**로 등록 →
그 계정 소유자가 Instagram 앱(또는 instagram.com 설정 → 앱 및 웹사이트)에서 초대 수락 →
개발자센터의 "액세스 토큰 생성" 섹션에서 계정 옆 "토큰 생성" 버튼 클릭.

## 필요 권한 (Meta for Developers)
- `instagram_business_basic`, `instagram_business_manage_comments`, `instagram_business_manage_messages`
- 대상 계정은 Instagram **비즈니스/크리에이터 계정**이어야 함

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
