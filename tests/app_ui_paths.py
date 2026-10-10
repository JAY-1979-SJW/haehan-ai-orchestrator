"""앱 UI 시험 공용 도우미 — 화면 파일 경로 해석.

화면은 Next.js 라우트 그룹 `app/assistant/(legacy)/<화면>/page.tsx` 로 옮겨졌고, URL 은 그대로다.
시험이 `app/assistant/<화면>/page.tsx` 를 직접 조합하면 파일을 못 찾으므로, 직접 경로를 먼저 보고
없으면 `(legacy)` 안을 본다(`tools/audits/app/audit_app_ui_shell_readonly_api_wiring.py::_route_page` 와 같은 규칙).
저장소 루트는 이 파일 위치 기준 상대 계산 — 절대경로·계정명 하드코딩 없음.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSISTANT_APP_DIR = REPO_ROOT / "admin-web" / "src" / "app" / "assistant"


def assistant_route(*parts: str, app_dir: Path = ASSISTANT_APP_DIR) -> Path:
    """`app/assistant/<parts...>` 를 찾는다. 직접 경로 우선, 없으면 `(legacy)` 아래, 둘 다 없으면 직접 경로."""
    direct = app_dir.joinpath(*parts)
    if direct.exists():
        return direct
    grouped = app_dir.joinpath("(legacy)", *parts)
    return grouped if grouped.exists() else direct
