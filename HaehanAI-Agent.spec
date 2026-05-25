# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = []
hiddenimports = [
    'websockets', 'keyring', 'keyring.backends.Windows',
    'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
    'pystray', 'pystray._win32',
    'PIL', 'PIL.Image', 'PIL.ImageDraw',
    'customtkinter',
    'starlette.middleware.base',
    'uvicorn', 'fastapi', 'httpx',
    'desktop.app_config',
    'desktop.remote_access',
    'desktop.local_runner',
    'desktop.status_provider',
    'desktop.task_receiver',
    'desktop.local_server',
    'desktop.user_settings',
]
datas += collect_data_files('customtkinter')
hiddenimports += collect_submodules('local_agent')
hiddenimports += collect_submodules('desktop')


a = Analysis(
    ['build\\agent_launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HaehanAI-Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HaehanAI-Agent',
)
