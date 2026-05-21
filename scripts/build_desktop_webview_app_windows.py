"""DESKTOP_WEBVIEW_PYINSTALLER_PACKAGE_01 — PyInstaller 빌드 스크립트.

산출:
  dist/HaehanAI-Desktop/HaehanAI-Desktop.exe  (onefolder 기본)
  data/inspection/desktop_webview_pyinstaller_package/build_report.json
  data/inspection/desktop_webview_pyinstaller_package/checksums.json

사용:
  python -m scripts.build_desktop_webview_app_windows
  python -m scripts.build_desktop_webview_app_windows --clean
  python -m scripts.build_desktop_webview_app_windows --onefile

보안: secret/env/token 파일 bundle 금지.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "HaehanAI-Desktop"
LAUNCHER = ROOT / "build" / "webview_launcher.py"
DIST_DIR = ROOT / "dist" / APP_NAME
OUT_DIR = ROOT / "data" / "inspection" / "desktop_webview_pyinstaller_package"
UI_DIST = ROOT / "desktop" / "ui_dist"


def _pyinstaller_version() -> str:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_launcher() -> None:
    LAUNCHER.parent.mkdir(parents=True, exist_ok=True)
    if not LAUNCHER.exists():
        LAUNCHER.write_text(
            "import sys\nfrom desktop.webview_app_pywebview import main\nsys.exit(main())\n",
            encoding="utf-8",
        )


def _build_cmd(*, onefile: bool, clean: bool) -> list[str]:
    """PyInstaller 실행 인자 구성."""
    ui_src = str(UI_DIST)
    # ui_dist → 패키지 내 desktop/ui_dist 위치로 번들
    ui_dest = "desktop/ui_dist"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--onefile" if onefile else "--onedir",
        "--windowed",        # 콘솔 창 숨김 (운영자 앱)
        # --- static data ---
        "--add-data", f"{ui_src}{os.pathsep}{ui_dest}",
        # --- hidden imports: webview ---
        "--hidden-import", "webview",
        "--hidden-import", "webview.platforms.winforms",
        "--collect-submodules", "webview",
        # --- hidden imports: server ---
        "--hidden-import", "uvicorn",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "fastapi",
        "--hidden-import", "starlette",
        "--hidden-import", "starlette.staticfiles",
        "--hidden-import", "starlette.responses",
        "--hidden-import", "httpx",
        "--hidden-import", "websockets",
        "--hidden-import", "websockets.legacy",
        "--hidden-import", "websockets.legacy.client",
        # --- hidden imports: agent ---
        "--hidden-import", "keyring",
        "--hidden-import", "keyring.backends.Windows",
        "--collect-submodules", "local_agent",
        "--collect-submodules", "desktop",
        # --- launcher ---
        str(LAUNCHER),
    ]

    if clean:
        cmd.insert(3, "--clean")

    return [c for c in cmd if c]


def build(*, onefile: bool = False, clean: bool = False) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app_name": APP_NAME,
        "mode": "onefile" if onefile else "onefolder",
        "launcher": str(LAUNCHER.relative_to(ROOT)),
        "ui_dist_included": UI_DIST.exists(),
        "pyinstaller_version": "",
        "ok": False,
        "exe_path": "",
        "exe_sha256": "",
        "dist_artifacts": [],
        "checksums": {},
    }

    ver = _pyinstaller_version()
    report["pyinstaller_version"] = ver
    if not ver:
        report["error"] = "PyInstaller 미설치 — pip install pyinstaller"
        _save_report(report)
        return report

    if not UI_DIST.exists() or not (UI_DIST / "index.html").exists():
        report["error"] = "FAIL_UI_DIST_MISSING — desktop/ui_dist/index.html 없음"
        _save_report(report)
        return report

    _ensure_launcher()
    cmd = _build_cmd(onefile=onefile, clean=clean)
    report["cmd"] = " ".join(cmd)

    print(f"[build] PyInstaller {ver} — {APP_NAME} ({report['mode']}) 빌드 시작...")
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=str(ROOT),
        )
        # secret 패턴 마스킹 후 저장
        report["stdout_tail"] = _mask_secrets(r.stdout or "")[-2000:]
        report["stderr_tail"] = _mask_secrets(r.stderr or "")[-2000:]
        if r.returncode != 0:
            report["error"] = f"pyinstaller_failed returncode={r.returncode}"
            _save_report(report)
            return report
    except subprocess.TimeoutExpired:
        report["error"] = "build_timeout"
        _save_report(report)
        return report
    except Exception as exc:
        report["error"] = f"build_exception:{type(exc).__name__}"
        _save_report(report)
        return report

    # 산출물 확인
    if onefile:
        exe = ROOT / "dist" / f"{APP_NAME}.exe"
    else:
        exe = DIST_DIR / f"{APP_NAME}.exe"

    if not exe.exists():
        # fallback
        alts = list((ROOT / "dist").rglob(f"{APP_NAME}.exe"))
        exe = alts[0] if alts else exe

    if exe.exists():
        report["exe_path"] = str(exe.relative_to(ROOT))
        report["exe_sha256"] = _sha256(exe)
        report["dist_artifacts"].append(str(exe.relative_to(ROOT)))
        report["ok"] = True
        print(f"[build] 성공: {exe}")
        print(f"[build] SHA256: {report['exe_sha256'][:16]}…")
    else:
        report["error"] = "FAIL_EXE_MISSING — dist 산출물 없음"

    _save_report(report)
    return report


def _mask_secrets(text: str) -> str:
    import re
    return re.sub(
        r"(device_token|api[_\-]?key|authorization|password|secret|registration_code)\s*[:=]\s*\S+",
        r"\1=<REDACTED>",
        text,
        flags=re.IGNORECASE,
    )


def _save_report(report: dict) -> None:
    (OUT_DIR / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "checksums.json").write_text(
        json.dumps({"checksums": report.get("checksums", {}),
                    "exe_sha256": report.get("exe_sha256", "")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="HaehanAI-Desktop PyInstaller 빌드")
    ap.add_argument("--onefile", action="store_true", help="단일 exe 생성")
    ap.add_argument("--clean", action="store_true", help="빌드 캐시 삭제 후 빌드")
    args = ap.parse_args(argv)

    report = build(onefile=args.onefile, clean=args.clean)
    summary = {k: v for k, v in report.items() if k not in ("stdout_tail", "stderr_tail", "cmd")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
