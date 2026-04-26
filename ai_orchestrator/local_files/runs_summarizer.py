"""LOCAL-FS-3 — runs/ 최근 결과 자동 요약.

작업군별 최신 JSON 결과를 읽어 PASS/WARN/FAIL 및 next_actions를 요약한다.

분류 규칙:
  FAIL  : status in {BLOCKED, failed} | security.* any True
  WARN  : status in {NEEDS_REAUTH, UNKNOWN} | warnings[] non-empty
          | ffmpeg_available == false | review_required == true | mode == "dry_run"
  PASS  : 위 조건 없음

절대 금지:
  - .env / secrets / browser_state 원문 읽기·출력
  - API key / token / password 원문 출력 (redact_sensitive_text 항상 적용)
"""
from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_orchestrator.local_files.file_indexer import (
    normalize_root,
    redact_sensitive_text,
)

# ── 작업군별 glob 패턴 ────────────────────────────────────────────────────

GROUPS: dict[str, list[str]] = {
    "developer_console": ["runs/developer_console/**/*.json"],
    "video":             ["runs/video/*.json", "runs/video/worker/**/*.json",
                          "runs/video/edits/**/*.json", "runs/video/tts/**/*.json",
                          "runs/video/subtitles/**/*.json", "runs/video/smoke/**/*.json",
                          "runs/video/internal_smoke/**/*.json"],
    "render":            ["runs/video/render/**/*.json"],
    "local_files":       ["runs/local_files/*.json"],
    "local_agent":       ["runs/local_agent/**/*.json"],
    "naver":             ["runs/naver/**/*.json"],
    "youtube":           ["runs/youtube/**/*.json"],
    "content":           ["runs/content/**/*.json"],
}

# ── 보안 제외 경로 ────────────────────────────────────────────────────────

_SKIP_PATH_PARTS = {"secrets", ".env", "browser_state"}

_SKIP_GLOBS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.sqlite", "*.db")

_STATUS_PRIORITY = {"FAIL": 2, "WARN": 1, "PASS": 0}


def _is_safe_path(path: Path) -> bool:
    """secrets / .env / browser_state 경로 차단."""
    for part in path.parts:
        if part in _SKIP_PATH_PARTS:
            return False
    name = path.name
    for g in _SKIP_GLOBS:
        if fnmatch.fnmatch(name, g):
            return False
    return True


# ── 파일 탐색 ─────────────────────────────────────────────────────────────

def find_latest_files(root: Path, group: str, max_files: int = 3) -> list[Path]:
    """주어진 작업군 glob 패턴에서 최신 max_files개 JSON 파일 반환."""
    patterns = GROUPS.get(group, [])
    found: list[Path] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and _is_safe_path(path):
                found.append(path)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # recent_runs_summary 자기 자신은 제외
    found = [f for f in found if "recent_runs_summary" not in f.name]
    return found[:max_files]


# ── JSON 로드 ─────────────────────────────────────────────────────────────

def load_run_json(path: Path) -> dict[str, Any] | None:
    """JSON 파일을 로드한다. 실패 시 None 반환."""
    if not _is_safe_path(path):
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None


# ── PASS/WARN/FAIL 분류 ───────────────────────────────────────────────────

def classify_status(data: dict[str, Any]) -> tuple[str, list[str]]:
    """PASS/WARN/FAIL 및 감지 신호 목록 반환."""
    signals: list[str] = []
    status = "PASS"

    def _upgrade(level: str, signal: str) -> None:
        nonlocal status
        signals.append(signal)
        if _STATUS_PRIORITY[level] > _STATUS_PRIORITY[status]:
            status = level

    # security block — True 항목 있으면 FAIL
    security = data.get("security") or {}
    if isinstance(security, dict):
        for key, val in security.items():
            if val is True:
                _upgrade("FAIL", f"security.{key}=true")

    # status 필드 (문자열)
    top_status = data.get("status", "")
    if isinstance(top_status, str):
        s = top_status.upper()
        if s in ("BLOCKED", "FAILED"):
            _upgrade("FAIL", f"status={top_status}")
        elif s in ("NEEDS_REAUTH", "UNKNOWN"):
            _upgrade("WARN", f"status={top_status}")
        elif s == "READY_LOGGED_IN":
            pass  # PASS

    # consoles[] (developer_console session_health)
    consoles = data.get("consoles") or []
    if isinstance(consoles, list):
        counts: dict[str, int] = {}
        for c in consoles:
            if not isinstance(c, dict):
                continue
            cs = (c.get("status") or "").upper()
            counts[cs] = counts.get(cs, 0) + 1
        for cs, cnt in counts.items():
            if cs in ("BLOCKED", "FAILED"):
                _upgrade("FAIL", f"console.status={cs}: {cnt}")
            elif cs in ("NEEDS_REAUTH", "UNKNOWN"):
                _upgrade("WARN", f"console.status={cs}: {cnt}")

    # summary block (developer_console)
    summary_block = data.get("summary") or {}
    if isinstance(summary_block, dict):
        for key in ("BLOCKED", "FAILED"):
            if summary_block.get(key, 0) > 0:
                _upgrade("FAIL", f"summary.{key}={summary_block[key]}")
        for key in ("NEEDS_REAUTH", "UNKNOWN"):
            if summary_block.get(key, 0) > 0:
                _upgrade("WARN", f"summary.{key}={summary_block[key]}")

    # warnings[]
    warnings = data.get("warnings") or []
    if isinstance(warnings, list) and warnings:
        _upgrade("WARN", f"warnings: {len(warnings)}개")

    # ffmpeg_available
    if data.get("ffmpeg_available") is False:
        _upgrade("WARN", "ffmpeg_available=false")

    # review_required
    if data.get("review_required") is True:
        _upgrade("WARN", "review_required=true")

    # mode == "dry_run"
    if data.get("mode") == "dry_run":
        _upgrade("WARN", "mode=dry_run")

    # render_items[] blocked
    render_items = data.get("render_items") or []
    if isinstance(render_items, list):
        blocked = sum(1 for r in render_items if isinstance(r, dict) and r.get("status") == "blocked")
        if blocked > 0:
            _upgrade("WARN", f"render_items.blocked: {blocked}개")

    return status, signals


