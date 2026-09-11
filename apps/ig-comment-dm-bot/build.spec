# PyInstaller 빌드 설정
# 실행: pyinstaller build.spec
a = Analysis(
    ["main.py"],
    pathex=["."],
    hiddenimports=["keyring.backends.Windows"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="ig-comment-dm-bot",
    console=False,
    onefile=True,
)
