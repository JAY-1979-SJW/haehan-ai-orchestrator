"""로컬 에이전트 설정 (Stage 1).

환경 변수로 오버라이드 가능하지만 기본값은 모두 안전 모드 — 외부 호출 금지,
read-only 디렉터리만 화이트리스트.
"""
from __future__ import annotations

import os
from pathlib import Path


# 서버 오케스트레이터 base URL (사용자가 명시적으로 설정해야 함)
SERVER_BASE_URL: str = os.getenv("HAEHAN_AGENT_SERVER", "http://127.0.0.1:8400")

# 1단계는 폴링 모드. WebSocket 푸시는 2단계에서 활성화.
WEBSOCKET_ENABLED: bool = os.getenv("HAEHAN_AGENT_WS_ENABLED", "false").lower() == "true"

# 폴링 주기 (초)
POLL_INTERVAL_SEC: int = int(os.getenv("HAEHAN_AGENT_POLL_SEC", "10"))

# 에이전트가 실행 가능한 PC 측 앱 (1단계는 browser 만 실제 실행)
ALLOWED_APPS: list[str] = ["browser", "excel", "hwp", "cad"]
APPS_EXECUTABLE_STAGE1: frozenset[str] = frozenset({"browser"})

# list_files_readonly 가 접근 가능한 디렉터리 화이트리스트.
# 절대 시스템/사용자 비밀 디렉터리를 추가하지 말 것.
READ_ONLY_DIRS: list[Path] = [
    Path(os.getenv("HAEHAN_AGENT_PUBLIC_DIR", str(Path.home() / "Documents" / "haehan-public"))),
]

# 로컬 감사 로그 파일 (PC 내부 보관, 서버에는 요약만 보고)
LOCAL_AUDIT_PATH: Path = Path(
    os.getenv("HAEHAN_AGENT_AUDIT", str(Path.home() / ".haehan_agent" / "audit.jsonl"))
)

# device_token 보관 위치 (사용자 홈, 권한 600 권장 — Windows 는 ACL 별도 안내)
TOKEN_STORE_PATH: Path = Path(
    os.getenv("HAEHAN_AGENT_TOKEN", str(Path.home() / ".haehan_agent" / "device_token"))
)

# open_url 허용 스킴
URL_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# Stage 3: capture_screenshot 이 저장할 로컬 디렉터리. 서버로 업로드하지 않는다.
# 기본값은 사용자 홈 하위의 비공개 디렉터리 — 사용자가 필요 시 명시적으로
# 공유할 수 있도록 분리. 절대 OneDrive / 공용 폴더를 기본값으로 두지 않는다.
LOCAL_AGENT_SCREENSHOT_DIR: Path = Path(
    os.getenv(
        "LOCAL_AGENT_SCREENSHOT_DIR",
        str(Path.home() / ".haehan_agent" / "screenshots"),
    )
)


__all__ = [
    "SERVER_BASE_URL", "WEBSOCKET_ENABLED", "POLL_INTERVAL_SEC",
    "ALLOWED_APPS", "APPS_EXECUTABLE_STAGE1",
    "READ_ONLY_DIRS", "LOCAL_AUDIT_PATH", "TOKEN_STORE_PATH",
    "URL_ALLOWED_SCHEMES",
    "LOCAL_AGENT_SCREENSHOT_DIR",
]
