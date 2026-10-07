# Naver Live Safety Policy

Updated: 2026-05-13

Naver workflows must not assume an official API is available. The supported
operating model is:

```text
static catalog -> dry-run -> manual/user-visible live read -> approval-gated submit
```

## Default Rule

Naver and SmartStore live browser access is blocked by default.

Live browser access requires:

```text
--live-ok
```

Multi-target live scans additionally require:

```text
--allow-multi-target
```

Without those flags, commands must use stored artifacts, static catalogs, or
dry-run plans.

After a valid login and explicit live approval, faster page reading is allowed
as long as the session remains consistent and no robot/security/monitoring
signal appears. If such a signal appears, adjust by slowing down, narrowing the
scope to the current page, or stopping the live workflow.

Do not advance from one Naver page or section to the next until the current page
is fully implemented or explicitly deferred with a reason. Accuracy and complete
page coverage take priority over speed.

## Stop Signals

Any of these signals immediately stop live automation:

- robot detection text
- captcha or recaptcha selector
- security text such as `보안문자`, `보안 확인`, `본인 확인`
- abnormal access text such as `비정상 접근`, `비정상 활동`
- additional authentication text
- login user mismatch such as `different_user_logged_in`

The stop is recorded as `NAVER_ROBOT_DETECTED` in realtime audit logs when the
page can be inspected.

## Implementation

Safety module:

- `scripts/naver/common/live_safety.py`

Integrated paths:

- `scripts/naver/router.py` for `naver content explore`
- `scripts/naver/common/content.py` before/after content navigation and before surface extraction
- `scripts/smartstore/router.py` before every live SmartStore browser action

## Operational Notes

Do not retry automatically after a robot/security signal. The next step should
be manual browser inspection or offline processing of already downloaded/exported
files. Browser automation remains the last resort for Naver workflows.

Page-by-page rule:

1. Complete current page discovery.
2. Build/update action catalog.
3. Implement prepare/dry-run behavior.
4. Verify audit artifacts.
5. Then move to the next page.

## Common Session Policy

Login/session mismatch is not a Naver-only rule. It is a common site automation
blocker.

- Common policy: `docs/common_login_session_safety_policy_20260513.md`
- Common module: `scripts/site_engine/site_session_safety.py`

Naver live safety uses the common policy first, then applies Naver-specific
robot/captcha/security-signal checks.
