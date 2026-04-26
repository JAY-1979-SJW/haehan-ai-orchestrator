"""SESSION-HEALTH-1 — Developer console session health check.

전용 브라우저 프로필 기반 세션 상태를 점검한다.
로그인되어 있으면 READY_LOGGED_IN, 만료되었으면 NEEDS_REAUTH 기록 +
재개 가능한 pending task 파일을 생성한다.

허용:
  - 전용 프로필 기반 세션 재사용
  - 로그인 상태 자동 점검 (텍스트/타이틀/링크 분석)
  - pending task JSON 생성 (NEEDS_REAUTH 시)
  - 결과 JSON/MD 저장

절대 금지:
  - 비밀번호/OTP 자동 입력
  - 쿠키/session/storage_state 추출
  - password input value 읽기
  - API key / Client Secret 원문 저장
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from local_agent.browser_observer import observe_public_browser_page

_CONSOLES: list[dict[str, str]] = [
    {
        "name": "kakao_developers",
        "profile_name": "kakao_developer_console",
        "target_url": "https://developers.kakao.com/console/app",
        "display": "Kakao Developers",
    },
    {
        "name": "naver_developers",
        "profile_name": "naver_developer_console",
        "target_url": "https://developers.naver.com/apps/#/list",
        "display": "Naver Developers",
    },
    {
        "name": "google_cloud_console",
        "profile_name": "google_cloud_console",
        "target_url": "https://console.cloud.google.com/",
        "display": "Google Cloud Console",
    },
]

_LOGIN_SIGNALS: dict[str, tuple[str, ...]] = {
    "kakao_developers": (
        "로그인", "sign in", "signin", "login", "카카오 계정",
        "이메일 또는 전화번호", "비밀번호",
    ),
    "naver_developers": (
        "로그인", "sign in", "네이버 아이디로 로그인", "id", "비밀번호",
    ),
    "google_cloud_console": (
        "sign in", "google accounts", "choose an account", "로그인",
    ),
}

_AUTH_SIGNALS: dict[str, tuple[str, ...]] = {
    "kakao_developers": (
        "로그아웃", "logout", "내 애플리케이션", "앱 목록", "마이앱",
    ),
    "naver_developers": (
        "로그아웃", "logout", "내 애플리케이션", "application list", "앱 목록",
    ),
    "google_cloud_console": (
        "dashboard", "프로젝트", "project", "console.cloud.google.com",
        "apis & services", "iam",
    ),
}


def _classify_session(console_name: str, result: dict) -> str:
    """Returns READY_LOGGED_IN | NEEDS_REAUTH | UNKNOWN | BLOCKED."""
    if not result.get("success") and result.get("error_code") == "BLOCKED":
        return "BLOCKED"

    text = (result.get("text_excerpt") or "").lower()
    title = (result.get("title") or "").lower()
    page_state = result.get("page_state", "")
    combined = text + " " + title

    login_tokens = _LOGIN_SIGNALS.get(console_name, ())
    auth_tokens = _AUTH_SIGNALS.get(console_name, ())

    if page_state == "login_required" or any(t.lower() in combined for t in login_tokens):
        return "NEEDS_REAUTH"
    if any(t.lower() in combined for t in auth_tokens):
        return "READY_LOGGED_IN"
    return "UNKNOWN"


def _build_pending_task(console: dict, ts: str, pending_dir: Path) -> Path:
    task_id = f"{console['name']}_{ts}"
    task = {
        "task_id": task_id,
        "console": console["name"],
        "target_url": console["target_url"],
        "profile_name": console["profile_name"],
        "status": "NEEDS_REAUTH",
        "resume_command": (
            f"python scripts/check_developer_console_sessions.py "
            f"--console {console['name']} --json"
        ),
        "next_action_after_login": "observe_apps",
        "created_at": ts,
        "warnings": [
            "재인증 후 이 파일의 status를 READY_AFTER_REAUTH로 변경하고 resume_command를 실행한다.",
            "비밀번호/쿠키/session 추출 금지.",
        ],
    }
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / f"{task_id}.json"
    path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def check_one(console: dict, out_base: Path, ts: str, timeout_ms: int) -> dict[str, Any]:
    raw = observe_public_browser_page(
        console["target_url"],
        timeout_ms=timeout_ms,
        max_text_chars=4_000,
        capture_screenshot=False,
        wait_until="networkidle",
    )
    status = _classify_session(console["name"], raw)
    pending_task_path: str | None = None

    if status == "NEEDS_REAUTH":
        pending_dir = out_base / "pending_auth_tasks"
        p = _build_pending_task(console, ts, pending_dir)
        pending_task_path = str(p)

    return {
        "console": console["name"],
        "display": console["display"],
        "profile_name": console["profile_name"],
        "target_url": console["target_url"],
        "status": status,
        "reachable": bool(raw.get("success") or raw.get("status_code") in (200, 301, 302)),
        "pending_task_path": pending_task_path,
        "warnings": list(raw.get("warnings") or []),
        "checked_at": ts,
    }


def check_all(
    out_dir: str = "runs/developer_console",
    timeout_ms: int = 20_000,
    consoles: list[dict] | None = None,
) -> dict[str, Any]:
    if consoles is None:
        consoles = _CONSOLES
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_base = Path(out_dir)
    out_base.mkdir(parents=True, exist_ok=True)

    results = [check_one(c, out_base, ts, timeout_ms) for c in consoles]

    summary: dict[str, Any] = {
        "checked_at": ts,
        "consoles": results,
        "summary": {
            "READY_LOGGED_IN": sum(1 for r in results if r["status"] == "READY_LOGGED_IN"),
            "NEEDS_REAUTH": sum(1 for r in results if r["status"] == "NEEDS_REAUTH"),
            "UNKNOWN": sum(1 for r in results if r["status"] == "UNKNOWN"),
            "BLOCKED": sum(1 for r in results if r["status"] == "BLOCKED"),
        },
        "security": {
            "password_stored": False,
            "cookie_exported": False,
            "password_input_read": False,
            "otp_stored": False,
            "session_exported": False,
        },
    }

    json_path = out_base / f"session_health_{ts}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out_base / f"session_health_{ts}.md"
    md_path.write_text(_build_md(summary), encoding="utf-8")

    summary["output_json"] = str(json_path)
    summary["output_md"] = str(md_path)
    return summary


def _build_md(summary: dict) -> str:
    ts = summary["checked_at"]
    lines = [
        "# Developer Console Session Health",
        "",
        f"checked_at: {ts}",
        "",
        "| 콘솔 | 상태 | 재사용 가능 | pending_task |",
        "|------|------|------------|--------------|",
    ]
    for r in summary["consoles"]:
        reusable = "O" if r["status"] == "READY_LOGGED_IN" else "-"
        pending = r.get("pending_task_path") or "-"
        lines.append(f"| {r['display']} | {r['status']} | {reusable} | {pending} |")

    lines += [
        "",
        "## 요약",
        "",
    ]
    for k, v in summary["summary"].items():
        lines.append(f"- {k}: {v}")

    lines += [
        "",
        "## 보안 확인",
        "",
        "- 비밀번호 저장: 없음",
        "- 쿠키/session export: 없음",
        "- password input 읽기: 없음",
        "- OTP/TOTP seed 저장: 없음",
        "- session_state export: 없음",
        "",
        "## NEEDS_REAUTH 처리",
        "",
        "세션 만료 콘솔은 `runs/developer_console/pending_auth_tasks/` 하위에 재개 가능한 task 파일이 생성된다.",
        "재인증 완료 후 해당 파일의 `resume_command`를 실행하면 작업이 자동 재개된다.",
        "대표님에게 터미널 실행, 파일 확인, 결과 붙여넣기를 요구하지 않는다.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="SESSION-HEALTH-1 — Developer console session health check")
    parser.add_argument("--out-dir", default="runs/developer_console")
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--console", help="특정 콘솔만 점검 (kakao_developers|naver_developers|google_cloud_console)")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    consoles = _CONSOLES
    if args.console:
        consoles = [c for c in _CONSOLES if c["name"] == args.console]
        if not consoles:
            print(f"[ERROR] 알 수 없는 콘솔: {args.console}", file=sys.stderr)
            return 1

    result = check_all(
        out_dir=args.out_dir,
        timeout_ms=args.timeout_ms,
        consoles=consoles,
    )

    print(f"[결과] {result.get('output_json')}", file=sys.stderr)
    print(f"[결과] {result.get('output_md')}", file=sys.stderr)

    if args.json_output:
        print(json.dumps(
            {
                "checked_at": result["checked_at"],
                "summary": result["summary"],
                "consoles": [
                    {"console": r["console"], "status": r["status"], "reachable": r["reachable"]}
                    for r in result["consoles"]
                ],
            },
            ensure_ascii=False, indent=2,
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
