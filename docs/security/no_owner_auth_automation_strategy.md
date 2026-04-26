# 대표님 무인증 자동화 전략

## 1. 목표

대표님이 로그인/2FA/OTP/인증서 입력을 하지 않는 자동화 구조 정의.
AI가 인증을 우회하거나 저장된 비밀번호를 수집하는 구조는 금지.
공식 위임, 서비스계정, OAuth token, API key, developer console operator, finance approver 구조로 해결.

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
| 3 | `KAKAO-DEV-2` | Kakao Developers 콘솔 접속/상태 관찰 |
| 4 | `NAVER-DEV-2` | Naver Developers 콘솔 접속/상태 관찰 |
| 5 | `BANK-AUTH-1` | 법인뱅킹 API 계약 요건 정리 |
| 6 | `SECRET-OPS-1` | secret store / safe env 운영 표준화 |
