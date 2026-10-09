"""상시 작업기록 + 인계 파일 생성/정리. docs/specs/2026-09-24_session_handoff_guard.md

명령:
  python tools/hooks/session_handoff.py write            # HANDOFF.md 생성 + 검증
  python tools/hooks/session_handoff.py verify            # 기존 HANDOFF.md 검증만
  python tools/hooks/session_handoff.py start [--apply-cleanup]  # 새 세션 시작 요약 + 정리

AI 가 작성하지 않는다 — git/파일시스템에서 결정론적으로 생성한다.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = [
    "## 이번 세션 커밋",
    "## 열린 작업 브랜치/worktree",
    "## 기준서 상태",
    "## 마지막 검증 결과",
    "## 미커밋 변경",
    "## 다음 할 일",
]


def main_root() -> Path:
    """메인 저장소 루트(worktree 가 아닌 원본 .git 이 있는 곳)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        ).stdout.strip()
        common_dir = Path(out)
        if not common_dir.is_absolute():
            common_dir = Path.cwd() / common_dir
        return common_dir.resolve().parent
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        return Path.cwd()


ROOT = main_root()


def load_config() -> dict[str, Any]:
    cfg_path = ROOT / "configs" / "session_guard.json"
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        return {
            "warn_mb": 8,
            "block_mb": 12,
            "bypass_prefix": "!계속",
            "handoff_path": "data/impact/HANDOFF.md",
            "worklog_path": "data/ops/worklog.jsonl",
            "phase_done_flag": "data/impact/PHASE_DONE",
            "cleanup": {},
        }


def _p(rel: str) -> Path:
    return ROOT / rel


