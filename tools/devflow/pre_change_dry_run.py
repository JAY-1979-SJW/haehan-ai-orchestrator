"""Record pre-change dry-run evidence before editing code.

The command is meant to be run after the worktree index and before code edits:

    python scripts/ops/pre_change_dry_run.py --scope smartstore --reason "router update" -- python -m pytest tests/smartstore/test_smartstore_actions.py -q
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
LATEST_PATH = ROOT / "data" / "logs" / "pre_change_dry_run_latest.json"
HISTORY_DIR = ROOT / "data" / "logs" / "pre_change_dry_runs"
WORKTREE_INDEX_PATH = ROOT / "data" / "worktree_change_index_latest.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _git_head() -> str:
    result = subprocess.run(  # noqa: UP022 - 이동 전부터 있던 기존 패턴, 이동과 무관
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _load_worktree_summary() -> dict[str, Any]:
    if not WORKTREE_INDEX_PATH.exists():
        return {}
    try:
        data = json.loads(WORKTREE_INDEX_PATH.read_text(encoding="utf-8"))
        return data.get("summary") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_record(
    *,
    scope: str,
    reason: str,
    command: list[str],
    exit_code: int,
    output: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "status": "ok" if exit_code == 0 else "failed",
        "phase": "before_code_update",
        "scope": scope,
        "reason": reason,
        "command": command,
        "exit_code": exit_code,
        "git_head": _git_head(),
        "worktree_index": str(WORKTREE_INDEX_PATH),
        "worktree_summary": _load_worktree_summary(),
        "output_tail": output[-2000:],
    }


def save_record(record: dict[str, Any], *, latest_path: Path = LATEST_PATH, history_dir: Path = HISTORY_DIR) -> Path:
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = history_dir / f"pre_change_dry_run_{stamp}.json"
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    latest_path.write_text(payload, encoding="utf-8")
    history_path.write_text(payload, encoding="utf-8")
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            "PRE_CHANGE_DRY_RUN_RECORDED",
            site="repo",
            workflow="pre_change_dry_run",
            status=record["status"],
            risk="policy",
            message="pre-change dry-run evidence recorded",
            artifact_path=str(history_path),
            metadata={
                "scope": record.get("scope"),
                "reason": record.get("reason"),
                "command": record.get("command"),
                "exit_code": record.get("exit_code"),
            },
        )
    except Exception:  # noqa: BLE001, S110 - 변경 전 드라이런 증거 기록 — latest/history 파일은 이미 저장 완료된 뒤, 부가적인 실시간 감사 이벤트 전송(emit_event) 실패만 흡수, 기록 자체의 무결성에는 영향 없음.
        pass
    return history_path


def load_latest(path: Path = LATEST_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def latest_ok_for_scope(scope: str, *, path: Path = LATEST_PATH) -> bool:
    record = load_latest(path)
    if not record:
        return False
    if record.get("status") != "ok":
        return False
    return str(record.get("scope") or "") == scope


def run_dry_run(command: list[str], *, scope: str, reason: str) -> tuple[int, Path]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        encoding="utf-8",
    )
    print(result.stdout, end="")
    record = build_record(
        scope=scope, reason=reason, command=command, exit_code=result.returncode, output=result.stdout
    )
    path = save_record(record)
    print(f"pre-change dry-run evidence: {path}")
    return result.returncode, path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and record pre-change dry-run evidence")
    parser.add_argument("--scope", required=True, help="owner/workflow scope, for example smartstore or naver")
    parser.add_argument("--reason", default="", help="why this code change is about to be made")
    parser.add_argument("--check", action="store_true", help="check latest evidence for scope instead of running")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="dry-run command after --")
    args = parser.parse_args()

    if args.check:
        ok = latest_ok_for_scope(args.scope)
        print(f"pre-change dry-run latest scope={args.scope} ok={ok}")
        return 0 if ok else 2

    command = [part for part in args.command if part != "--"]
    if not command:
        print(
            "usage: python tools/devflow/pre_change_dry_run.py --scope <scope> --reason <reason> -- <dry-run command>",
            file=sys.stderr,
        )
        return 2
    exit_code, _path = run_dry_run(command, scope=args.scope, reason=args.reason)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
