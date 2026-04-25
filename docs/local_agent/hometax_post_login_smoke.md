# 홈택스 post-login smoke runner (F-4G-3B)

홈택스에 대표님이 직접 로그인 + 인증서 + 보안프로그램 설치 + 메뉴 이동을 끝낸
*후* 화면을, AI 가 read-only 로 한 번만 관찰하고 controlled action plan 을
표준 JSON / MD 파일로 저장하는 전용 smoke 실행기입니다.

본 단계 이전에는 대표님이 다음과 같은 긴 한 줄을 직접 복붙해야 했습니다:

```bash
python -c "from local_agent.browser_manual_handoff import observe_after_user_ready; ..."
```

이제는 본 스크립트 한 줄로 동일 흐름이 재현됩니다.

## 실행 명령

```bash
python scripts/run_hometax_post_login_smoke.py
```

기본값:
- `--url https://www.hometax.go.kr/`
- `--user-ready-seconds 120`     (대표님 수동 로그인/인증/보안설치 대기)
- `--dwell-after-capture-seconds 10`
- `--max-text-chars 10000`
- `--out-dir runs/local_agent`
- `--warmup-url https://example.com/`     (F-4G-3E)
- `--goto-retries 2`                       (F-4G-3E)
- `--goto-retry-delay-seconds 1.5`         (F-4G-3E)
- `--goto-timeout-ms 90000`                (F-4G-3E)

옵션 예시:

```bash
# 매출 세금계산서 메뉴까지 직접 이동한 다음 60초 안에 캡처
python scripts/run_hometax_post_login_smoke.py \
    --user-ready-seconds 60 \
    --max-text-chars 20000

# 결과 JSON 을 콘솔에도 출력
python scripts/run_hometax_post_login_smoke.py --print-json

# 결과를 별도 폴더에 저장
python scripts/run_hometax_post_login_smoke.py --out-dir runs/smoke_2026_04_25

# warmup 비활성화 (drift 진단용)
python scripts/run_hometax_post_login_smoke.py --no-warmup

# goto 재시도 횟수를 더 늘려야 할 때
python scripts/run_hometax_post_login_smoke.py \
    --goto-retries 3 --user-ready-seconds 120 --print-json
```

## F-4G-3E — fresh hometax goto reset 대응

진단 (`runs/local_agent/diagnostics/goto_diagnostic_*.json`) 결과 요약:

- `example.com` / `google.com` 은 `domcontentloaded` / `load` / `networkidle`
  모두 정상 → **Chromium 미설치 / 일반 네트워크 문제 아님**.
- `https://www.hometax.go.kr/` 는 fresh Chromium 첫 접속에서
  `net::ERR_CONNECTION_RESET` 가 발생할 수 있음.
- 그러나 `wait_until="networkidle"` 자체는 2.94 초 만에 성공 → `wait_until`
  변경은 불필요.

따라서 본 runner 의 기본 대응은 **warmup + retry** 입니다.

- `--warmup-url https://example.com/` : target URL 로 navigate 하기 전에
  무관한 URL 1회 navigate 로 Chromium 의 첫-접속 reset 확률을 낮춤.
- `--goto-retries 2` : target URL goto 를 최대 2회 시도. 1회 실패 시
  `--goto-retry-delay-seconds` 만큼 대기 후 재시도.
- 결과 JSON / MD `summary` 에 다음이 항상 기록됨:
  - `warmup_attempted`, `warmup_success`, `warmup_url`
  - `goto_attempts_used`, `goto_retries`,
    `goto_retry_delay_seconds`, `goto_timeout_ms`

문제가 지속되면 다음 명령으로 재시도 횟수를 늘려보십시오:

```bash
python scripts/run_hometax_post_login_smoke.py \
    --goto-retries 3 --user-ready-seconds 120 --print-json
```

> ⚠️ 경고: warmup / retry 로직은 자동 클릭/입력/쿠키 접근을 *추가하지 않습니다*.
> 여전히 `observe_after_user_ready` 와 동일하게 read-only 만 수행합니다.

## 대표님이 직접 로그인해야 하는 이유