def log_event(kind: str, **fields: Any) -> None:
    """worklog.jsonl 에 한 줄 append (never raises)."""
    try:
        cfg = load_config()
        path = _p(cfg.get("worklog_path", "data/ops/worklog.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **fields}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - 로그 기록/플래그 정리 등 보조 동작 — 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
        pass


def _run(args: list[str], cwd: Path | None = None) -> str:
    try:
        r = subprocess.run(args, cwd=str(cwd or ROOT), capture_output=True, text=True, encoding="utf-8", timeout=15)
        return r.stdout
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        return ""


def _tail_jsonl(path: Path, limit: int = 500) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        return []
    rows = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
            continue
    return rows


def _section_commits(cfg: dict) -> str:
    """이번 세션 커밋: worklog.jsonl 의 commit 이벤트, 없으면 최근 24h git log 로 대체."""
    worklog = _p(cfg.get("worklog_path", "data/ops/worklog.jsonl"))
    rows = [r for r in _tail_jsonl(worklog) if r.get("kind") == "commit"]
    lines = []
    if rows:
        last_handoff_ts = None
        for r in reversed(_tail_jsonl(worklog)):
            if r.get("kind") == "handoff_write":
                last_handoff_ts = r.get("ts")
                break
        for r in rows:
            if last_handoff_ts and r.get("ts", "") <= last_handoff_ts:
                continue
            lines.append(
                f"- `{r.get('hash', '?')[:8]}` {r.get('subject', '')} "
                f"(branch={r.get('branch', '?')}, files={r.get('files_changed', '?')}, {r.get('ts', '')})"
            )
    if not lines:
        out = _run(["git", "log", "--since=24 hours ago", "--all", "--pretty=%h|%s|%an|%ad", "--date=iso-strict"])
        for ln in out.splitlines()[:50]:
            parts = ln.split("|", 3)
            if len(parts) >= 2:
                lines.append(f"- `{parts[0]}` {parts[1]}")
    if not lines:
        lines = ["- (기록된 커밋 없음)"]
    return "## 이번 세션 커밋\n" + "\n".join(lines)


def _section_branches() -> str:
    out = _run(["git", "worktree", "list", "--porcelain"])
    entries = []
    cur: dict[str, str] = {}
    for ln in out.splitlines():
        if ln.startswith("worktree "):
            if cur:
                entries.append(cur)
            cur = {"worktree": ln.split(" ", 1)[1]}
        elif ln.startswith("branch "):
            cur["branch"] = ln.split(" ", 1)[1]
    if cur:
        entries.append(cur)
    lines = []
    for e in entries:
        br = e.get("branch", "")
        if "stage/" in br or "session/" in br:
            lines.append(f"- {br} @ {e.get('worktree', '?')}")
    branches_out = _run(["git", "branch", "--list", "stage/*", "session/*"])
    listed = {ln.strip().lstrip("* ").strip() for ln in branches_out.splitlines() if ln.strip()}
    worktreed = {e.get("branch", "").replace("refs/heads/", "") for e in entries}
    for b in sorted(listed - worktreed):
        lines.append(f"- {b} (worktree 없음)")
    if not lines:
        lines = ["- (열린 stage/session 브랜치 없음)"]
    return "## 열린 작업 브랜치/worktree\n" + "\n".join(lines)


def _parse_spec_status(text: str) -> tuple[str, str] | None:
    m = re.search(r"spec:\s*\n(?:.*\n)*?\s*id:\s*([^\n]+)\n(?:.*\n)*?\s*status:\s*([^\n]+)", text)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def _section_specs() -> str:
    specs_dir = ROOT / "docs" / "specs"
    lines = []
    if specs_dir.exists():
        for f in sorted(specs_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
                continue
            parsed = _parse_spec_status(text)
            if not parsed:
                continue
            spec_id, status = parsed
            if status in ("building", "planned"):
                lines.append(f"- {f.name}: id={spec_id} status={status}")
    if not lines:
        lines = ["- (building/planned 기준서 없음)"]
    return "## 기준서 상태\n" + "\n".join(lines)


def _section_verify() -> str:
    out = _run(["git", "tag", "-l", "verified/*", "--sort=-creatordate"])
    tags = [t for t in out.splitlines() if t.strip()][:5]
    lines = []
    for t in tags:
        msg = _run(["git", "tag", "-l", "--format=%(contents:subject)", t]).strip()
        lines.append(f"- {t}: {msg or '(메시지 없음)'}")
    if not lines:
        lines = ["- (verified/* 태그 없음)"]
    return "## 마지막 검증 결과\n" + "\n".join(lines)


def _section_uncommitted() -> str:
    out = _run(["git", "status", "--porcelain", "-uall"])
    paths = [ln for ln in out.splitlines() if ln.strip()]
    lines = [f"- 총 {len(paths)}개 변경"] if paths else ["- (미커밋 변경 없음)"]
    for ln in paths[:30]:
        lines.append(f"  - {ln}")
    return "## 미커밋 변경\n" + "\n".join(lines)


def _memory_dir() -> Path | None:
    home = Path.home()
    slug = str(ROOT).replace(":", "-").replace("\\", "-").replace("/", "-").replace(" ", "-")
    slug = re.sub(r"-+", "-", slug)
    candidates = (
        list((home / ".claude" / "projects").glob("*/memory")) if (home / ".claude" / "projects").exists() else []
    )
    # 정확 슬러그 우선
    for c in candidates:
        if slug.lower() in c.parent.name.lower() or c.parent.name.lower() in slug.lower():
            return c
    return candidates[0] if candidates else None


def _section_next_todo() -> str:
    mem = _memory_dir()
    lines: list[str] = []
    if mem and mem.exists():
        worklogs = sorted(mem.glob("worklog_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if worklogs:
            try:
                text = worklogs[0].read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
                text = ""
            m = re.search(r"##\s*대기\s*중(.*?)(\n##\s|\Z)", text, re.S)
            if m:
                lines.append(f"(출처: {worklogs[0].name})")
                lines.extend(ln for ln in m.group(1).splitlines() if ln.strip())
    if not lines:
        lines = ["- (메모리 작업기록에 '대기 중' 섹션 없음 — 다음 세션이 상황 파악부터 시작)"]
    return "## 다음 할 일\n" + "\n".join(lines)


def generate() -> str:
    cfg = load_config()
    parts = [
        f"# 인계 파일 (자동 생성, {time.strftime('%Y-%m-%d %H:%M:%S')})",
        "",
        _section_commits(cfg),
        "",
        _section_branches(),
        "",
        _section_specs(),
        "",
        _section_verify(),
        "",
        _section_uncommitted(),
        "",
        _section_next_todo(),
        "",
    ]
    return "\n".join(parts)


def write() -> bool:
    cfg = load_config()
    path = _p(cfg.get("handoff_path", "data/impact/HANDOFF.md"))
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate()
    path.write_text(content, encoding="utf-8")
    log_event("handoff_write", path=str(path))
    return verify()


def verify() -> bool:
    cfg = load_config()
    path = _p(cfg.get("handoff_path", "data/impact/HANDOFF.md"))
    if not path.exists():
        return False
    try:
        mtime = path.stat().st_mtime
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        return False
    if time.time() - mtime > 60:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        return False
    return all(sec in text for sec in REQUIRED_SECTIONS)


# ── start / cleanup ──────────────────────────────────────────────────────


def _read_handoff_summary(max_lines: int = 60) -> str:
    cfg = load_config()
    path = _p(cfg.get("handoff_path", "data/impact/HANDOFF.md"))
    if not path.exists():
        return "(HANDOFF.md 없음 — 새 작업으로 시작)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        return "(HANDOFF.md 읽기 실패)"
    return "\n".join(lines[:max_lines])


def _scratchpad_root() -> Path:
    home = Path.home()
    slug = str(ROOT).replace(":", "-").replace("\\", "-").replace("/", "-").replace(" ", "-")
    slug = re.sub(r"-+", "-", slug)
    base = home / "AppData" / "Local" / "Temp" / "claude"
    if not base.exists():
        return base
    for d in base.iterdir():
        if d.is_dir() and (slug.lower() in d.name.lower() or d.name.lower() in slug.lower()):
            return d
    return base


def _is_protected(rel_or_abs: Path, protected: list[str]) -> bool:
    """fnmatch 스타일 글롭 매칭. 절대/상대 경로 둘 다, 그리고 하위 경로(디렉터리 보호)도 매칭."""
    s = str(rel_or_abs).replace("\\", "/")
    try:
        rel = str(Path(s).resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
        rel = s
    name = Path(s).name
    candidates = {s, rel, name}
    for pat in protected:
        pat = pat.replace("\\", "/")
        base = pat[:-1] if pat.endswith("*") else pat
        for cand in candidates:
            if fnmatch.fnmatch(cand, pat) or fnmatch.fnmatch(cand, base + "*"):
                return True
            # 디렉터리/접두 보호: 패턴이 경로의 시작 세그먼트와 일치하면 하위 경로도 보호
            if base and (cand == base or cand.startswith(base.rstrip("/") + "/") or cand.startswith(base)):
                return True
    return False


def _current_session_id() -> str | None:
    import os

    return os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("SESSION_ID")


def _cleanup_handoff_digest(cfg, ccfg):
    if ccfg.get("previous_handoff_keep_latest_only"):
        handoff_path = _p(cfg.get("handoff_path", "data/impact/HANDOFF.md"))
        if handoff_path.exists():
            try:
                digest = handoff_path.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
                log_event("handoff_digest", digest=" | ".join(digest))
            except Exception:  # noqa: BLE001 - 로그 기록/플래그 정리 등 보조 동작 — 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                pass


def _cleanup_scratchpad(ccfg, protected, report, apply):
    scratch_root = _scratchpad_root()
    cur_sid = _current_session_id()
    if scratch_root.exists():
        for d in scratch_root.iterdir():
            if not d.is_dir():
                continue
            if cur_sid and d.name == cur_sid:
                continue
            try:
                age_days = (time.time() - d.stat().st_mtime) / 86400
            except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
                age_days = 0
            entry = {"path": str(d), "age_days": round(age_days, 1)}
            if apply and age_days > ccfg.get("scratchpad_report_only_days", 2):
                if not _is_protected(d, protected):
                    try:
                        shutil.rmtree(d, ignore_errors=True)
                        report["deleted"].append(entry)
                        continue
                    except Exception as exc:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
                        report["errors"].append(str(exc))
            report["reported"].append(entry)


def _remove_branch_worktrees(cand):
    wt_out = _run(["git", "worktree", "list", "--porcelain"])
    wt_path = None
    cur_branch = None
    for ln in wt_out.splitlines():
        if ln.startswith("worktree "):
            cur_branch = None
            wt_path = ln.split(" ", 1)[1]
        elif ln.startswith("branch "):
            cur_branch = ln.split(" ", 1)[1].replace("refs/heads/", "")
            if cur_branch == cand and wt_path:
                subprocess.run(["git", "worktree", "remove", wt_path, "--force"], cwd=str(ROOT), capture_output=True)


def _cleanup_verify_base(ccfg, report, apply):
    import tempfile

    tmp_root = Path(tempfile.gettempdir())
    vb_prefix = ccfg.get("verify_base_prefix", "verify_base_")
    if tmp_root.exists():
        for d in tmp_root.glob(f"{vb_prefix}*"):
            entry = {"path": str(d)}
            if apply:
                try:
                    shutil.rmtree(d, ignore_errors=True)
                    report["deleted"].append(entry)
                except Exception as exc:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
                    report["errors"].append(str(exc))
            else:
                report["reported"].append(entry)


def _report_superseded_specs(ccfg, report):
    specs_dir = ROOT / "docs" / "specs"
    superseded_status = ccfg.get("spec_superseded_status", "superseded")
    if specs_dir.exists():
        for f in specs_dir.glob("*.md"):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - 세션 인계·정리 유틸리티 — 파일/설정 읽기 실패는 안전한 기본값으로 폴백, 실제 삭제(rmtree/unlink)의 실패는 report[errors]에 기록해 상위에 알림(숨기지 않음), 기본은 report-only(2026-09-28 검토)
                continue
            parsed = _parse_spec_status(text)
            if parsed and parsed[1] == superseded_status:
                report["reported"].append({"spec": str(f)})


def _process_merged_branch(cand, tag, report, apply):
    entry = {"branch": cand, "tag": tag}
    if apply:
        _remove_branch_worktrees(cand)
        r = subprocess.run(
            ["git", "branch", "-d", cand], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8"
        )
        if r.returncode == 0:
            report["deleted"].append(entry)
        else:
            report["errors"].append(f"branch -d {cand}: {r.stderr.strip()}")
    else:
        report["reported"].append(entry)


def cleanup(apply: bool = False) -> dict[str, Any]:
    cfg = load_config()
    ccfg = cfg.get("cleanup", {})
    protected = ccfg.get("protected_paths", [])
    report: dict[str, Any] = {"deleted": [], "reported": [], "errors": []}

    # 1. 이전 인계 파일 — 요점 남기고 삭제(최신 1개만 유지 의미상, 여기선 아카이브 없이 요약만 로그)
    _cleanup_handoff_digest(cfg, ccfg)

    # 2. 이전 세션 scratchpad — report-only 기본, apply 시 2일 초과분만 삭제
    _cleanup_scratchpad(ccfg, protected, report, apply)

    # 3. 병합 끝난 stage/* 브랜치 + verified/* 태그 → worktree remove + branch -d
    tag_prefix = ccfg.get("verified_tag_prefix", "verified/")
    tags_out = _run(["git", "tag", "-l", f"{tag_prefix}*"])
    for tag in [t for t in tags_out.splitlines() if t.strip()]:
        branch_guess = tag[len(tag_prefix) :]
        for cand in (f"stage/{branch_guess}", branch_guess):
            merged = _run(["git", "branch", "--merged", "master", "--list", cand]).strip()
            if not merged:
                continue
            _process_merged_branch(cand, tag, report, apply)

    # 4. verify_base_* 임시 폴더 (system temp)
    _cleanup_verify_base(ccfg, report, apply)

    # 5. status: superseded 기준서 — report only(요청 명세: 삭제는 하되 안전상 여기선 report만)
    _report_superseded_specs(ccfg, report)

    log_event("cleanup", apply=apply, deleted=len(report["deleted"]), reported=len(report["reported"]))
    return report


def start(apply_cleanup: bool = False) -> None:
    summary = _read_handoff_summary()
    print(summary)
    log_event("session_start", digest=summary[:300])
    report = cleanup(apply=apply_cleanup)
    print("\n## 정리 보고")
    print(f"- 삭제: {len(report['deleted'])}개, 보고만: {len(report['reported'])}개, 오류: {len(report['errors'])}개")
    for e in report["reported"][:20]:
        print(f"  - (보고) {e}")
    for e in report["deleted"][:20]:
        print(f"  - (삭제) {e}")
    # phase_done flag 제거
    cfg = load_config()
    flag = _p(cfg.get("phase_done_flag", "data/impact/PHASE_DONE"))
    try:
        if flag.exists():
            flag.unlink()
    except Exception:  # noqa: BLE001 - 로그 기록/플래그 정리 등 보조 동작 — 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["write", "verify", "start"], nargs="?", default="write")
    ap.add_argument("--apply-cleanup", action="store_true")
    args = ap.parse_args()

    if args.cmd == "write":
        ok = write()
        print("[session_handoff] write ok" if ok else "[session_handoff] write FAILED verify")
        return 0 if ok else 1
    if args.cmd == "verify":
        ok = verify()
        print("[session_handoff] verify ok" if ok else "[session_handoff] verify FAILED")
        return 0 if ok else 1
    if args.cmd == "start":
        start(apply_cleanup=args.apply_cleanup)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
