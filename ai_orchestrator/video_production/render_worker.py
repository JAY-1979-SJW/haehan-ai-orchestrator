"""F-4S-13 restricted ffmpeg render worker.

설계 원칙:
- 입력: F-4S-12 render_plan JSON
- 기본 동작: dry-run (실제 ffmpeg 미실행)
- execute 모드: --execute 명시 + ffmpeg_path 확인 + 경로 검증 통과 시에만 실행
- shell=True 절대 금지
- os.system 금지
- subprocess.run: allowlisted ffmpeg_path + list args + dry_run=False 시에만 허용
- 외부 URL 입력 금지
- 입력 경로: runs/video 또는 samples 하위만 허용
- 출력 경로: runs/video/render/output 하위만 허용
- 출력 확장자: .mp4만 허용
- YouTube/Naver 업로드 금지
- OAuth 금지
- 브라우저/Playwright 금지
- API key/secret 출력 금지
- .env 커밋 금지
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SECRET_KEYWORDS = ("api_key", "secret", "password", "token", "client_secret", "bearer")
_URL_SCHEMES = ("http://", "https://", "file://", "ftp://")
_FORBIDDEN_STEP_TYPES = ("upload", "publish", "delete", "post", "login", "purchase", "comment")
_SHELL_METACHARS = re.compile(r"[;&|`$<>\\]")
_ALLOWED_INPUT_ROOTS = ("runs/video", "samples")
_ALLOWED_OUTPUT_ROOT = "runs/video/render/output"


def _has_secret(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _SECRET_KEYWORDS)


def _is_external_url(s: str) -> bool:
    return any(s.startswith(scheme) for scheme in _URL_SCHEMES)


def _is_under_roots(path_str: str, roots: Tuple[str, ...]) -> bool:
    """경로가 허용 root 하위인지 확인 (절대/상대 모두)."""
    p = Path(path_str)
    parts = p.parts
    # check relative path segments
    path_normalized = path_str.replace("\\", "/").lower()
    return any(root.lower() in path_normalized for root in roots)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_render_plan(path: Any) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_render_item_for_execute(
    item: Dict[str, Any],
    allowed_roots: Optional[Tuple[str, ...]] = None,
) -> Tuple[bool, List[str]]:
    """실행 가능 여부 검증. (ok, reasons) 반환."""
    reasons: List[str] = []
    roots = allowed_roots or _ALLOWED_INPUT_ROOTS

    cmd = item.get("command_plan", {})
    if not isinstance(cmd, dict):
        reasons.append("command_plan_missing")
        return False, reasons

    if cmd.get("program") != "ffmpeg":
        reasons.append(f"program_not_ffmpeg:{cmd.get('program')}")

    args = cmd.get("args")
    if not isinstance(args, list):
        reasons.append("args_not_list")
        return False, reasons

    if not all(isinstance(a, str) for a in args):
        reasons.append("args_contain_non_str")

    # shell metachar check
    for arg in args:
        if _SHELL_METACHARS.search(arg) and not Path(arg).exists():
            reasons.append(f"shell_metachar_in_arg:{arg[:40]}")

    # external URL check in args
    for arg in args:
        if _is_external_url(arg):
            reasons.append(f"external_url_blocked:{arg[:60]}")

    # -i input path validation
    for idx, arg in enumerate(args):
        if arg == "-i" and idx + 1 < len(args):
            inp = args[idx + 1]
            if inp.startswith("<"):
                reasons.append(f"input_planned_not_resolved:{inp}")
            elif _is_external_url(inp):
                reasons.append(f"input_external_url:{inp[:60]}")
            elif not _is_under_roots(inp, roots):
                reasons.append(f"input_outside_allowed_roots:{inp[:60]}")
            elif not Path(inp).exists():
                reasons.append(f"input_file_not_found:{inp[:60]}")

    # output path validation (last arg)
    output_path = args[-1] if args else ""
    if output_path:
        if _is_external_url(output_path):
            reasons.append(f"output_external_url:{output_path[:60]}")
        else:
            out_normalized = output_path.replace("\\", "/").lower()
            allowed_out = _ALLOWED_OUTPUT_ROOT.lower()
            if allowed_out not in out_normalized:
                reasons.append(f"output_outside_allowed_root:{output_path[:60]}")
            if not output_path.lower().endswith(".mp4"):
                reasons.append(f"output_ext_not_mp4:{output_path[-20:]}")

    # forbidden step type check
    action = item.get("action") or item.get("step_type") or ""
    if action in _FORBIDDEN_STEP_TYPES:
        reasons.append(f"forbidden_action:{action}")

    # secret in args
    for arg in args:
        if _has_secret(arg):
            reasons.append(f"secret_like_arg:{arg[:20]}")

    return len(reasons) == 0, reasons


def validate_ffmpeg_args(args: List[str]) -> Tuple[bool, List[str]]:
    """args list 자체 검증."""
    issues: List[str] = []
    if not isinstance(args, list):
        return False, ["args_not_list"]
    if not all(isinstance(a, str) for a in args):
        issues.append("args_contain_non_str")
        return False, issues
    for arg in args:
        if _SHELL_METACHARS.search(arg):
            issues.append(f"shell_metachar:{arg[:40]}")
    return len(issues) == 0, issues


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


def execute_render_item(
    item: Dict[str, Any],
    *,
    ffmpeg_path: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    render_id = item.get("render_id", "unknown")
    cmd = item.get("command_plan", {})
    args = cmd.get("args", [])

    if dry_run:
        return {
            "render_id": render_id,
            "status": "dry_run",
            "dry_run": True,
            "executed": False,
            "ffmpeg_path": None,
            "returncode": None,
            "stdout": None,
            "stderr": None,
            "error": None,
            "display": cmd.get("display", ""),
        }

    # resolve ffmpeg path
    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not resolved_ffmpeg:
        return {
            "render_id": render_id,
            "status": "blocked",
            "dry_run": False,
            "executed": False,
            "ffmpeg_path": None,
            "returncode": None,
            "stdout": None,
            "stderr": None,
            "error": "ffmpeg_not_found",
            "display": cmd.get("display", ""),
        }

    ok, reasons = validate_render_item_for_execute(item)
    if not ok:
        return {
            "render_id": render_id,
            "status": "blocked",
            "dry_run": False,
            "executed": False,
            "ffmpeg_path": resolved_ffmpeg,
            "returncode": None,
            "stdout": None,
            "stderr": None,
            "error": f"validation_failed:{';'.join(reasons)}",
            "display": cmd.get("display", ""),
        }

    # ensure output dir exists
    output_path = args[-1] if args else ""
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    full_cmd = [resolved_ffmpeg] + args
    try:
        result = subprocess.run(  # noqa: S603
            full_cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "render_id": render_id,
            "status": "done" if result.returncode == 0 else "error",
            "dry_run": False,
            "executed": True,
            "ffmpeg_path": resolved_ffmpeg,
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:] if result.stdout else None,
            "stderr": result.stderr[-2000:] if result.stderr else None,
            "error": None if result.returncode == 0 else f"returncode:{result.returncode}",
            "display": cmd.get("display", ""),
        }
    except subprocess.TimeoutExpired:
        return {
            "render_id": render_id,
            "status": "error",
            "dry_run": False,
            "executed": True,
            "ffmpeg_path": resolved_ffmpeg,
            "returncode": None,
            "stdout": None,
            "stderr": None,
            "error": "timeout",
            "display": cmd.get("display", ""),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "render_id": render_id,
            "status": "error",
            "dry_run": False,
            "executed": True,
            "ffmpeg_path": resolved_ffmpeg,
            "returncode": None,
            "stdout": None,
            "stderr": None,
            "error": f"exception:{type(exc).__name__}:{str(exc)[:200]}",
            "display": cmd.get("display", ""),
        }


def execute_render_plan(
    plan: Dict[str, Any],
    *,
    ffmpeg_path: Optional[str] = None,
    dry_run: bool = True,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    items = plan.get("render_items") or []
    if isinstance(max_items, int) and max_items > 0:
        items = items[:max_items]

    results: List[Dict[str, Any]] = []
    for item in items:
        r = execute_render_item(item, ffmpeg_path=ffmpeg_path, dry_run=dry_run)
        results.append(r)

    executed_count = sum(1 for r in results if r.get("executed"))
    blocked_count = sum(1 for r in results if r.get("status") == "blocked")
    done_count = sum(1 for r in results if r.get("status") == "done")
    error_count = sum(1 for r in results if r.get("status") == "error")
    dry_run_count = sum(1 for r in results if r.get("status") == "dry_run")

    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": dry_run,
        "ffmpeg_available": resolved_ffmpeg is not None,
        "ffmpeg_path": resolved_ffmpeg,
        "total_items": len(results),
        "executed_count": executed_count,
        "done_count": done_count,
        "blocked_count": blocked_count,
        "error_count": error_count,
        "dry_run_count": dry_run_count,
        "results": results,
        "notes": [
            "F-4S-13 restricted render worker",
            f"dry_run={dry_run}",
            "shell=True 금지 / os.system 금지",
            "입력: runs/video 또는 samples 하위만",
            "출력: runs/video/render/output 하위만",
            "외부 URL 금지 / .mp4만 허용",
            "YouTube/Naver 업로드 금지 / OAuth 금지",
        ],
    }


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def render_render_worker_markdown(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Render Worker 리포트 (F-4S-13)")
    lines.append("")
    lines.append(f"- generated_at: {result.get('generated_at')}")
    lines.append(f"- dry_run: {result.get('dry_run')}")
    lines.append(f"- ffmpeg_available: {result.get('ffmpeg_available')}")
    lines.append(f"- ffmpeg_path: {result.get('ffmpeg_path') or '(not found)'}")
    lines.append(f"- total_items: {result.get('total_items')}")
    lines.append(f"- executed_count: {result.get('executed_count')}")
    lines.append(f"- done_count: {result.get('done_count')}")
    lines.append(f"- blocked_count: {result.get('blocked_count')}")
    lines.append(f"- error_count: {result.get('error_count')}")
    lines.append(f"- dry_run_count: {result.get('dry_run_count')}")
    lines.append("")

    for r in result.get("results") or []:
        lines.append(f"## {r['render_id']} — status: {r['status']}")
        lines.append(f"- executed: {r.get('executed')}")
        lines.append(f"- dry_run: {r.get('dry_run')}")
        if r.get("returncode") is not None:
            lines.append(f"- returncode: {r['returncode']}")
        if r.get("error"):
            lines.append(f"- error: {r['error']}")
        lines.append(f"- display: `{r.get('display', '')}`")
        lines.append("")

    notes = result.get("notes") or []
    if notes:
        lines.append("## 주의사항")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


def write_render_worker_result_files(
    result: Dict[str, Any],
    out_dir: Any,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"render_worker_{ts}"
    json_path = out / f"{base}.json"
    md_path = out / f"{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_render_worker_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}
