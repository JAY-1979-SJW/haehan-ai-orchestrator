# 대표님 무인증 자동화 전략

## 기본 방향

Claude Code는 가능한 작업을 직접 실행한다. 개발자 콘솔 작업은 전용 브라우저 프로필 기반 세션 재사용 구조로 실행한다. 로그인되어 있으면 즉시 업무를 수행하고, 세션 만료 시에는 NEEDS_REAUTH로 기록하여 재개 가능한 pending task 파일을 남긴다. 인증이 필요한 작업은 "대표님 대기"가 아니라 "인증 주체 필요(NEEDS_AUTH_PRINCIPAL)"로 분류하고, 인증 주체가 준비되면 Claude Code가 자율 진행한다. 타인 계정 자동화·보안 우회는 금지. 본인 계정은 전용 프로필·storageState·`.env` 기반 허용.

### 전용 프로필 기반 실행 구조

```
전용 프로필 준비
→ 세션 상태 자동 점검 (READY_LOGGED_IN / SESSION_EXPIRED)
→ 로그인 유지 중이면 즉시 업무 실행
→ 만료 시 NEEDS_REAUTH 기록 + pending task 파일 생성
→ 재인증 후 자동 재개
→ 결과 저장/보고
```

대표님에게 터미널 실행, 파일 확인, 결과 붙여넣기를 요구하지 않는다.

## 1. 목표

대표님이 로그인/2FA/OTP/인증서 입력을 하지 않는 자동화 구조 정의.
AI가 인증을 우회하거나 저장된 비밀번호를 수집하는 구조는 금지.
공식 위임, 서비스계정, OAuth token, API key, developer console operator, finance approver 구조로 해결.

## 인증 자동화 정책

- 본인 소유 계정에 한해 Playwright storageState, .env 기반 자격증명, 쿠키/세션 재사용을 통한 로그인 자동화를 허용한다.
- 타인 계정 자동화, credential 하드코딩, 공개 저장소에 .env·storageState 커밋은 금지한다.
- .gitignore에 .env, storageState.json, auth.json이 포함되어 있는지 확인한다.
- CAPTCHA, 2FA, 봇 탐지 등 보안 메커니즘 우회는 계속 금지한다.
- 자동화 대상 사이트의 이용약관(ToS)을 확인하고, 약관 위반 시 사용자에게 고지한다.

## 2. 기본 원칙

| 원칙 | 내용 |
|------|------|
| 대표님 인증 없음 | 로그인/2FA/OTP/인증서 입력 요구 금지 |
| AI 인증 우회 없음 | 비밀번호 추출, 쿠키 탈취, captcha 우회 금지 |
| 공식 위임 구조 사용 | OAuth delegation, service account, developer role 기반 |

## 3. 인증 주체 유형

| 주체 | 설명 |
|------|------|
| `service_account` | Google, GCP 등 서비스 계정 (JSON key) |
| `oauth_delegated_account` | OAuth token으로 위임된 계정 |
| `developer_console_operator` | 개발자 콘솔 운영 전담 계정 |
| `finance_approver` | 결제/송금 승인 전담 계정 |
| `workspace_admin` | Google Workspace, Hiworks 관리자 |
| `api_key_admin` | API key 발급/관리 전담 계정 |
| `public_api_key` | 인증 없이 사용 가능한 공개 API key |
| `unavailable_without_authorized_principal` | 지정 주체 없이 진행 불가 |

## 4. 서비스별 인증 매트릭스

| 서비스 | 권장 인증 방식 | 인증 주체 | 대표님 개입 | 반복 개입 | 공식 위임 가능 |
|--------|--------------|---------|-----------|---------|--------------|
| Naver Search API | API key | `public_api_key` | 최초 1회 | 없음 | O |
| YouTube Data API (read) | API key | `public_api_key` | 최초 1회 | 없음 | O |
| PublicData/NTS API | API key | `public_api_key` | 최초 1회 | 없음 | O |
| Google Drive/Sheets | service account | `service_account` | JSON key 발급 시 1회 | 없음 | O |
| YouTube Analytics | OAuth | `oauth_delegated_account` | 최초 OAuth 승인 1회 | token 만료 시 | O |
| Kakao Developers console | console role | `developer_console_operator` | 계정 설정 시 | 없음 | O |
| Naver Developers console | console role | `developer_console_operator` | 계정 설정 시 | 없음 | O |
| Google Cloud Console | service account / console role | `developer_console_operator` | 계정 설정 시 | 없음 | O |
| Naver Cafe write | OAuth | `oauth_delegated_account` | OAuth 승인 1회 | token 만료 시 | O |
| Kakao Login/OAuth | OAuth | `oauth_delegated_account` | OAuth 승인 1회 | token 만료 시 | O |
| Google Workspace (DWD) | domain-wide delegation | `workspace_admin` | 관리자 설정 1회 | 없음 | 계약 필요 |
| Hiworks | 관리자 API | `workspace_admin` | 관리자 계정 설정 | 없음 | 계약 필요 |
| 법인뱅킹/펌뱅킹 | 법인 API | `finance_approver` | 계약/등록 | 없음 | 계약 필요 |
| YouTube upload | OAuth | `oauth_delegated_account` | OAuth 승인 1회 | token 만료 시 | O |
| SNS posting | OAuth | `oauth_delegated_account` | OAuth 승인 1회 | token 만료 시 | O (승인형) |
| Hometax | 법인 공인인증 | `finance_approver` | 갱신 시 | 인증서 갱신 주기 | 제한적 |
| G2B | 법인 공인인증 | `finance_approver` | 갱신 시 | 인증서 갱신 주기 | 제한적 |

## 5. 대표님 개입 0으로 가능한 항목

- Naver Search API (API key 발급 완료 후)
- YouTube Data API public read (API key)
- PublicData/NTS API (API key)
- Google service account 기반 Drive/Sheets/BigQuery 자동화
- 내부 웹 녹화/렌더링 파이프라인

## 6. 대표님 대신 인증 담당자가 필요한 항목

- Kakao Developers console 설정/권한 신청
- Naver Developers console 설정/권한 신청
- Google Cloud Console 서비스 계정/권한 설정
- YouTube Analytics OAuth 위임
- Naver Cafe write OAuth 위임

## 7. 계약/관리자 설정이 필요한 항목

- Google Workspace domain-wide delegation
- 법인뱅킹/펌뱅킹 API 계약
- Hiworks 관리자 API 계약
- Kakao 비즈니스 권한 (비즈앱/카카오싱크)

## 8. 계속 승인형으로 남길 항목

- 송금 최종 승인
- 결제
- 광고비 집행
- 외부 게시/댓글/업로드
- 삭제
- DB 변경
- 운영 서버 재시작
- git push

## 9. 구현 순서

| 단계 | 작업 키 | 내용 |
|------|---------|------|
| 1 | `DEV-CONSOLE-ROLE-1` | developer_console_operator 역할/권한 체크리스트 |
| 2 | `GOOGLE-SA-1` | Google service account / domain-wide delegation 설계 |
| 3 | `KAKAO-DEV-3R` | Kakao Developers 전용 프로필 기반 세션 재사용 — 앱 목록/설정/권한 확인 |
| 4 | `NAVER-DEV-2` | Naver Developers 콘솔 접속/상태 관찰 |
| 5 | `BANK-AUTH-1` | 법인뱅킹 API 계약 요건 정리 |
| 6 | `SECRET-OPS-1` | secret store / safe env 운영 표준화 |
| 7 | `SESSION-HEALTH-1` | developer console session health check 스크립트 (check_developer_console_sessions.py) |
