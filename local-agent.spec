# ruff: noqa
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for local CDP agent.

빌드:
    python -m PyInstaller local-agent.spec --noconfirm --clean --distpath dist
결과:
    dist/local-agent/local-agent.exe

2026-10-07 복구(W2): 2026-09-23 b13d1216에서 삭제됐다가 전체 복구. 진입점
core/agent_runtime/runtime/local_agent.py와 hidden_imports의 smartstore 경로는 그대로 유효해
변경 없음(정적 점검으로 확인, 실제 빌드는 CI 첫 실행에서 확인).
"""

import os
from pathlib import Path

ROOT = Path(SPECPATH)

hidden_imports = [
    "websocket",
    "websocket._abnf",
    "websocket._core",
    "websocket._exceptions",
    "websocket._handshake",
    "websocket._http",
    "websocket._logging",
    "websocket._socket",
    "websocket._ssl_compat",
    "websocket._utils",
    "playwright",
    "playwright.sync_api",
    "playwright.async_api",
    "playwright._impl._api_types",
    # smartstore modules
    "scripts.naver.smartstore",
    "scripts.naver.smartstore.product.form_runner",
    "scripts.naver.smartstore.navigation.cdp_popup_manager",
    "scripts.naver.smartstore.navigation.popup_handler",
    # stdlib
    "ctypes",
    "threading",
    "json",
    "argparse",
]

datas = [
    # scripts 전체 (smartstore 모듈 포함)
    (str(ROOT / "scripts"), "scripts"),
    # configs
    (str(ROOT / "configs"), "configs"),
]

# Playwright 드라이버 번들 (playwright inspect node 등)
try:
    import playwright
    pw_path = Path(playwright.__file__).parent
    if pw_path.exists():
        datas.append((str(pw_path), "playwright"))
        print(f"[spec] Playwright 번들: {pw_path}")
except Exception as e:
    print(f"[spec] WARNING: Playwright 경로 탐지 실패: {e}")

a = Analysis(
    [str(ROOT / "scripts" / "local_agent.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="local-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="local-agent",
)
