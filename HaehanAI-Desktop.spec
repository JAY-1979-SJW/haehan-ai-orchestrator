# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['webview', 'webview.platforms.winforms', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi', 'starlette', 'starlette.staticfiles', 'starlette.responses', 'httpx', 'websockets', 'websockets.legacy', 'websockets.legacy.client', 'keyring', 'keyring.backends.Windows']
hiddenimports += collect_submodules('webview')
hiddenimports += collect_submodules('local_agent')
hiddenimports += collect_submodules('desktop')


a = Analysis(
    ['C:\\Users\\skyjw\\OneDrive\\03. PYTHON\\35. haehan-ai-orchestrator\\build\\webview_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\skyjw\\OneDrive\\03. PYTHON\\35. haehan-ai-orchestrator\\desktop\\ui_dist', 'desktop/ui_dist')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['playwright', 'pytest', 'pytest_asyncio', 'anyio'],
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
