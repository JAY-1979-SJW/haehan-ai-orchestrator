# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all
from pathlib import Path
import playwright as _pw
_pw_driver = Path(_pw.__file__).parent / 'driver'

hiddenimports = [
    # webview
    'webview', 'webview.platforms.winforms', 'webview.platforms.edgechromium',
    # uvicorn + asgi
    'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl', 'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
    # fastapi / starlette
    'fastapi', 'fastapi.middleware', 'fastapi.middleware.cors',
    'starlette', 'starlette.staticfiles', 'starlette.responses',
    'starlette.middleware', 'starlette.middleware.base',
    'starlette.middleware.cors',
    # anyio (uvicorn 내부 의존)
    'anyio', 'anyio._backends._asyncio', 'anyio._backends._trio',
    'anyio.abc', 'anyio.streams',
    # h11
    'h11', 'h11._readers', 'h11._writers',
    # httpx
    'httpx', 'httpx._transports', 'httpx._transports.default',
    # websockets
    'websockets', 'websockets.legacy', 'websockets.legacy.client',
    'websockets.legacy.server',
    # keyring
    'keyring', 'keyring.backends', 'keyring.backends.Windows',
    # pythonnet / clr
    'clr', 'clr_loader',
    # 기타
    'psutil', 'httptools', 'sniffio', 'exceptiongroup',
]
hiddenimports += collect_submodules('webview')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')
hiddenimports += collect_submodules('anyio')
hiddenimports += collect_submodules('local_agent')
hiddenimports += collect_submodules('desktop')
hiddenimports += collect_submodules('playwright')
hiddenimports += collect_submodules('h11')
hiddenimports += collect_submodules('httpx')
hiddenimports += collect_submodules('httptools')

# collect_all: 바이너리+데이터+서브모듈 강제 수집
_uvicorn_d, _uvicorn_b, _uvicorn_h  = collect_all('uvicorn')
_fastapi_d, _fastapi_b, _fastapi_h  = collect_all('fastapi')
_starlette_d, _starlette_b, _starlette_h = collect_all('starlette')
_anyio_d, _anyio_b, _anyio_h        = collect_all('anyio')
_h11_d, _h11_b, _h11_h              = collect_all('h11')
_httpx_d, _httpx_b, _httpx_h        = collect_all('httpx')
hiddenimports += _uvicorn_h + _fastapi_h + _starlette_h + _anyio_h + _h11_h + _httpx_h

a = Analysis(
    ['C:\\Users\\skyjw\\OneDrive\\03. PYTHON\\35. haehan-ai-orchestrator\\build\\webview_launcher.py'],
    pathex=['C:\\Users\\skyjw\\OneDrive\\03. PYTHON\\35. haehan-ai-orchestrator'],
    datas=[
        ('C:\\Users\\skyjw\\OneDrive\\03. PYTHON\\35. haehan-ai-orchestrator\\desktop\\ui_dist', 'desktop/ui_dist'),
        (str(_pw_driver), 'playwright/driver'),
        *_uvicorn_d, *_fastapi_d, *_starlette_d, *_anyio_d, *_h11_d, *_httpx_d,
    ],
    binaries=[
        *_uvicorn_b, *_fastapi_b, *_starlette_b, *_anyio_b, *_h11_b, *_httpx_b,
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'pytest_asyncio'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HaehanAI-Desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HaehanAI-Desktop',
)
