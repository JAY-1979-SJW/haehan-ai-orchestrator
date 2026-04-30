# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — haehan desktop local_agent (console exe).

빌드 예 (Windows):
  pyinstaller packaging/local-agent.spec --noconfirm

산출물:
  dist/haehan-agent/haehan-agent.exe  (onedir 모드)

빌드 산출물(dist/, build/, *.spec.bak)은 git에 커밋하지 않는다.
"""
import os

block_cipher = None

REPO_ROOT = os.path.abspath(os.path.dirname(SPEC))
ENTRY = os.path.join(REPO_ROOT, "..", "local_agent", "agent.py")

hiddenimports = [
    # network / async
    "websockets",
    "websockets.client",
    "websockets.exceptions",
    # screenshots (실제 호출은 사용자 액션 시점)
    "PIL.ImageGrab",
    "PIL.Image",
    # Windows credential store
    "keyring",
    "keyring.backends.Windows",
    # 기타
    "platform",
    "json",
]

a = Analysis(
    [ENTRY],
    pathex=[os.path.abspath(os.path.join(REPO_ROOT, ".."))],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 데스크톱 패키지에는 필요 없는 서버측 의존성 제거
        "fastapi",
        "uvicorn",
        "starlette",
        "google",
        "openai",
        "playwright",
    ],
    noarchive=False,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="haehan-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
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
    name="haehan-agent",
)
