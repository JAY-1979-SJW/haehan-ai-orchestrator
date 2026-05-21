"""PyInstaller 기반 Windows 데스크앱 에이전트 패키징.

산출:
  dist/HaehanAI-Agent/HaehanAI-Agent.exe (one-folder 기본)
  build_report.json
  checksums.json

사용:
  python -m scripts.build_desktop_agent_windows
  python -m scripts.build_desktop_agent_windows --onefile
  python -m scripts.build_desktop_agent_windows --clean --onefile

PyInstaller 미설치 시:
  pip install pyinstaller
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


ENTRY_MODULE = "local_agent.desktop_launcher"
APP_NAME = "HaehanAI-Agent"
DIST_DIR = Path("dist") / APP_NAME
BUILD_REPORT = Path("data/inspection/local_agent_installer_package")


def _which_pyinstaller() -> str:
    try:
        r = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build(*, onefile: bool = False, clean: bool = False) -> dict:
    BUILD_REPORT.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "entry": ENTRY_MODULE,
        "app_name": APP_NAME,
        "mode": "onefile" if onefile else "onefolder",
        "pyinstaller_version": "",
        "ok": False,
        "dist_artifacts": [],
        "checksums": {},
    }
    ver = _which_pyinstaller()
    report["pyinstaller_version"] = ver
    if not ver:
        report["error"] = ("PyInstaller 미설치. `pip install pyinstaller` 후 재시도. "
                            "본 공정에서는 빌드 스크립트/문서/테스트만 검증.")
        _save(report)
        return report

    if clean and Path("build").exists():
        shutil.rmtree("build", ignore_errors=True)
    if clean and DIST_DIR.parent.exists():
        for p in DIST_DIR.parent.iterdir():
            if p.name.startswith(APP_NAME):
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean" if clean else "",
        "--onefile" if onefile else "--onedir",
        "--console",   # 디버깅 용이 — 정식 배포에선 --windowed 검토
        # 안 보이는 추가 import 보장
        "--hidden-import", "websockets",
        "--hidden-import", "keyring",
        "--hidden-import", "keyring.backends.Windows",
        # GUI hidden imports (AGENT_GUI_TRAY_01)
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        # customtkinter 모던 디자인
        "--hidden-import", "customtkinter",
        "--collect-data", "customtkinter",
        "--collect-submodules", "local_agent",
        # 엔트리: 모듈 실행 wrapper
        "-c", "import sys; from local_agent.desktop_launcher import main; sys.exit(main())",
    ]
    # -c 옵션은 PyInstaller 에 없음 — 별도 launcher 파일 필요
    # launcher 파일 생성:
    launcher = Path("build") / "agent_launcher.py"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(
        "import sys\n"
        "from local_agent.desktop_launcher import main\n"
        "sys.exit(main())\n",
        encoding="utf-8",
    )
    cmd = [c for c in cmd if c]
    # -c 제거 + entry 위치 변경
    cmd = [a for a in cmd if a != "-c"]
    cmd = [a for a in cmd if a != "import sys; from local_agent.desktop_launcher import main; sys.exit(main())"]
    cmd.append(str(launcher))

    report["cmd"] = " ".join(cmd)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        report["stdout_tail"] = (r.stdout or "")[-1000:]
        report["stderr_tail"] = (r.stderr or "")[-1000:]
        if r.returncode != 0:
            report["error"] = f"pyinstaller_failed code={r.returncode}"
            _save(report)
            return report
    except Exception as exc:
        report["error"] = f"build_exception:{exc}"
        _save(report)
        return report

    # 산출물
    target = (Path("dist") / APP_NAME / (APP_NAME + ".exe")) if not onefile \
             else Path("dist") / (APP_NAME + ".exe")
    if not target.exists():
        # PyInstaller 가 다른 이름으로 만들었을 가능성 — fallback
        alt = list((Path("dist")).glob(f"{APP_NAME}*"))
        target = alt[0] if alt else target
    if target.exists():
        report["dist_artifacts"].append(str(target))
        if target.is_file():
            report["checksums"][target.name] = _sha256(target)
        elif target.is_dir():
            for f in target.rglob("*"):
                if f.is_file():
                    report["dist_artifacts"].append(str(f))
        report["ok"] = True
    else:
        report["error"] = "dist artifact missing after build"

    _save(report)
    return report


def _save(report: dict) -> None:
    path = BUILD_REPORT / "build_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    csum = BUILD_REPORT / "checksums.json"
    csum.write_text(json.dumps(report.get("checksums", {}),
                                ensure_ascii=False, indent=2),
                    encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onefile", action="store_true")
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args(argv)
    r = build(onefile=args.onefile, clean=args.clean)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
