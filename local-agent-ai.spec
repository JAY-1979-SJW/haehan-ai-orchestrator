# ruff: noqa
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AI 작업 콘솔 로컬 에이전트 (local_agent/agent.py).

빌드:
    python -m PyInstaller local-agent-ai.spec --noconfirm --clean --distpath dist
결과:
    dist/local-agent-ai/local-agent-ai.exe

local-agent.spec(scripts/local_agent.py = 스마트스토어 전용 옛 에이전트)와는 다른 프로그램이다.
이 에이전트는 /api/v1/local-agents/ws 로 접속해 AI 작업 콘솔의 run_claude_agent 작업을 받는다.
2026-10-08 결함: 설치본이 이 에이전트를 번들하지 않아 설치 앱의 AI 작업 콘솔이 항상 "미연결"(503)이었다.

- 진입점은 상대 import 가 없는 scripts/local_agent_ai_entry.py (agent.py 는 상대 import 사용).
- local_agent/* 는 actions 가 동적으로 부르는 모듈이 많아 collect_submodules 로 통째로 담는다.
- keyring(Windows Credential Manager)은 entry point(메타데이터)로 백엔드를 찾으므로 메타데이터와 백엔드를 명시한다.
- 서버 패키지(ai_orchestrator)는 actions 가 일부(계약·정책 상수)만 import 한다 — 정적 분석이 따라간 만큼만 담는다.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH)

hidden_imports = [
    "websockets",
    "websockets.asyncio.client",
    "websocket",
    "keyring",
    "keyring.backends",
    "keyring.backends.Windows",
    "win32ctypes.pywin32.pywintypes",
    "win32ctypes.pywin32.win32cred",
    "ai_orchestrator.server.desktop_entry",
    "ai_orchestrator.local_agent_actions",
    "ai_orchestrator.contracts.agent_result_limits",
    "ai_orchestrator.browser_tool",
    "playwright",
    "playwright.sync_api",
    "playwright.async_api",
    "scripts.web_connector",
    "scripts.navigator",
    "scripts.browser_sandbox_gate",
]
hidden_imports += collect_submodules("local_agent")
hidden_imports += collect_submodules("keyring.backends")

datas = []
for dist_name in ("keyring", "websockets", "jaraco.classes", "jaraco.context", "jaraco.functools", "importlib_metadata"):
    try:
        datas += copy_metadata(dist_name)
    except Exception as exc:  # 없는 배포판은 건너뛴다(선택적 의존)
        print(f"[spec] 메타데이터 생략 {dist_name}: {exc}")

# actions 가 함수 안에서 `from scripts import navigator` 등을 부른다 — local-agent.spec 과 같이 소스째 담는다
datas += [
    (str(ROOT / "scripts"), "scripts"),
    (str(ROOT / "configs"), "configs"),
]

try:
    import playwright

    pw_path = Path(playwright.__file__).parent
    if pw_path.exists():
        datas.append((str(pw_path), "playwright"))
except Exception as exc:
    print(f"[spec] WARNING: Playwright 경로 탐지 실패: {exc}")

a = Analysis(
    [str(ROOT / "scripts" / "local_agent_ai_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "cv2", "pandas", "scipy", "numpy", "tests", "ai_orchestrator.tests"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="local-agent-ai",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="local-agent-ai",
)
