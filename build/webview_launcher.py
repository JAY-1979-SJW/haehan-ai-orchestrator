"""HaehanAI-Desktop PyInstaller entry point.

HAEHAN_SINGLE_EXE_BUILD_01 — main_launcher 통합 진입점으로 재배선.
consent / tray / whoami / admin webview 흐름은 desktop.main_launcher.main()
이 일관되게 분기한다. webview_app_pywebview.main() 직접 호출은 사용하지 않는다.
"""
import sys
from desktop.main_launcher import main

sys.exit(main())
