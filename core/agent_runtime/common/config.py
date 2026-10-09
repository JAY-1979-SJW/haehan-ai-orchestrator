"""로컬 에이전트 설정 (Stage 1).

환경 변수로 오버라이드 가능하지만 기본값은 모두 안전 모드 — 외부 호출 금지,
read-only 디렉터리만 화이트리스트.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[3]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402


def _discover_server_base_url() -> str:
    """서버 base URL 결정 우선순위(2026-09-30, defect_index #18 근본 대책):
    1) HAEHAN_AGENT_SERVER 환경변수 — 명시적 지정은 항상 최우선 존중.
    2) data/runtime/server_info.json — 실제로 지금 뜬 FastAPI 서버가 자기 자신의
       host:port를 기록해둔 자동탐지 파일(ai_orchestrator/asgi.py lifespan 에서 기록).
       포트 충돌로 다른 포트에 뜨거나 여러 인스턴스가 떠 있어도 하드코딩 없이 찾아간다.
    3) 위 둘 다 없으면 기존 하드코딩 기본값(8401)으로 폴백 — 완전히 새 환경(서버를 아직
       한 번도 안 띄워본 상태)에서도 동작해야 하므로 폴백 자체는 유지한다.
    """
    env_val = os.getenv("HAEHAN_AGENT_SERVER", "").strip()
    if env_val:
        return env_val
    try:
        import json

        discovery_path = repo_root() / "data" / "runtime" / "server_info.json"
        if discovery_path.exists():
            info = json.loads(discovery_path.read_text(encoding="utf-8"))
            host, port = info.get("host"), info.get("port")
            if host and port:
                # server.py 는 APP_HOST=0.0.0.0 으로도 기동할 수 있는데, 로컬 클라이언트가
                # 접속할 땐 0.0.0.0(바인딩 전용 주소)이 아니라 127.0.0.1 로 접속해야 한다.
                connect_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host  # noqa: S104
                return f"http://{connect_host}:{port}"
    except (OSError, ValueError, TypeError):
        pass  # 자동탐지 실패는 비치명적 — 아래 하드코딩 기본값으로 폴백
    return "http://127.0.0.1:8401"


# 서버 오케스트레이터 base URL. 자동탐지 우선순위는 _discover_server_base_url() 참고.
SERVER_BASE_URL: str = _discover_server_base_url()

# 1단계는 폴링 모드. WebSocket 푸시는 2단계에서 활성화.
WEBSOCKET_ENABLED: bool = os.getenv("HAEHAN_AGENT_WS_ENABLED", "false").lower() == "true"

# 폴링 주기 (초)
POLL_INTERVAL_SEC: int = int(os.getenv("HAEHAN_AGENT_POLL_SEC", "10"))

# 동시 처리 작업 수 (기본 1 = 직렬, 최대 3) — 기준서 2026-10-02_app_agent_dispatch P1
MAX_PARALLEL: int = max(1, min(3, int(os.getenv("LOCAL_AGENT_MAX_PARALLEL", "1") or "1")))

# 에이전트가 실행 가능한 PC 측 앱 (1단계는 browser 만 실제 실행)
ALLOWED_APPS: list[str] = ["browser", "excel", "hwp", "cad"]
APPS_EXECUTABLE_STAGE1: frozenset[str] = frozenset({"browser"})

# list_files_readonly 가 접근 가능한 디렉터리 화이트리스트.
# 절대 시스템/사용자 비밀 디렉터리를 추가하지 말 것.
READ_ONLY_DIRS: list[Path] = [
    Path(os.getenv("HAEHAN_AGENT_PUBLIC_DIR", str(Path.home() / "Documents" / "haehan-public"))),
]

# 로컬 감사 로그 파일 (PC 내부 보관, 서버에는 요약만 보고)
LOCAL_AUDIT_PATH: Path = Path(os.getenv("HAEHAN_AGENT_AUDIT", str(Path.home() / ".haehan_agent" / "audit.jsonl")))

# device_token 보관 위치 (사용자 홈, 권한 600 권장 — Windows 는 ACL 별도 안내)
TOKEN_STORE_PATH: Path = Path(os.getenv("HAEHAN_AGENT_TOKEN", str(Path.home() / ".haehan_agent" / "device_token")))

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
    "ALLOWED_APPS",
    "APPS_EXECUTABLE_STAGE1",
    "LOCAL_AGENT_SCREENSHOT_DIR",
    "LOCAL_AUDIT_PATH",
    "MAX_PARALLEL",
    "POLL_INTERVAL_SEC",
    "READ_ONLY_DIRS",
    "SERVER_BASE_URL",
    "TOKEN_STORE_PATH",
    "URL_ALLOWED_SCHEMES",
    "WEBSOCKET_ENABLED",
]
