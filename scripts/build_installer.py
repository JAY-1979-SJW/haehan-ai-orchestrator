"""Haehan AI 인스톨러 빌드 스크립트.

단계:
  1. Next.js 프로덕션 빌드 (admin-web)
  2. PyInstaller로 FastAPI 서버 번들 (dist/haehan-server/)
  3. electron-builder로 NSIS 인스톨러 생성 (dist-electron/)

사용:
    python scripts/build_installer.py
    python scripts/build_installer.py --skip-next   # Next.js 빌드 생략
    python scripts/build_installer.py --skip-py     # PyInstaller 생략
    python scripts/build_installer.py --skip-electron  # Electron 빌드 생략
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_SERVER = ROOT / "dist" / "haehan-server"
DIST_ELECTRON = ROOT / "dist-electron"
SPEC_FILE = ROOT / "haehan-server.spec"
ADMIN_WEB = ROOT / "admin-web"
ELECTRON_DIR = ADMIN_WEB / "electron"


def run(cmd: list[str], cwd: Path | None = None, shell: bool = False) -> int:
    """명령어 실행 후 returncode 반환."""
    print(f"\n{'=' * 60}")
    print(f"▶ {' '.join(str(c) for c in cmd)}")
    print(f"  cwd: {cwd or ROOT}")
    print(f"{'=' * 60}")
    result = subprocess.run(cmd, cwd=cwd or ROOT, shell=shell)
    if result.returncode != 0:
        print(f"❌ 실패 (exit={result.returncode}): {' '.join(str(c) for c in cmd)}")
    return result.returncode


def step_next_build() -> bool:
    """Next.js 프로덕션 빌드."""
    print("\n🔨 [1/3] Next.js 빌드...")
    rc = run(["npm", "run", "build"], cwd=ADMIN_WEB, shell=True)
    if rc != 0:
        return False
    print("✅ Next.js 빌드 완료")
    return True


def step_pyinstaller() -> bool:
    """PyInstaller로 FastAPI 서버 번들."""
    print("\n🔨 [2/3] PyInstaller 번들...")
    if DIST_SERVER.exists():
        print(f"  기존 dist 삭제: {DIST_SERVER}")
        shutil.rmtree(DIST_SERVER)

    rc = run(
        [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--distpath", str(ROOT / "dist"), "--noconfirm"],
        cwd=ROOT,
    )
    if rc != 0:
        return False
    if not DIST_SERVER.exists():
        print(f"❌ 번들 결과 없음: {DIST_SERVER}")
        return False

    # 크기 확인
    total = sum(f.stat().st_size for f in DIST_SERVER.rglob("*") if f.is_file())
    print(f"✅ FastAPI 번들 완료 ({total // 1024 // 1024}MB): {DIST_SERVER}")
    return True


def step_electron_build() -> bool:
    """electron-builder로 NSIS 인스톨러 생성."""
    print("\n🔨 [3/3] Electron 인스톨러 빌드...")

    # dist/haehan-server 존재 확인
    if not DIST_SERVER.exists():
        print(f"❌ FastAPI 번들 없음 — 먼저 PyInstaller 빌드 필요: {DIST_SERVER}")
        return False

    rc = run(["npm", "run", "dist:win"], cwd=ELECTRON_DIR, shell=True)
    if rc != 0:
        return False

    # 생성된 파일 확인
    installers = list(DIST_ELECTRON.glob("*.exe"))
    if installers:
        for f in installers:
            size_mb = f.stat().st_size // 1024 // 1024
            print(f"✅ 인스톨러 생성: {f.name} ({size_mb}MB)")
    else:
        print("⚠️  .exe 파일이 dist-electron/ 에서 발견되지 않음")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Haehan AI 인스톨러 빌드")
    parser.add_argument("--skip-next", action="store_true", help="Next.js 빌드 생략")
    parser.add_argument("--skip-py", action="store_true", help="PyInstaller 생략")
    parser.add_argument("--skip-electron", action="store_true", help="Electron 빌드 생략")
    args = parser.parse_args()

    t0 = time.time()
    failed = []

    if not args.skip_next:
        if not step_next_build():
            failed.append("Next.js")
    else:
        print("⏭️  Next.js 빌드 생략")

    if not args.skip_py:
        if not step_pyinstaller():
            failed.append("PyInstaller")
    else:
        print("⏭️  PyInstaller 생략")

    if not args.skip_electron:
        if not step_electron_build():
            failed.append("Electron")
    else:
        print("⏭️  Electron 빌드 생략")

    elapsed = int(time.time() - t0)
    print(f"\n{'=' * 60}")
    if failed:
        print(f"❌ 빌드 실패: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"✅ 빌드 완료 ({elapsed}초)")
        print(f"   인스톨러 위치: {DIST_ELECTRON}/")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
