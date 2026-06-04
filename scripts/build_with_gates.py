"""Haehan AI 게이트 빌드 스크립트.

게이트 구조:
  Gate 0 (Pre)  — 소스 존재, app-builder 실행 가능 여부
  Gate 1 (Post) — 출력 exe 크기 > 100MB, resources 내 server/ + nextjs/ + local-agent/ 포함
  Gate 2 (Smoke)— NSIS 인스톨러 + portable exe 모두 존재

사용:
    python scripts/build_with_gates.py
    python scripts/build_with_gates.py --skip-next      # Next.js 빌드 생략
    python scripts/build_with_gates.py --skip-py        # haehan-server PyInstaller 생략
    python scripts/build_with_gates.py --skip-agent     # local-agent PyInstaller 생략
    python scripts/build_with_gates.py --skip-electron
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
DIST_AGENT = ROOT / "dist" / "local-agent"
DIST_OUT = ROOT / "dist-installer"
ADMIN_WEB = ROOT / "admin-web"
ELECTRON_DIR = ADMIN_WEB / "electron"
NEXT_STANDALONE = ADMIN_WEB / ".next" / "standalone"
SPEC_FILE = ROOT / "haehan-server.spec"
AGENT_SPEC_FILE = ROOT / "local-agent.spec"

# ── 유틸 ──────────────────────────────────────────────────────────────────────


def run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"\n{'=' * 60}\n▶ {' '.join(str(c) for c in cmd)}\n  cwd: {cwd or ROOT}\n{'=' * 60}")
    result = subprocess.run(cmd, cwd=str(cwd or ROOT), shell=False)
    if result.returncode != 0:
        print(f"❌ 실패 (exit={result.returncode})")
    return result.returncode


def run_shell(cmd: str, cwd: Path | None = None) -> int:
    print(f"\n{'=' * 60}\n▶ {cmd}\n  cwd: {cwd or ROOT}\n{'=' * 60}")
    result = subprocess.run(cmd, cwd=str(cwd or ROOT), shell=True)
    if result.returncode != 0:
        print(f"❌ 실패 (exit={result.returncode})")
    return result.returncode


def dir_size_mb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1024 / 1024


# ── Gate 0 : Pre-build ────────────────────────────────────────────────────────


def gate0_pre(skip_next: bool, skip_py: bool) -> list[str]:
    """빌드 전 사전 조건 검사. 문제 목록 반환."""
    issues: list[str] = []

    if not skip_next:
        pkg = ADMIN_WEB / "package.json"
        if not pkg.exists():
            issues.append(f"admin-web/package.json 없음: {pkg}")

    if not skip_py:
        spec = SPEC_FILE
        if not spec.exists():
            issues.append(f"PyInstaller spec 없음: {spec}")

    # electron node_modules
    eb = ELECTRON_DIR / "node_modules" / "electron-builder"
    if not eb.exists():
        issues.append("electron-builder node_modules 없음 — npm install 필요")

    # app-builder.exe 실행 가능 여부
    ab = ELECTRON_DIR / "node_modules" / "app-builder-bin" / "win" / "x64" / "app-builder.exe"
    if not ab.exists():
        issues.append(f"app-builder.exe 없음: {ab}")
    else:
        r = subprocess.run([str(ab), "--version"], capture_output=True, timeout=10)
        if r.returncode != 0:
            issues.append(f"app-builder.exe 실행 실패 (exit={r.returncode}): {r.stderr.decode(errors='replace')[:200]}")
        else:
            print(f"  ✅ app-builder.exe: {r.stdout.decode(errors='replace').strip()}")

    return issues


# ── 빌드 단계 ─────────────────────────────────────────────────────────────────


def step_next_build() -> bool:
    print("\n🔨 [1/3] Next.js 빌드...")
    if run_shell("npm run build", cwd=ADMIN_WEB) != 0:
        return False

    static_src = ADMIN_WEB / ".next" / "static"
    static_dst = NEXT_STANDALONE / ".next" / "static"
    public_src = ADMIN_WEB / "public"
    public_dst = NEXT_STANDALONE / "public"
    wrapper_src = ELECTRON_DIR / "lib" / "nextjs_wrapper.js"
    wrapper_dst = NEXT_STANDALONE / "wrapper.js"

    for src, dst in [(static_src, static_dst), (public_src, public_dst)]:
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  ✅ 복사: {dst}")
    if wrapper_src.exists():
        shutil.copy2(wrapper_src, wrapper_dst)
        print(f"  ✅ wrapper 복사: {wrapper_dst}")

    print("✅ Next.js 빌드 완료")
    return True


def step_pyinstaller() -> bool:
    print("\n🔨 [2/4] haehan-server PyInstaller 번들...")
    if DIST_SERVER.exists():
        shutil.rmtree(DIST_SERVER)
    if run([sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--distpath", str(ROOT / "dist"), "--noconfirm"]) != 0:
        return False
    if not DIST_SERVER.exists():
        print(f"❌ 번들 결과 없음: {DIST_SERVER}")
        return False
    mb = dir_size_mb(DIST_SERVER)
    print(f"✅ FastAPI 번들 완료 ({mb:.0f}MB): {DIST_SERVER}")
    return True


def step_agent_pyinstaller() -> bool:
    print("\n🔨 [3/4] local-agent PyInstaller 번들...")
    if DIST_AGENT.exists():
        shutil.rmtree(DIST_AGENT)
    if (
        run(
            [sys.executable, "-m", "PyInstaller", str(AGENT_SPEC_FILE), "--distpath", str(ROOT / "dist"), "--noconfirm"]
        )
        != 0
    ):
        return False
    if not DIST_AGENT.exists():
        print(f"❌ 번들 결과 없음: {DIST_AGENT}")
        return False
    exe = DIST_AGENT / "local-agent.exe"
    if not exe.exists():
        print(f"❌ local-agent.exe 없음: {exe}")
        return False
    mb = dir_size_mb(DIST_AGENT)
    print(f"✅ local-agent 번들 완료 ({mb:.0f}MB): {DIST_AGENT}")
    return True


def step_electron_build() -> bool:
    print("\n🔨 [4/4] Electron 인스톨러 빌드 (2단계)...")
    if not DIST_SERVER.exists():
        print(f"❌ FastAPI 번들 없음: {DIST_SERVER}")
        return False

    # 이전 빌드 잠금 프로세스 종료 + win-unpacked 삭제
    import subprocess as _sp

    for proc_name in ["haehan-server", "chrome", "Haehan AI"]:
        _sp.run(["taskkill", "/F", "/IM", f"{proc_name}.exe"], capture_output=True)
    unpacked_old = DIST_OUT / "win-unpacked"
    if unpacked_old.exists():
        shutil.rmtree(unpacked_old, ignore_errors=True)
    import time as _t

    _t.sleep(2)

    # package.json output을 dist-installer 로 고정 (--dir / --prepackaged 모두 적용)
    pkg_json = ELECTRON_DIR / "package.json"
    original = pkg_json.read_text(encoding="utf-8")
    patched = original.replace('"../../dist-electron-new"', '"../../dist-installer"')
    pkg_json.write_text(patched, encoding="utf-8")

    try:
        unpacked = DIST_OUT / "win-unpacked"

        # 1단계: --dir 으로 win-unpacked 생성 (인스톨러 미생성)
        print("  [4-1] win-unpacked 생성 (--dir)...")
        rc = run_shell("npx electron-builder --win --dir", cwd=ELECTRON_DIR)
        if rc != 0:
            return False

        # 2단계: standalone/node_modules 수동 복사 (electron-builder 기본 제외 우회)
        nm_src = NEXT_STANDALONE / "node_modules"
        nm_dst = unpacked / "resources" / "nextjs" / "node_modules"
        if nm_src.exists():
            print(f"  [4-2] node_modules 복사: {nm_src} → {nm_dst}")
            if nm_dst.exists():
                shutil.rmtree(nm_dst)
            shutil.copytree(nm_src, nm_dst)
            mb = dir_size_mb(nm_dst)
            print(f"  ✅ node_modules 복사 완료 ({mb:.0f}MB)")
        else:
            print(f"  ⚠️  standalone/node_modules 없음: {nm_src}")

        # 3단계: --prepackaged 로 인스톨러만 생성
        print("  [4-3] 인스톨러 패키징 (--prepackaged)...")
        rc = run_shell(
            f'npx electron-builder --win --prepackaged "{unpacked}"',
            cwd=ELECTRON_DIR,
        )
        return rc == 0

    finally:
        pkg_json.write_text(original, encoding="utf-8")  # 원복


# ── Gate 1 : Post-Electron ────────────────────────────────────────────────────


def gate1_post_electron() -> list[str]:
    issues: list[str] = []

    exes = list(DIST_OUT.glob("*.exe")) if DIST_OUT.exists() else []
    if not exes:
        issues.append(f"출력 exe 없음: {DIST_OUT}")
        return issues

    for exe in exes:
        size_mb = exe.stat().st_size / 1024 / 1024
        if size_mb < 100:
            issues.append(f"{exe.name} 크기 {size_mb:.1f}MB < 100MB — 번들 누락 의심")
        else:
            print(f"  ✅ {exe.name}: {size_mb:.0f}MB")

    # win-unpacked/resources 구조 확인
    unpacked = DIST_OUT / "win-unpacked" / "resources"
    min_sizes = {"server": 100, "nextjs": 20, "local-agent": 10}
    for required, min_mb in min_sizes.items():
        p = unpacked / required
        if not p.exists():
            issues.append(f"resources/{required}/ 없음 — extraResources 누락")
        else:
            mb = dir_size_mb(p)
            if mb < min_mb:
                issues.append(f"resources/{required}/ {mb:.0f}MB < {min_mb}MB — 번들 불완전 (node_modules 누락 등)")
            else:
                print(f"  ✅ resources/{required}/: {mb:.0f}MB")
    # nextjs node_modules 존재 확인
    nm = unpacked / "nextjs" / "node_modules"
    if not nm.exists():
        issues.append("resources/nextjs/node_modules/ 없음 — Next.js 모듈 누락")

    return issues


# ── Gate 2 : Smoke ────────────────────────────────────────────────────────────


def gate2_smoke() -> list[str]:
    issues: list[str] = []

    nsis = list(DIST_OUT.glob("*Setup*.exe"))
    portable = list(DIST_OUT.glob("*portable*.exe"))

    if not nsis:
        issues.append("NSIS 인스톨러(*Setup*.exe) 없음")
    else:
        print(f"  ✅ NSIS: {nsis[0].name}")

    if not portable:
        issues.append("Portable exe(*portable*.exe) 없음")
    else:
        print(f"  ✅ Portable: {portable[0].name}")

    return issues


# ── 메인 ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Haehan AI 게이트 빌드")
    parser.add_argument("--skip-next", action="store_true")
    parser.add_argument("--skip-py", action="store_true")
    parser.add_argument("--skip-agent", action="store_true")
    parser.add_argument("--skip-electron", action="store_true")
    args = parser.parse_args()

    t0 = time.time()

    # ── Gate 0 ──
    print("\n" + "=" * 60)
    print("🔍 Gate 0: Pre-build 점검")
    print("=" * 60)
    issues = gate0_pre(args.skip_next, args.skip_py)
    if issues:
        for i in issues:
            print(f"  ❌ {i}")
        print("\n[Gate 0] FAIL — 빌드 중단")
        sys.exit(1)
    print("[Gate 0] PASS ✅")

    # ── 빌드 단계 ──
    failed: list[str] = []

    if not args.skip_next:
        if not step_next_build():
            failed.append("Next.js")
    else:
        print("⏭️  Next.js 생략")

    if not args.skip_py:
        if not step_pyinstaller():
            failed.append("haehan-server")
    else:
        print("⏭️  haehan-server PyInstaller 생략")

    if not args.skip_agent:
        if not step_agent_pyinstaller():
            failed.append("local-agent")
    else:
        print("⏭️  local-agent PyInstaller 생략")

    if failed:
        print(f"\n❌ 선행 빌드 실패: {', '.join(failed)} — Electron 단계 중단")
        sys.exit(1)

    if not args.skip_electron:
        if not step_electron_build():
            failed.append("Electron")
    else:
        print("⏭️  Electron 생략")

    if "Electron" in failed:
        print("\n[Electron] FAIL — 게이트 진행 불가")
        sys.exit(1)

    # ── Gate 1 ──
    print("\n" + "=" * 60)
    print("🔍 Gate 1: Post-Electron 출력 점검")
    print("=" * 60)
    issues = gate1_post_electron()
    if issues:
        for i in issues:
            print(f"  ❌ {i}")
        print("\n[Gate 1] FAIL")
        sys.exit(1)
    print("[Gate 1] PASS ✅")

    # ── Gate 2 ──
    print("\n" + "=" * 60)
    print("🔍 Gate 2: Smoke 점검")
    print("=" * 60)
    issues = gate2_smoke()
    if issues:
        for i in issues:
            print(f"  ❌ {i}")
        print("\n[Gate 2] FAIL")
        sys.exit(1)
    print("[Gate 2] PASS ✅")

    elapsed = int(time.time() - t0)
    print(f"\n{'=' * 60}")
    print(f"✅ 빌드 + 게이트 전체 PASS ({elapsed}초)")
    print(f"   인스톨러 위치: {DIST_OUT}/")
    for exe in sorted(DIST_OUT.glob("*.exe")):
        print(f"   📦 {exe.name}  ({exe.stat().st_size / 1024 / 1024:.0f}MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