# ── next_actions 추출 ──────────────────────────────────────────────────────

def extract_next_actions(data: dict[str, Any]) -> list[str]:
    """next_actions 필드 추출 (redaction 적용)."""
    actions: list[str] = []

    raw = data.get("next_actions") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                actions.append(redact_sensitive_text(item))
            elif isinstance(item, dict):
                label = item.get("action") or item.get("label") or item.get("description") or str(item)
                actions.append(redact_sensitive_text(str(label)))

    # console별 pending_task_path가 있으면 액션 추가
    consoles = data.get("consoles") or []
    if isinstance(consoles, list):
        for c in consoles:
            if not isinstance(c, dict):
                continue
            cs = (c.get("status") or "").upper()
            name = c.get("display") or c.get("console") or ""
            if cs in ("NEEDS_REAUTH", "UNKNOWN", "BLOCKED"):
                actions.append(f"{name}: 재인증 필요 ({cs})")

    return actions[:20]


# ── 그룹 요약 ─────────────────────────────────────────────────────────────

def summarize_group(
    root: Path,
    group: str,
    max_files: int = 3,
) -> dict[str, Any]:
    """단일 작업군 요약 dict 반환."""
    files = find_latest_files(root, group, max_files=max_files)
    if not files:
        return {
            "status": "PASS",
            "latest_file": None,
            "latest_ts": None,
            "signals": [],
            "next_actions": [],
            "action_required": False,
            "file_count": 0,
        }

    latest = files[0]
    data = load_run_json(latest) or {}

    status, signals = classify_status(data)
    next_actions = extract_next_actions(data)

    # ts 추출 (파일명에서)
    ts = data.get("summarized_at") or data.get("searched_at") or data.get(
        "generated_at") or data.get("checked_at") or ""

    return {
        "status": status,
        "latest_file": str(latest.relative_to(root)).replace("\\", "/"),
        "latest_ts": ts,
        "signals": signals,
        "next_actions": next_actions,
        "action_required": bool(next_actions) or status in ("WARN", "FAIL"),
        "file_count": len(files),
    }


# ── 전체 요약 ─────────────────────────────────────────────────────────────

def summarize_all_groups(
    root: str | Path,
    max_files_per_group: int = 3,
    groups: list[str] | None = None,
) -> dict[str, Any]:
    """모든(또는 선택) 작업군 요약 반환."""
    root_path = normalize_root(root)
    target_groups = groups or list(GROUPS.keys())

    overall_priority = 0
    overall_status = "PASS"
    group_results: dict[str, Any] = {}
    all_next_actions: list[str] = []

    for g in target_groups:
        summary = summarize_group(root_path, g, max_files=max_files_per_group)
        group_results[g] = summary
        prio = _STATUS_PRIORITY.get(summary["status"], 0)
        if prio > overall_priority:
            overall_priority = prio
            overall_status = summary["status"]
        for action in summary["next_actions"]:
            label = f"[{g}] {action}"
            if label not in all_next_actions:
                all_next_actions.append(label)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return {
        "summarized_at": ts,
        "root": str(root_path),
        "overall_status": overall_status,
        "groups": group_results,
        "all_next_actions": all_next_actions,
    }


# ── MD 빌더 ──────────────────────────────────────────────────────────────

def _build_summary_md(summary: dict[str, Any]) -> str:
    overall = summary.get("overall_status", "PASS")
    ts = summary.get("summarized_at", "")
    lines = [
        "# Recent Runs Summary",
        "",
        f"summarized_at: {ts}",
        f"overall_status: **{overall}**",
        "",
        "## 작업군별 상태",
        "",
        "| 작업군 | 상태 | 최신파일 | 신호 | 액션필요 |",
        "|--------|------|----------|------|----------|",
    ]

    for group, g in summary.get("groups", {}).items():
        st = g.get("status", "PASS")
        latest = (g.get("latest_file") or "(없음)").split("/")[-1]
        signals_str = "; ".join(g.get("signals", []))[:60] or "-"
        action_str = "Yes" if g.get("action_required") else "-"
        lines.append(f"| {group} | {st} | {latest} | {signals_str} | {action_str} |")

    lines += ["", "## 전체 next_actions", ""]
    for action in summary.get("all_next_actions", []):
        lines.append(f"- {action}")

    lines += [
        "",
        "## 보안 확인",
        "- .env / secrets / browser_state 원문 출력: 없음",
        "- API key / token / password 원문: redaction 처리",
    ]
    return "\n".join(lines)


# ── 파일 저장 ─────────────────────────────────────────────────────────────

def write_runs_summary(summary: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    """요약 결과를 JSON + MD로 저장한다. 문자열 필드는 redaction 적용."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    ts = summary.get("summarized_at", datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))

    # all_next_actions redaction
    safe_summary = dict(summary)
    if "all_next_actions" in safe_summary:
        safe_summary["all_next_actions"] = [
            redact_sensitive_text(a) if isinstance(a, str) else a
            for a in safe_summary["all_next_actions"]
        ]

    json_path = out_path / f"recent_runs_summary_{ts}.json"
    json_path.write_text(json.dumps(safe_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out_path / f"recent_runs_summary_{ts}.md"
    md_path.write_text(_build_summary_md(safe_summary), encoding="utf-8")

    return {"json": str(json_path), "md": str(md_path)}
