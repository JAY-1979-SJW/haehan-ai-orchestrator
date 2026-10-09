# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for haehan-ai MCP server (Claude Desktop 연동용, 경량).

ai_orchestrator/server/mcp_server.py 는 로컬 FastAPI(127.0.0.1:8401)를 HTTP로 호출하는
얇은 프록시라 haehan-server.spec(전체 백엔드, torch/cv2 등 포함)과 달리 가볍게 빌드된다.
스마트스토어/카페 CDP 수집(playwright)과 로컬 에이전트 브라우저 연동이 실제 의존성.

빌드:
    python -m PyInstaller mcp-server.spec --noconfirm --clean --distpath dist
결과:
    dist/haehan-mcp/haehan-mcp.exe

2026-10-07 복구(W2): 2026-09-23 b13d1216에서 삭제됐다가 복구. OpenAI 제거
(2026-09-24, docs/specs/2026-09-24_openai_removal_claude_mcp.md)로 옛 버전이
쓰던 gpt_description_writer·scripts.common.critical_logger·scripts.logger가
mcp_server.py에서 더 이상 안 보여 hidden_imports에서 뺐다. 대신 현재 코드가
실제로 동적 import하는 경로(scripts.naver.smartstore.*, scripts.naver.cafe.*,
scripts.browser.agent.*)로 갱신했다(정적 점검, 실제 빌드 확인은
CI 첫 실행에서).
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
    "dotenv",
    "playwright",
    "playwright.sync_api",
    "scripts.browser.agent.universal_actions",
    "scripts.browser.agent.electron_target",
    "scripts.naver.smartstore",
    "scripts.naver.smartstore.product.page_builder",
    "scripts.naver.smartstore.product.form_runner",
    "scripts.naver.cafe.management.board",
]

a = Analysis(
    [str(ROOT / "ai_orchestrator" / "mcp_server.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # mcp_server.py가 scripts.naver.* 를 함수 안에서 동적 import — 전체 트리 필요
        (str(ROOT / "scripts" / "naver"), "scripts/naver"),
    ],
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
