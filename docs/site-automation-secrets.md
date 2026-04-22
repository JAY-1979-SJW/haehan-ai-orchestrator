# 사이트 자동화 자격증명 / 세션 파일 정책

## 파일 경로 정책

| 용도 | 경로 | 예 |
|------|------|----|
| 사이트 자격증명 (env 형태) | `secrets/sites/<site_name>.env` | `secrets/sites/example_portal.env` |
| 브라우저 storage state | `secrets/browser_state/<site_name>.json` | `secrets/browser_state/example_portal.json` |
| 스크린샷 | `ai_orchestrator/storage/site_screenshots/<site_name>/` | — |

- `site_name` 은 `^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$` 만 허용 (path traversal 방지).
- 환경변수 override:
  - `SECRETS_ROOT` — 기본값 `<repo>/secrets`
  - `SITES_CREDENTIALS_ROOT` — 기본값 `<SECRETS_ROOT>/sites`
  - `BROWSER_STATE_ROOT` — 기본값 `<SECRETS_ROOT>/browser_state`

## 커밋 금지 (절대)

`.gitignore` 에 다음 경로가 포함되어 있다.

```
secrets/
secrets/sites/
secrets/browser_state/
ai_orchestrator/storage/site_screenshots/
```

- **절대로 실제 비밀번호, 쿠키, storage state 원문을 리포지토리에 커밋하지 않는다.**
- 샘플(`http_users.sample.json` 처럼 placeholder 만 들어있는 파일)만 커밋 대상이다.
- 자격증명이 실수로 staged 되면 `git rm --cached` 로 즉시 제외하고, 리포지토리 history 에서도 제거를 검토한다.

## Graceful Failure

- 자격증명 파일이 없는 경우 → `credentials_present()` 가 `False` 반환, 예외 미발생
- 세션 파일이 없는 경우 → `session_state_present()` 가 `False` 반환, 예외 미발생
- `ExamplePortalConnector.health_check()` 는 두 파일 모두 없을 때 `state="unconfigured"` 로만 응답하고 외부 접속을 하지 않는다.

## 로그/audit 에 남기지 않는 것

다음은 **어떤 레벨에서도 기록하지 않는다.**
- 비밀번호 원문
- 쿠키 원문 (Set-Cookie 헤더 포함)
- Authorization 헤더 원문 (`Basic ...`, `Bearer ...` raw)
- storage state JSON 원문
- raw session token

audit 로그에는 다음 같은 **비민감 필드만** 남긴다.
- `event_type` (예: `SITE_HEALTH_CHECK`, `SITE_TASK_DRY_RUN`, `SITE_CONNECTORS_LISTED`)
- `task_id`, `target_site`, `action_type`, `actor`, `role`
- `decision`, `duration_ms`, `error_code`

## 자격증명 회전 (운영 원칙)

- 자격증명이 유출된 정황이 있으면 즉시 새 파일로 교체 + 기존 파일 삭제
- 회전 이력은 별도 운영 문서에 기록 (코드 base 에 남기지 않음)
- 공유 계정은 최소화하고, 가능하면 사이트별로 분리된 서비스 계정을 사용
- OWASP 권장대로 중앙 관리 가능한 secrets 저장소(예: vault)로의 이관은 향후 단계에서 검토

## 이번 단계의 한계

- 실제 자동 로그인/자동 제출 코드는 포함하지 않는다.
- CAPTCHA/MFA 우회를 하지 않는다.
- session state 파일은 **최초에 수동으로 작성된 storage state** 만 사용 (Playwright 공식 문서 권장 방식과 동일한 형식).
- `execute()` 는 1단계에서 `NOT_IMPLEMENTED` 가 기본이며, 향후 안전한 read-only action 부터 단계적으로 개방한다.
