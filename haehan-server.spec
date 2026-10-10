# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for haehan-ai FastAPI server.

빌드:
    python -m PyInstaller haehan-server.spec --noconfirm --clean --distpath dist
결과:
    dist/haehan-server/haehan-server.exe

2026-10-07 복구(W2, 데스크톱 릴리스 빌드 워크플로): 2026-09-23 b13d1216에서
삭제됐다가 전체 복구. 그 사이 루트 모듈 분리(orchestrator_v1/)로 진입점이
scripts/run_server.py → ai_orchestrator/asgi.py 로 바뀌어 반영했고,
scripts.browser_agent(삭제됨)를 hidden_imports에서 뺐다. ai_orchestrator/storage
와 data/ 는 사용자 데이터(계정 DB·감사 로그 등)가 들어있어 번들에서 명시적으로
제외한다(DESKTOP_RUNTIME_AUDIT.md D1/D3 — CI는 git 체크아웃이라 애초에 비어
있지만, 로컬에서 실수로 빌드해도 안 들어가게 방어적으로 막아 둔다).
"""

import sys
import os
from pathlib import Path

import playwright

ROOT = Path(SPECPATH)

block_cipher = None

# ── Hidden imports ──────────────────────────────────────────────────────────
hidden_imports = [
    # ai_orchestrator 패키지 (uvicorn 문자열 import 대응)
    "ai_orchestrator",
    "ai_orchestrator.server",
    "ai_orchestrator.routers.registry",
    "tools.gates.auth",
    "ai_orchestrator.auth.user_db",
    "ai_orchestrator.agent_hub.registry.facade",
    "ai_orchestrator.agent_hub.registry.common",
    "ai_orchestrator.agent_hub.registry.agent",
    "ai_orchestrator.agent_hub.registry.task_queue",
    "ai_orchestrator.agent_hub.registry.task_lifecycle",
    "ai_orchestrator.agent_hub.registry.task_cancel",
    "ai_orchestrator.agent_hub.registry.cleanup",
    "ai_orchestrator.agent_hub.registry.sanitize",
    "ai_orchestrator.agent_hub.router.root",
    "ai_orchestrator.agent_hub.router.ws",
    "ai_orchestrator.agent_hub.router.registration",
    "ai_orchestrator.audit.audit_logger",
    "scripts.browser.cdp.connection",
    "scripts.browser.page.web_connector",
    "scripts.naver.smartstore.navigation.cdp_popup_manager",
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
    # 메일 프로토콜 (hiworks_mail_reader.py 가 동적 로드 — 정적분석 누락 방지)
    "poplib",
    "imaplib",
    "smtplib",
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

# 우리 패키지는 손으로 적은 목록 대신 하위 모듈 전체를 자동 수집한다 — 폴더를 옮길 때마다 목록이
# 낡아 번들에서 모듈이 빠졌다(2026-10-08 E2E 실측: 루트 shim 이 import_module 로 부르는
# orchestrator_v1.inbox.* 가 정적 분석에 안 잡혀 'No module named orchestrator_v1.inbox').
# 시험 폴더는 번들에 넣지 않는다.
from PyInstaller.utils.hooks import collect_submodules


def _not_tests(name: str) -> bool:
    return ".tests" not in name and not name.endswith("tests")


for _pkg in ("ai_orchestrator", "orchestrator_v1"):
    hidden_imports += collect_submodules(_pkg, filter=_not_tests)

# ── Data files ──────────────────────────────────────────────────────────────
def _tree_excluding(src_dir: Path, dest_prefix: str, exclude_dirnames: set[str]) -> list[tuple[str, str]]:
    """src_dir 전체를 (file, dest) 목록으로 모으되, exclude_dirnames 에 든 하위
    폴더(예: 'storage' — 계정 DB·감사 로그 등 사용자 데이터)는 통째로 뺀다.
    CI는 git 체크아웃이라 storage/ 가 비어 있지만(.gitignore), 로컬에서 실수로
    빌드해도 사용자 데이터가 번들에 안 들어가게 방어적으로 막는다(D1/D3)."""
    out: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirnames and d != "__pycache__"]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = full.relative_to(src_dir)
            dest = str(Path(dest_prefix) / rel.parent) if str(rel.parent) != "." else dest_prefix
            out.append((str(full), dest))
    return out


datas = [
    # .env (로컬 전용 — 배포용 제거 가능)
    # (str(ROOT / '.env'), '.'),
    # configs
    (str(ROOT / 'configs'), 'configs'),
    # ai_orchestrator 패키지 내 데이터 (storage/ 제외 — 계정 DB·감사 로그 등 사용자 데이터)
    *_tree_excluding(ROOT / 'ai_orchestrator', 'ai_orchestrator', {'storage'}),
    # scripts 전체 (realtime_audit, naver, google 등 런타임 import)
    (str(ROOT / 'scripts'), 'scripts'),
    # 루트 레벨 모듈 (logging_utils 등 ai_orchestrator가 직접 import)
    *[(str(p), '.') for p in ROOT.glob('*.py') if p.stem not in ('run_server', 'conftest')],
    # Playwright 드라이버 (driver/package). sys.executable 기준(= Path(sys.executable).parent
    # / 'Lib' / 'site-packages')은 venv 에서 틀린다 — venv 의 sys.executable 은
    # Scripts\python.exe 라 그 parent 가 Scripts 지 site-packages 를 담은 폴더가 아니다
    # (venv 로컬 빌드 리허설 2026-10-10 실측: ..\Scripts\Lib\site-packages 로 꺾여 FileNotFoundError).
    # 패키지 자신의 설치 위치(playwright.__file__)를 기준으로 하면 venv·非venv 모두 맞다.
    (str(Path(playwright.__file__).resolve().parent / 'driver'), 'playwright/driver'),
]

# ── Playwright Chromium 번들 제외 (2026-09-09) ────────────────────────────────
# 예전엔 대상 PC에 Chrome 미설치 시에도 동작하도록 425MB 짜리 Chromium을 통째로
# 번들했으나, 설치 파일이 너무 커져(15,000+ 파일, 2.2GB) 배포/설치 시간이 과도해짐.
# 대상 PC에 Google Chrome 설치를 전제로 바꾸고 번들을 뺀다(admin-web/electron/
# lib/cdp_manager.js 가 Chrome 미탐지 시 설치 안내 다이얼로그를 띄움).
print("[spec] Chromium 번들 제외 — 대상 PC에 Google Chrome 설치 필요(cdp_manager.js가 안내)")

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    # 진입점: 상대 import 가 없는 전용 진입 파일. asgi.py 를 직접 쓰면 단독 스크립트로 실행돼
    # `from . import config` 가 실패한다(2026-10-08 첫 빌드 E2E fastapi.log 실측).
    [str(ROOT / 'ai_orchestrator' / 'server' / 'desktop_entry.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],  # build_hooks/ 삭제 후 미복구 — 현재 커스텀 훅 없음
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
