"""GitHub 저장소에 배포 Webhook을 자동 등록한다.

실행:
  python scripts/ops/setup_github_webhook.py --check    # 현재 webhook 목록 확인
  python scripts/ops/setup_github_webhook.py --register # webhook 신규 등록
  python scripts/ops/setup_github_webhook.py --delete <id>  # webhook 삭제

필요 환경변수:
  GITHUB_TOKEN          — repo webhook 권한이 있는 Personal Access Token
  DEPLOY_WEBHOOK_SECRET — HMAC 서명 시크릿 (서버 .env 와 동일해야 함)

보안 원칙:
  - GITHUB_TOKEN, DEPLOY_WEBHOOK_SECRET 원문 출력 금지
  - 등록 후 secret 은 GitHub API 응답에서 마스킹됨
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REPO_OWNER = "JAY-1979-SJW"
REPO_NAME = "haehan-ai-orchestrator"
WEBHOOK_URL = "https://haehan-ai.kr/orchestrator/api/v1/deploy/webhook"
EVENTS = ["push"]
GITHUB_API = "https://api.github.com"


def _token() -> str:
    t = os.environ.get("GITHUB_TOKEN", "")
    if not t:
        sys.exit("ERROR: GITHUB_TOKEN 환경변수가 설정되지 않았습니다.")
    return t


def _secret() -> str:
    s = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
    if not s:
        sys.exit("ERROR: DEPLOY_WEBHOOK_SECRET 환경변수가 설정되지 않았습니다.")
    return s


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", "replace")
        sys.exit(f"GitHub API 오류 {e.code}: {body_text[:300]}")


def list_webhooks() -> list[dict]:
    return _request("GET", f"/repos/{REPO_OWNER}/{REPO_NAME}/hooks")


def register_webhook() -> dict:
    secret = _secret()
    payload = {
        "name": "web",
        "active": True,
        "events": EVENTS,
        "config": {
            "url": WEBHOOK_URL,
            "content_type": "json",
            "secret": secret,
            "insecure_ssl": "0",
        },
    }
    result = _request("POST", f"/repos/{REPO_OWNER}/{REPO_NAME}/hooks", payload)
    return result


def delete_webhook(hook_id: int) -> None:
    url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{hook_id}"
    req = urllib.request.Request(
        url,
        method="DELETE",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except urllib.error.HTTPError as e:
        sys.exit(f"삭제 실패 {e.code}: {e.read().decode()[:200]}")


def cmd_check() -> None:
    hooks = list_webhooks()
    if not hooks:
        print("등록된 webhook 없음.")
        return
    for h in hooks:
        cfg = h.get("config", {})
        active = "✅" if h.get("active") else "❌"
        print(f"  id={h['id']} {active} url={cfg.get('url')} events={h.get('events')}")


def cmd_register() -> None:
    # 중복 체크
    hooks = list_webhooks()
    for h in hooks:
        if h.get("config", {}).get("url") == WEBHOOK_URL:
            print(f"이미 등록됨: id={h['id']} url={WEBHOOK_URL}")
            return

    result = register_webhook()
    print(f"webhook 등록 완료: id={result.get('id')} url={WEBHOOK_URL}")
    print("secret_values_output: False")


def cmd_delete(hook_id: int) -> None:
    delete_webhook(hook_id)
    print(f"webhook {hook_id} 삭제 완료.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GitHub webhook 관리")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="등록된 webhook 목록 확인")
    g.add_argument("--register", action="store_true", help="webhook 신규 등록")
    g.add_argument("--delete", type=int, metavar="ID", help="webhook 삭제")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.check:
        cmd_check()
    elif args.register:
        cmd_register()
    elif args.delete is not None:
        cmd_delete(args.delete)


if __name__ == "__main__":
    main()
