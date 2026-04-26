# Kakao Developers 자동화 전략

## 1. 목표

Kakao Developers에서 앱 권한 신청, 동의항목 설정, 비즈앱/카카오싱크/카카오 로그인 관련 권한 신청을
Claude Code가 자동으로 진행할 수 있는 구조를 설계한다.

## 2. 자동화 대상

| feature_key | purpose | official_path | required_permission | business_review_needed | auto_fill_allowed | auto_submit_allowed | risk_level |
|-------------|---------|--------------|--------------------|-----------------------|-------------------|---------------------|-----------|
| `platform_web_domain` | 웹 플랫폼 도메인 등록 | 앱 설정 > 플랫폼 | developer_console_operator | N | Y | Y | LOW |
| `redirect_uri` | Redirect URI 등록 | 카카오 로그인 > Redirect URI | developer_console_operator | N | Y | Y | LOW |
| `kakao_login_enable` | 카카오 로그인 활성화 | 카카오 로그인 > 활성화 | developer_console_operator | N | Y | Y | LOW |
| `consent_profile` | 닉네임/프로필 동의항목 | 카카오 로그인 > 동의항목 | developer_console_operator | N | Y | Y | LOW |
| `consent_email` | 이메일 동의항목 (선택) | 카카오 로그인 > 동의항목 | developer_console_operator | N | Y | Y | LOW |
| `consent_phone` | 전화번호 동의항목 | 카카오 로그인 > 동의항목 | 비즈앱 + 비즈니스 인증 | Y | Y | N (심사 후) | MEDIUM |
| `kakao_sync` | 카카오싱크 | 카카오싱크 설정 | 비즈앱 + 계약 | Y | Y | N (계약 필요) | HIGH |
| `biz_app_conversion` | 비즈앱 전환 | 앱 설정 > 비즈앱 | developer_console_operator | Y | Y | Y | MEDIUM |
| `biz_channel_link` | 비즈니스 채널 연결 | 카카오톡 채널 > 연결 | developer_console_operator | N | Y | Y | LOW |
| `client_secret_enable` | Client Secret 활성화 | 앱 설정 > 보안 | developer_console_operator | N | Y | Y | MEDIUM |
| `message_api` | 메시지 API | 카카오 로그인 > 동의항목 | 비즈앱 | Y | Y | N (심사 후) | MEDIUM |
| `channel_message_api` | 카카오톡 채널 메시지 | 채널 관리자센터 | 비즈니스 채널 | Y | Y | N (심사 후) | HIGH |
| `moment_api` | 카카오모먼트/광고 API | 광고 플랫폼 | 별도 계약 | Y | N | N | HIGH |

## 3. 자동화 금지 대상

| 항목 | 이유 |
|------|------|
| 앱 삭제 | APPROVAL_REQUIRED — 복구 불가 |
| Client Secret 재발급/폐기 | APPROVAL_REQUIRED — 운영 영향 |
| 쿠키/session 추출 | BLOCKED — 보안 정책 |
| 비밀번호 읽기 | BLOCKED — 보안 정책 |
| 광고비 직접 집행 | APPROVAL_REQUIRED — 금전 관련 |
| 사업자 정보 변경 | APPROVAL_REQUIRED — 법적 영향 |

## 4. 권한 신청 흐름

```
1. 콘솔 접속 (developer_console_operator 주체)
2. 앱 선택
3. 신청 대상 feature 확인
4. 신청서 자동 작성 (auto_fill_allowed=Y)
5. 심사 자료 첨부 (business_review_needed=Y 인 경우)
6. 제출 (auto_submit_allowed=Y)
7. 심사 상태 모니터링
8. 반려 시 → 보완 자료 작성 → 재신청
```

## 5. 필요한 입력 자료

- 앱 이름 (app_name)
- 앱 ID (app_id)
- 서비스 목적 설명 (purpose_text)
- 사업자등록번호 (비즈앱 전환 시)
- 카카오 비즈니스 채널 ID (채널 연결 시)
- 플랫폼 도메인 목록
- Redirect URI 목록

## 6. 자동 생성할 심사 자료

- 서비스 목적 기술서 (purpose_text 기반 자동 작성)
- 동의항목 수집 목적 명세서
- 개인정보 처리방침 URL
- 서비스 화면 캡처 (내부 URL 기반 자동 촬영)

## 7. 브라우저 자동화 경계

| 허용 | 금지 |
|------|------|
| 콘솔 URL 직접 접근 | 로그인 자격증명 입력 |
| 폼 자동 작성 | 쿠키/session 추출 |
| 버튼 클릭 (저장/제출) | 비밀번호 읽기 |
| 상태 확인 (심사 진행/완료/반려) | Client Secret 원문 출력 |
| 스크린샷 (심사 자료용) | 광고비 결제 클릭 |

## 8. Secret 처리 원칙

- REST API Key, JavaScript Key, Admin Key → secret store에 저장
- Client Secret → safe env setter로만 등록, 원문 출력 금지
- Admin Key → 서버 전용, 클라이언트 노출 금지

## 9. 작업 큐 설계

```json
{
  "task_type": "kakao_permission_request",
  "app_name": "...",
  "app_id": "...",
  "feature_key": "kakao_login_profile",
  "requested_permissions": ["profile_nickname", "profile_image"],
  "purpose_text": "...",
  "required_documents": ["privacy_policy_url", "service_screenshot"],
  "auto_submit": true,
  "requires_auth_principal": "developer_console_operator",
  "forbidden_actions": [
    "delete_app",
    "regenerate_secret",
    "read_cookies",
    "export_session"
  ]
}
```

## 10. 단계별 구현 계획

| 단계 | 작업 키 | 내용 | 상태 |
|------|---------|------|------|
| 1 | `KAKAO-DEV-1` | 전략 문서 작성 (본 문서) | DONE |
| 2 | `KAKAO-DEV-2` | Kakao Developers 콘솔 접속/로그인 상태 관찰 | READY |
| 3 | `KAKAO-DEV-3` | 앱 설정 상태 관찰 (platform, redirect URI, login 활성화) | READY |
| 4 | `KAKAO-DEV-4` | 권한 신청서 draft builder | READY |
| 5 | `KAKAO-DEV-5` | 권한 신청서 제출 자동화 | NEEDS_AUTH_PRINCIPAL |
| 6 | `KAKAO-DEV-6` | 심사 상태 모니터링 | NEEDS_AUTH_PRINCIPAL |
