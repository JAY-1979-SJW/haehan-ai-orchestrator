# Credential Handling Policy

## 기본 방향

Claude Code는 공식 권한 위임 구조(OAuth, service account, API key, developer console role)를 사용해 자율 실행한다. 인증서 비밀번호 저장 금지.

## 인증 자동화 정책

- 본인 소유 계정에 한해 Playwright storageState, .env 기반 자격증명, 쿠키/세션 재사용을 통한 로그인 자동화를 허용한다.
- 타인 계정 자동화, credential 하드코딩, 공개 저장소에 .env·storageState 커밋은 금지한다.
- .gitignore에 .env, storageState.json, auth.json이 포함되어 있는지 확인한다.
- CAPTCHA, 2FA, 봇 탐지 등 보안 메커니즘 우회는 계속 금지한다.
- 자동화 대상 사이트의 이용약관(ToS)을 확인하고, 약관 위반 시 사용자에게 고지한다.

## 1. 결론

비밀번호 수집/추출/별도 저장 금지.
자동화는 비밀번호 추출이 아니라 공식 권한 위임, OAuth token, service account, API key, developer console role 기반으로 수행.

## 2. 금지 방식

| 방식 | 이유 |
|------|------|
| browser password extraction | 보안 경계 침범 |
| Chrome Login Data DB 읽기 | 보안 경계 침범 |
| Google Password Manager 비밀번호 추출 | 보안 경계 침범 |
| Windows Credential Manager 비밀번호 추출 | 보안 경계 침범 |
| OTP/TOTP seed 저장 | 2FA 무력화 |
| 인증서 비밀번호 저장 | 법적 위험 |
| 평문/복호화 가능 비밀번호 DB 구축 | 데이터 유출 위험 |

## 3. 허용 방식

| 방식 | 설명 |
|------|------|
| OAuth token | 공식 위임 흐름, refresh token은 secret store에 저장 |
| API key | 플랫폼 발급 공개 키, secret store에 저장 |
| service account | JSON key 파일, secret store에 저장 |
| delegated admin | Workspace/플랫폼 관리자 위임 |
| developer console role | 콘솔 운영 전담 계정 |
| enterprise password manager | 1Password, Bitwarden Business 등 |
| secret manager | GCP Secret Manager, AWS Secrets Manager 등 |
| safe env setter | `.env` 파일 직접 작성 대신 setter 스크립트 사용 |

## 4. 서비스별 권장 인증 방식

| 서비스 | 권장 방식 | 비고 |
|--------|---------|------|
| Kakao | OAuth 2.0 (client_credentials / authorization_code) | client_secret은 secret store |
| Naver | OAuth 2.0 + API key | API key는 secret store |
| Google | service account JSON key / OAuth 2.0 | key 파일은 secret store |
| YouTube | OAuth 2.0 (YouTube Data API) | refresh token은 secret store |
| PublicData/NTS | API key | secret store |
| Hometax | 법인 공인인증서 | finance_approver 주체 |
| 법인뱅킹 | 법인 API + OTP (finance_approver) | 송금은 항상 APPROVAL_REQUIRED |
| Hiworks | 관리자 API key / OAuth | secret store |

## 5. AI가 할 수 있는 일

- 전용 브라우저 프로필 기반 세션 재사용 (cookie/session export 없이)
- 세션 상태 자동 점검 (READY_LOGGED_IN / SESSION_EXPIRED)
- 로그인 유지 중이면 즉시 콘솔 업무 수행
- 세션 만료 시 NEEDS_REAUTH 기록 + 재개 가능한 pending task 파일 생성
- 재인증 완료 후 작업 자동 재개
- 로그인된 콘솔에서 설정/신청 진행
- 토큰/키를 safe env setter로 저장
- API 호출 결과 확인
- 감사 로그 작성

## 6. AI가 하면 안 되는 일

- 비밀번호 읽기/저장
- OTP 저장
- 보안 우회
- 타인 계정 접근

## 7. 다음 구현 단계

| 단계 | 작업 키 | 내용 |
|------|---------|------|
| 1 | `SERVICE-ACCOUNT-1` | Google service account 발급/저장 자동화 |
| 2 | `OAUTH-TOKEN-1` | OAuth refresh token 갱신/저장 자동화 |
| 3 | `DEV-CONSOLE-ROLE-1` | developer console 전담 계정 설정 |
| 4 | `SECRET-STORE-1` | safe env setter / secret manager 통합 |
