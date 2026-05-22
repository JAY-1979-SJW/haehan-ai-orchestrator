"""HAEHAN_DESKTOP_INSTALL_SHORTCUT_01 — 공식 HaehanAI-Desktop.exe 바로가기 생성.

사용:
    python scripts/haehan/create_desktop_shortcut.py --desktop
    python scripts/haehan/create_desktop_shortcut.py --start-menu
    python scripts/haehan/create_desktop_shortcut.py --desktop --start-menu --dry-run
    python scripts/haehan/create_desktop_shortcut.py --detect-legacy

원칙:
    - dist/HaehanAI-Desktop/HaehanAI-Desktop.exe 만 정식 대상.
    - SHA-256 이 release baseline 문서 기록과 일치해야만 바로가기 생성.
    - legacy 경로(HaehanAI-Agent.exe / desktop/electron / desktop/webview_app.py)
      대상의 바로가기 생성은 절대 금지.
    - --dry-run 시 .lnk 파일 미생성, 결과만 출력.
    - secret 값/원문 출력 금지.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent

OFFICIAL_EXE_REL = "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe"
BASELINE_DOC_REL = "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md"
SHORTCUT_NAME = "HaehanAI Desktop.lnk"

# 금지 path 패턴 (포함되면 차단)
LEGACY_PATTERNS = (
    "HaehanAI-Agent.exe",
    "dist/HaehanAI-Agent",
    "dist\\HaehanAI-Agent",
    "desktop/electron",
    "desktop\\electron",
    "desktop/webview_app.py",
    "desktop\\webview_app.py",
)


@dataclass
class VerifyResult:
    ok: bool
    reason: str
    exe_path: str = ""
    sha256_actual: str = ""
    sha256_expected: str = ""


def baseline_sha256(root: Path = ROOT) -> Optional[str]:
    """release baseline 문서에서 첫 SHA-256 hex 추출."""
    p = root / BASELINE_DOC_REL
    if not p.exists():
        return None
    m = re.search(r"\b([0-9a-f]{64})\b", p.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_legacy_target(target: str) -> bool:
    norm = target.replace("\\", "/").lower()
    return any(pat.replace("\\", "/").lower() in norm for pat in LEGACY_PATTERNS)


def verify_official_exe(root: Path = ROOT) -> VerifyResult:
    exe = root / OFFICIAL_EXE_REL
    if not exe.exists():
        return VerifyResult(False, "exe_missing")
    if is_legacy_target(str(exe)):
        return VerifyResult(False, "legacy_target_rejected", exe_path=str(exe))
    expected = baseline_sha256(root)
    if not expected:
        return VerifyResult(False, "baseline_sha_missing", exe_path=str(exe))
    actual = file_sha256(exe)
    if actual != expected:
        return VerifyResult(False, "sha_mismatch", exe_path=str(exe),
                            sha256_actual=actual, sha256_expected=expected)
    return VerifyResult(True, "verified", exe_path=str(exe),
                        sha256_actual=actual, sha256_expected=expected)


def desktop_dir() -> Path:
    base = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(base) / "Desktop"


def start_menu_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "HaehanAI"


def _create_lnk_via_powershell(lnk_path: Path, target: Path,
                               working_dir: Path,
                               description: str) -> tuple[bool, str]:
    """WScript.Shell COM 으로 .lnk 생성. 실패 시 (False, error)."""
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$lnk = $ws.CreateShortcut('{lnk_path}'); "
        f"$lnk.TargetPath = '{target}'; "
        f"$lnk.WorkingDirectory = '{working_dir}'; "
        f"$lnk.Description = '{description}'; "
        "$lnk.WindowStyle = 1; "
        "$lnk.Save()"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return False, r.stderr.strip() or r.stdout.strip()
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def create_shortcut(*, target_exe: Path, lnk_path: Path,
                    description: str = "HaehanAI Desktop",
                    dry_run: bool = False) -> dict:
    """바로가기 생성. 사전 검증은 호출자 책임 (verify_official_exe)."""
    if is_legacy_target(str(target_exe)):
        return {"ok": False, "reason": "legacy_target_rejected",
                "target": str(target_exe), "lnk": str(lnk_path),
                "created": False}

    if dry_run:
        return {"ok": True, "reason": "dry_run", "target": str(target_exe),
                "lnk": str(lnk_path), "created": False}

    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    ok, err = _create_lnk_via_powershell(
        lnk_path=lnk_path, target=target_exe,
        working_dir=target_exe.parent, description=description,
    )
    return {"ok": ok, "reason": "" if ok else f"powershell_error:{err}",
            "target": str(target_exe), "lnk": str(lnk_path),
            "created": ok and lnk_path.exists()}


def detect_legacy_shortcuts() -> list[dict]:
    """바탕화면/시작 메뉴에서 legacy 대상 바로가기 탐지.

    .lnk 의 TargetPath 를 WScript.Shell 로 추출 — legacy 패턴이 포함된 항목 반환.
    """
    candidates = []
    for d in (desktop_dir(), start_menu_dir().parent / "HaehanAI",
              start_menu_dir().parent):
        if not d.exists():
            continue
        for lnk in d.rglob("*.lnk"):
            candidates.append(lnk)

    if not candidates:
        return []

    findings: list[dict] = []
    for lnk in candidates:
        try:
            ps = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"$s = $ws.CreateShortcut('{lnk}'); "
                "$s.TargetPath"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=10,
            )
            target = (r.stdout or "").strip()
        except Exception:
            continue
        if target and is_legacy_target(target):
            findings.append({"lnk": str(lnk), "target": target})
    return findings


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="haehan-shortcut")
    parser.add_argument("--desktop", action="store_true",
                        help="바탕화면 바로가기 생성")
    parser.add_argument("--start-menu", action="store_true",
                        help="시작 메뉴 바로가기 생성")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 .lnk 생성 없이 결과만 보고")
    parser.add_argument("--detect-legacy", action="store_true",
                        help="legacy 대상 바로가기만 탐지하고 종료")
    parser.add_argument("--exe", type=str, default="",
                        help="(테스트) exe 경로 override. 기본은 dist/HaehanAI-Desktop/HaehanAI-Desktop.exe")
    args = parser.parse_args(argv)

    if args.detect_legacy:
        items = detect_legacy_shortcuts()
        if not items:
            print("legacy 바로가기 없음")
            return 0
        for it in items:
            print(f"[LEGACY] {it['lnk']} → {it['target']}")
        return 0

    # 1. exe 검증
    if args.exe:
        target = Path(args.exe).resolve()
        if is_legacy_target(str(target)):
            print(f"[REJECT] legacy 경로 — {target}", file=sys.stderr)
            return 2
        if not target.exists():
            print(f"[REJECT] exe 부재 — {target}", file=sys.stderr)
            return 2
        # SHA 일치 검사 (override 모드여도 baseline 일치 요구)
        expected = baseline_sha256()
        if expected and file_sha256(target) != expected:
            print("[REJECT] SHA-256 불일치", file=sys.stderr)
            return 2
    else:
        v = verify_official_exe()
        if not v.ok:
            print(f"[REJECT] {v.reason}", file=sys.stderr)
            return 2
        target = Path(v.exe_path)

    if not (args.desktop or args.start_menu):
        print("--desktop 또는 --start-menu 중 하나 이상 필요", file=sys.stderr)
        return 1

    rc = 0
    if args.desktop:
        lnk = desktop_dir() / SHORTCUT_NAME
        r = create_shortcut(target_exe=target, lnk_path=lnk,
                            dry_run=args.dry_run)
        print(f"[desktop] ok={r['ok']} created={r['created']} lnk={r['lnk']}"
              + (f" reason={r['reason']}" if r['reason'] else ""))
        if not r["ok"]:
            rc = 3

    if args.start_menu:
        lnk = start_menu_dir() / SHORTCUT_NAME
        r = create_shortcut(target_exe=target, lnk_path=lnk,
                            dry_run=args.dry_run)
        print(f"[start-menu] ok={r['ok']} created={r['created']} lnk={r['lnk']}"
              + (f" reason={r['reason']}" if r['reason'] else ""))
        if not r["ok"]:
            rc = 3

    return rc


if __name__ == "__main__":
    sys.exit(main())
