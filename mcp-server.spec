# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for haehan-ai MCP server (Claude Desktop 연동용, 경량).

ai_orchestrator/mcp_server.py 는 로컬 FastAPI(127.0.0.1:8401)를 HTTP로 호출하는
얇은 프록시라 haehan-server.spec(전체 백엔드, torch/cv2 등 포함)과 달리 가볍게 빌드된다.
상세설명 생성(gpt_description_writer)과 스마트스토어 CDP 수집(playwright)만 실제 의존성.

빌드:
    python -m PyInstaller mcp-server.spec --noconfirm --clean --distpath dist
결과:
    dist/haehan-mcp/haehan-mcp.exe
"""

from pathlib import Path

ROOT = Path(SPECPATH)

block_cipher = None

hidden_imports = [
    "mcp",
    "mcp.server",
    "mcp.server.stdio",
    "mcp.types",
    "requests",
    "playwright",
    "playwright.sync_api",
    "ai_orchestrator.app_llm",
    "scripts.naver.smartstore.product.gpt_description_writer",
    "scripts.critical_logger",
    "scripts.logger",
]

a = Analysis(
    [str(ROOT / "ai_orchestrator" / "mcp_server.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "cv2", "pandas", "scipy", "numpy", "matplotlib"],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="haehan-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="haehan-mcp",
)