홈택스 로그인은 다음을 요구합니다:
- 공동인증서 / 금융인증서 / 간편인증 / 사업자인증서 등 사용자 본인만 처리 가능한
  인증.
- 인증서 비밀번호 입력 (보안키패드 / 가상키보드 사용).
- 보안프로그램 (AhnLab, INISafe, MagicLine, TouchEn 등) 설치/실행.
- OTP / SMS 추가 인증.

이 모든 것은 **사용자 본인** 의 책임이며, AI 가 자동화할 경우 정책/보안/감사
관점에서 절대 허용되지 않습니다.

## AI 가 절대 하지 않는 동작

본 runner 는 다음을 절대 수행하지 않습니다 (`local_agent.browser_manual_handoff`
의 `observe_after_user_ready` 와 동일 정책):

- `page.click` / `page.fill` / `page.type` / `page.press`
- `page.keyboard.*` / `page.mouse.*`
- `page.set_input_files` / `page.select_option`
- 폼 `submit` / 파일 다운로드 / 보안프로그램 자동 설치
- ID / PW / 인증서 비밀번호 / OTP / 보안값 입력
- 쿠키 / `storage_state` / `localStorage` / `sessionStorage` 접근
- input value / textarea value 수집
- 실제 controlled action 실행 (오직 plan 만 만든다)

## 결과 파일 위치

스크립트가 종료되면 다음 두 파일이 생성됩니다:

```
runs/local_agent/hometax_post_login_smoke_YYYYMMDD_HHMMSS.json
runs/local_agent/hometax_post_login_smoke_YYYYMMDD_HHMMSS.md
```

JSON 구조:

```jsonc
{
  "target_url": "https://www.hometax.go.kr/",
  "observer": { /* observe_after_user_ready 결과 전체 */ },
  "plan":     { /* build_hometax_controlled_action_plan 결과 전체 */ },
  "summary": {
    "success": true,
    "title": "홈택스 - ...",
    "final_url_host_path": "www.hometax.go.kr/...",
    "page_state": "authenticated",
    "text_length": 12345,
    "links_count": 80,
    "buttons_count": 15,
    "forms_count": 3,
    "inputs_count": 10,
    "manual_action_required": false,
    "safe_read_candidates_count": 12,
    "download_candidates_count": 3,
    "blocked_candidates_count": 5,
    "warnings_count": 0,
    "warmup_attempted": true,
    "warmup_success": true,
    "warmup_url": "https://example.com/",
    "goto_attempts_used": 1,
    "goto_retries": 2,
    "goto_retry_delay_seconds": 1.5,
    "goto_timeout_ms": 90000
  }
}
```

MD 는 같은 정보를 사람이 빠르게 읽을 수 있는 형태로 정리하며, safe_read /
download / blocked 후보 상위 10개와 약식 PASS/WARN/FAIL 판정을 포함합니다.

## 약식 판정 기준 (PASS/WARN/FAIL)

- **PASS** — observer.success=True 이고 safe_read 또는 download 후보가 1개 이상.
- **WARN** — observer.success=True 이지만 후보가 모두 비어있음 (대표님이 더 깊은
  메뉴까지 이동해 다시 캡처가 필요한 경우).
- **FAIL** — observer 자체가 실패 (URL_INVALID / FORBIDDEN_ENV_PRESENT /
  GOTO_FAILED / BROWSER_DEPENDENCY_MISSING 등).

## 다음 단계 (F-4G-4) 로 넘어가는 기준

본 단계 (F-4G-3B) 의 PASS 기준:

1. 대표님 PC 에서 `python scripts/run_hometax_post_login_smoke.py` 가 정상 종료.
2. `runs/local_agent/hometax_post_login_smoke_*.json` / `.md` 가 생성됨.
3. JSON 의 `summary.success == true`.
4. JSON 의 `plan.safe_read_candidates` 또는 `plan.download_candidates` 에 후보가
   1개 이상 존재 (즉 약식 판정이 **PASS**).
5. 보안 금지 동작 (page.click / cookies / storage_state / localStorage 등) 이
   runner 코드에서 발견되지 않음 (회귀 테스트 통과).

위 5개를 만족하면 F-4G-4 (실제 controlled action 실행 단계의 entry-point 검증)
로 진행합니다.
