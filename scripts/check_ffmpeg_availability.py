"""F-4S-13b ffmpeg availability check.

설계 원칙:
- shutil.which 로 경로 확인
- -version 실행은 which 결과가 있을 때만, shell=False, list args
- 실제 렌더링 명령 금지
- shell=True / os.system 금지
- 외부 URL / 업로드 / OAuth / 브라우저 금지
- API key / secret 출력 금지
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _run_version(path: str) -> str:
    """프로그램의 첫 번째 버전 줄만 반환. shell=False 강제."""
    try:
        r = subprocess.run(  # noqa: S603
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        first_line = (r.stdout or r.stderr or "").splitlines()[0] if (r.stdout or r.stderr) else ""
        return first_line.strip()
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}:{str(exc)[:100]}"


def check_ffmpeg_availability() -> dict:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    ffmpeg_version = _run_version(ffmpeg_path) if ffmpeg_path else None
    ffprobe_version = _run_version(ffprobe_path) if ffprobe_path else None

    warnings: list[str] = []
    if not ffmpeg_path:
        warnings.append("ffmpeg_not_found:install_required")
    if not ffprobe_path:
        warnings.append("ffprobe_not_found:optional_but_recommended")

    ready = bool(ffmpeg_path)
    recommendation = "ready_for_render_smoke" if ready else "install_required"

    import platform
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ffmpeg_found": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path,
        "ffmpeg_version_line": ffmpeg_version,
        "ffprobe_found": ffprobe_path is not None,
        "ffprobe_path": ffprobe_path,
        "ffprobe_version_line": ffprobe_version,
        "platform": platform.system(),
        "recommendation": recommendation,
        "warnings": warnings,
        "notes": [
            "F-4S-13b availability check only — 실제 렌더 미실행",
            "subprocess shell 옵션은 항상 False — os.system 사용 금지",
            "ffmpeg 설치 후 F-4S-13c에서 실제 render smoke 수행",
        ],
    }


def render_availability_markdown(result: dict) -> str:
    lines = [
        "# FFmpeg Availability Check (F-4S-13b)",
        "",
        f"- generated_at: {result.get('generated_at')}",
        f"- platform: {result.get('platform')}",
        f"- ffmpeg_found: {result.get('ffmpeg_found')}",
        f"- ffmpeg_path: {result.get('ffmpeg_path') or '(not found)'}",
        f"- ffmpeg_version_line: {result.get('ffmpeg_version_line') or '(N/A)'}",
        f"- ffprobe_found: {result.get('ffprobe_found')}",
        f"- ffprobe_path: {result.get('ffprobe_path') or '(not found)'}",
        f"- ffprobe_version_line: {result.get('ffprobe_version_line') or '(N/A)'}",
        f"- recommendation: **{result.get('recommendation')}**",
        "",
    ]
    for w in result.get("warnings") or []:
        lines.append(f"- WARNING: {w}")
    if result.get("warnings"):
        lines.append("")
    notes = result.get("notes") or []
    if notes:
        lines.append("## 주의사항")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


def write_availability_files(result: dict, out_dir: Path, *, timestamp: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"ffmpeg_availability_{ts}"
    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_availability_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="F-4S-13b ffmpeg availability check")
    parser.add_argument(
        "--out-dir",
        default="runs/video/render",
        help="output directory (default: runs/video/render)",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON 출력")
    args = parser.parse_args()

    result = check_ffmpeg_availability()
    paths = write_availability_files(result, Path(args.out_dir))

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_availability_markdown(result))

    print(f"\n[결과 파일]", file=sys.stderr)
    print(f"  JSON: {paths['json']}", file=sys.stderr)
    print(f"  MD:   {paths['md']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
