"""Chrome chrome UI 감시 — chrome_ui_watcher v1.0

UI Automation API로 Chrome 브라우저의 chrome UI(인포바, 세션 복원 풍선,
비밀번호 저장/번역 권유 등) 텍스트를 직접 읽는다. popup_watcher의
범위 밖에 있는 영역을 보완.

요구: uiautomation (Windows 전용)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TypedDict

import uiautomation as uia

from scripts.common.logger import get_logger

_log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DAEMON_STATE = ROOT / "data" / "cdp_daemon_state.json"

# Chrome UI 안의 의미있는 ControlType (호스트 렌더링용 Pane 제외)
_INTERESTING_TYPES = {
    "ButtonControl",
    "TextControl",
    "HyperlinkControl",
    "GroupControl",
    "ToolBarControl",
}

# 위치(주소창 아래 인포바 영역) 추정용 — y좌표가 윈도우 상단으로부터 50-200px 사이일 때
_INFOBAR_Y_MIN = 50
_INFOBAR_Y_MAX = 250

# Chrome chrome UI 패턴 → (마커, 액션, 클릭할 버튼 이름)
# action: 'auto_dismiss' | 'notify_user'
CHROME_UI_RULES: list[tuple[str, list[str], str, str | None]] = [
    # (마커키, 텍스트 키워드[OR], action, 클릭할 버튼)
    (
        "automation_warning",
        [
            "disable-blink-features=AutomationControlled",
            "지원되지 않는 명령줄 플래그",
            "자동 테스트 소프트웨어",
            "automated test software",
            "Chrome is being controlled",
        ],
        "notify_user",
        None,
    ),
    (
        "session_crashed",
        ["페이지 복원", "복원하시겠습니까", "Restore pages", "이전에 닫은 페이지", "정상적으로 종료되지 않"],
        "auto_dismiss",
        "닫기",
    ),
    ("save_password", ["비밀번호를 저장", "Save password", "Save Password"], "auto_dismiss", "나중에"),
    ("translate_offer", ["페이지를 번역", "Translate this page", "이 페이지를 번역"], "auto_dismiss", "아니요"),
    ("update_chrome", ["Chrome 업데이트", "업데이트 가능", "Update available", "Relaunch"], "notify_user", None),
    ("performance_warning", ["성능 문제", "Performance issue", "느려질 수 있"], "auto_dismiss", "닫기"),
    ("download_warning", ["위험할 수 있는 파일", "Dangerous file", "안전한 파일인지"], "notify_user", None),
    (
        "notification_permission",
        ["알림을 표시하시겠습니까", "Show notifications", "wants to show notifications"],
        "auto_dismiss",
        "차단",
    ),
    ("location_permission", ["위치에 액세스", "wants to know your location"], "auto_dismiss", "차단"),
]


class ChromeUIEvent(TypedDict):
    ts_ms: int
    marker: str  # rule key (automation_warning 등)
    snippet: str  # 매칭된 텍스트 일부
    target_window: str  # Chrome 윈도우 제목
    button_name: str | None  # 클릭 제안 버튼 이름


# ── 윈도우/요소 탐색 ─────────────────────────────────────────────────


def _get_daemon_chrome_pid() -> int | None:
    if not DAEMON_STATE.exists():
        return None
    try:
        return int(json.loads(DAEMON_STATE.read_text(encoding="utf-8")).get("chrome_pid") or 0) or None
    except Exception:  # noqa: BLE001 - 데몬 상태 파일 파싱 실패는 "pid 미상"으로 간주해 무시(읽기전용 감시 보조 정보일 뿐)
        return None


def find_chrome_windows(chrome_pid: int | None = None) -> list[uia.Control]:
    """데몬 chrome_pid 매칭 윈도우. None이면 모든 Chrome 윈도우."""
    target_pid = chrome_pid if chrome_pid is not None else _get_daemon_chrome_pid()
    out: list[uia.Control] = []
    try:
        root = uia.GetRootControl()
        for w in root.GetChildren():
            try:
                if w.ClassName != "Chrome_WidgetWin_1":
                    continue
                if target_pid and w.ProcessId != target_pid:
                    continue
                out.append(w)
            except Exception:  # noqa: BLE001 - UI Automation 요소 접근은 창이 그 사이 닫히는 등으로 흔히 실패 — 해당 창 하나만 건너뛰고 스캔 계속(읽기전용 감시)
                continue
    except Exception as e:  # noqa: BLE001 - UI Automation 루트 접근 실패는 이번 스캔 주기를 빈 목록으로 반환하고 다음 주기에 재시도(읽기전용 감시, 크래시 방지 우선)
        _log.warning("[chrome_ui_watcher] root 접근 실패: %s", e)
    return out


def _walk(
    ctrl: uia.Control, depth: int, max_depth: int, max_nodes: int, collected: list[dict], counter: list[int]
) -> None:
    if counter[0] >= max_nodes or depth > max_depth:
        return
    counter[0] += 1
    try:
        ctype = ctrl.ControlTypeName
        name = (ctrl.Name or "").strip()
        cls = ctrl.ClassName or ""
        rect = None
        try:
            r = ctrl.BoundingRectangle
            rect = (int(r.left), int(r.top), int(r.right - r.left), int(r.bottom - r.top))
        except Exception:  # noqa: BLE001 - 일부 UIA 요소는 좌표가 없거나 조회 중 사라짐 — rect=None으로 두고 계속(읽기전용 감시, 좌표는 부가정보)
            pass
        if name and ctype in _INTERESTING_TYPES and len(name) < 500:
            collected.append(
                {
                    "type": ctype,
                    "name": name,
                    "cls": cls,
                    "rect": rect,
                    "depth": depth,
                    "_ctrl": ctrl,
                }
            )
        for c in ctrl.GetChildren():
            _walk(c, depth + 1, max_depth, max_nodes, collected, counter)
    except Exception:  # noqa: BLE001 - 트리 재귀 중 요소 하나가 실패하면 그 하위 트리만 포기하고 리턴(읽기전용 감시, 이미 모은 형제 요소는 유지)
        return


def scan_chrome_ui(window: uia.Control, max_nodes: int = 600) -> list[dict]:
    """윈도우 안의 의미있는 UI 요소 수집."""
    collected: list[dict] = []
    _walk(window, 0, max_depth=20, max_nodes=max_nodes, collected=collected, counter=[0])
    return collected


# ── 알림 감지 ────────────────────────────────────────────────────────


def detect_alerts(window: uia.Control) -> list[ChromeUIEvent]:
    """알려진 chrome UI 패턴을 매칭해 이벤트로 반환."""
    elements = scan_chrome_ui(window)
    win_title = (window.Name or "")[:120]
    now_ms = int(time.time() * 1000)

    # 캡션 버튼/창 컨트롤 버튼 제외 (False positive 방지)
    BLOCKLIST_CLS = {"WindowsCaptionButton", "Frame", "TabStripRegionView"}

    events: list[ChromeUIEvent] = []
    seen_markers: set[str] = set()
    for el in elements:
        if el["cls"] in BLOCKLIST_CLS:
            continue
        name_lower = el["name"].lower()
        for marker, kws, action, btn in CHROME_UI_RULES:
            if marker in seen_markers:
                continue
            for kw in kws:
                if kw.lower() in name_lower:
                    events.append(
                        ChromeUIEvent(
                            ts_ms=now_ms,
                            marker=marker,
                            snippet=el["name"][:200],
                            target_window=win_title,
                            button_name=btn,
                        )
                    )
                    seen_markers.add(marker)
                    break
    return events


# ── 액션 (버튼 클릭) ────────────────────────────────────────────────


def click_button_in_window(window: uia.Control, name: str) -> bool:
    """윈도우 안에서 정확한 이름의 버튼을 찾아 클릭."""
    elements = scan_chrome_ui(window, max_nodes=800)
    name_lower = name.lower()
    # 정확 매칭 우선
    for el in elements:
        if el["type"] == "ButtonControl" and el["name"].strip().lower() == name_lower:
            try:
                el["_ctrl"].Click(simulateMove=False)
                return True
            except Exception as e:  # noqa: BLE001 - 정확매칭 버튼 클릭 실패는 부분매칭 fallback으로 계속 시도(자동클릭은 "안전한" 대상만 대상이라 재시도가 강행이 아님)
                _log.warning("[chrome_ui_watcher] 클릭 실패: %s", e)
    # 부분 매칭 fallback
    for el in elements:
        if el["type"] == "ButtonControl" and name_lower in el["name"].lower():
            try:
                el["_ctrl"].Click(simulateMove=False)
                return True
            except Exception:  # noqa: BLE001 - 부분매칭 버튼도 클릭 실패하면 다음 후보로 계속(전부 실패하면 False 반환 — 호출부가 notified로 폴백)
                continue
    return False


def scan_all() -> list[tuple[uia.Control, list[ChromeUIEvent]]]:
    """모든 데몬 Chrome 윈도우 스캔."""
    out = []
    for w in find_chrome_windows():
        try:
            events = detect_alerts(w)
            out.append((w, events))
        except Exception as e:  # noqa: BLE001 - 창 하나 스캔 실패로 전체 감시 루프를 죽이지 않는다 — 그 창만 건너뛰고 나머지 창 계속(읽기전용 감시)
            _log.debug("[chrome_ui_watcher] 윈도우 스캔 오류 무시: %s", e)
    return out
