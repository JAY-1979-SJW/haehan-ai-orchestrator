# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for haehan-ai FastAPI server.

빌드:
    pyinstaller haehan-server.spec
결과:
    dist/haehan-server/haehan-server.exe
"""

import sys
import os
from pathlib import Path

ROOT = Path(SPECPATH)

block_cipher = None

# ── Hidden imports ──────────────────────────────────────────────────────────
hidden_imports = [
    # ai_orchestrator 패키지 (uvicorn 문자열 import 대응)
    "ai_orchestrator",
    "ai_orchestrator.server",
    "ai_orchestrator.router",
    "ai_orchestrator.auth",
    "ai_orchestrator.user_db",
    "ai_orchestrator.local_agent_registry",
    "ai_orchestrator.local_agent_registry_common",
    "ai_orchestrator.local_agent_registry_agent",
    "ai_orchestrator.local_agent_registry_task_queue",
    "ai_orchestrator.local_agent_registry_task_lifecycle",
    "ai_orchestrator.local_agent_registry_task_cancel",
    "ai_orchestrator.local_agent_registry_cleanup",
    "ai_orchestrator.local_agent_registry_sanitize",
    "ai_orchestrator.local_agent_router",
    "ai_orchestrator.local_agent_router_ws",
    "ai_orchestrator.local_agent_router_registration",
    "ai_orchestrator.audit_logger",
    # FastAPI / uvicorn
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "fastapi",
    "fastapi.middleware.cors",
    "starlette.routing",
    "starlette.responses",
    "starlette.middleware",
    "starlette.middleware.cors",
    # AI
    "anthropic",
    "openai",
    # Playwright
    "playwright",
    "playwright.sync_api",
    "playwright.async_api",
    # DB / cache
    "sqlite3",
    "aiosqlite",
    # HTTP
    "httpx",
    "httpcore",
    "aiohttp",
    "aiofiles",
    # Utilities
    "websocket",
    "websockets",
    "pillow",
    "PIL",
    "PIL.Image",
    "PIL.ImageEnhance",
    "PIL.ImageOps",
    "pyautogui",
    "pyperclip",
    "pydantic",
    "pydantic.v1",
    "pydantic_settings",
    "python_dotenv",
    "dotenv",
    "cryptography",
    "cryptography.fernet",
    # Windows
    "win32api",
    "win32con",
    "win32gui",
    "winsound",
    "ctypes",
    "ctypes.wintypes",
    # Misc
    "email",
    "email.mime",
    "email.mime.text",
    "email.mime.multipart",
    "jinja2",
    "yaml",
    "toml",
    # Auth / Google
    "jwt",
    "google",
    "google.oauth2",
    "google.oauth2.credentials",
    "google.auth.transport.requests",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.errors",
    # DB
    "psycopg2",
    "psycopg2.extras",
    "psycopg2.extensions",
    # System / UI
    "keyring",
    "pystray",
    "win32clipboard",
    "win32process",
    "win32security",
    "winerror",
    "psutil",
    # Data
    "numpy",
    "openpyxl",
    "openpyxl.styles",
    "openpyxl.utils",
    "requests",
    "requests.adapters",
]

# ── Data files ──────────────────────────────────────────────────────────────
datas = [
    # .env (로컬 전용 — 배포용 제거 가능)
    # (str(ROOT / '.env'), '.'),
    # configs
    (str(ROOT / 'configs'), 'configs'),
    # ai_orchestrator 패키지 내 데이터
    (str(ROOT / 'ai_orchestrator'), 'ai_orchestrator'),
    # scripts 전체 (realtime_audit, naver, google 등 런타임 import)
    (str(ROOT / 'scripts'), 'scripts'),
    # 루트 레벨 모듈 (logging_utils 등 ai_orchestrator가 직접 import)
    *[(str(p), '.') for p in ROOT.glob('*.py') if p.stem not in ('run_server', 'conftest')],
    # Playwright 드라이버 (driver/package)
    (str(Path(sys.executable).parent / 'Lib' / 'site-packages' / 'playwright' / 'driver'), 'playwright/driver'),
]

# ── Playwright Chromium 번들 ─────────────────────────────────────────────────
PLAYWRIGHT_CHROMIUM = Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright' / 'chromium-1223' / 'chrome-win64'
if PLAYWRIGHT_CHROMIUM.exists():
    datas.append((str(PLAYWRIGHT_CHROMIUM), 'chromium/chrome-win64'))
    print(f"[spec] Chromium 번들 포함: {PLAYWRIGHT_CHROMIUM}")
else:
    print(f"[spec] WARNING: Playwright Chromium 없음 — Chrome이 대상 PC에 설치되어야 함")

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / 'scripts' / 'run_server.py')],  # 진입점
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[str(ROOT / 'build_hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy.testing',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='haehan-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,     # 디버그용 콘솔 표시 (배포 시 False)
    icon=str(ROOT / 'admin-web' / 'electron' / 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='haehan-server',
)
