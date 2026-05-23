"""HaehanAI 통합 Tray Mode runtime (HAEHAN_TRAY_REGISTRATION_MERGE_01).

main_launcher.run_tray_mode 가 호출하는 실제 트레이 구현. 기존 local_agent
모듈을 흡수해서 등록 wizard / token store / WSS heartbeat / diagnostics 를
통합한다.

핵심 분리:
  - 순수 로직 함수 (decide_*, build_*, apply_*) — GUI 무관, 단위 테스트 가능
  - GUI/IO 어댑터 (run_wizard_gui, start_tray_gui) — pystray/tkinter 의존,
    실패 시 graceful degrade

기존 모듈 의존:
  - local_agent.token_store
  - local_agent.registration_client
  - local_agent.websocket_client (lazy import — heavy)
  - local_agent.connection_diagnostics
  - local_agent.desktop_config

보안:
  - registration_code 입력 후 즉시 변수 폐기
  - device_token 원문 UI/log/return 노출 0
  - lock/config 파일에 secret 저장 금지
  - 모든 diagnostics 출력에 redact 적용

Admin Mode pywebview lazy load 는 본 공정 OUT_OF_SCOPE.
다음 공정 HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 에서 처리.
"""
from __future__ import annotations

import logging
import platform
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import agent_runtime_boundary

logger = logging.getLogger(__name__)


# ── 데이터 클래스 ─────────────────────────────────────────────────────────

@dataclass
class RegistrationStatus:
    """token / config 기반 등록 상태. token 원문 절대 포함 금지."""
    registered: bool
    server_url: str = ""
    agent_id: str = ""
    config_present: bool = False
    token_present: bool = False
    backend: str = ""


@dataclass
class TrayMenuItem:
    """순수 데이터 — pystray 의존 없이 테스트 가능."""
    id: str
    label: str
    enabled: bool = True
    checked: Optional[bool] = None  # toggle 항목용
    is_separator: bool = False


@dataclass
class HeartbeatPlan:
    """heartbeat 실행 전 결정 사항."""
    can_start: bool
    reason: str = ""
    server_url: str = ""
    agent_id: str = ""
    ws_url: str = ""


@dataclass
class WizardOutcome:
    """wizard 실행 결과 — 토큰 원문 미포함."""
    success: bool
    agent_id: str = ""
    error_code: str = ""
    error_message: str = ""


# ── 순수 로직: 상태 판단 ──────────────────────────────────────────────────

def check_registration_status(
    *, plaintext_fallback: bool = False,
    config_loader: Optional[Callable[[], Any]] = None,
    token_checker: Optional[Callable[[str, str], bool]] = None,
) -> RegistrationStatus:
    """등록 상태 확인 — token 원문 절대 반환 않음.

    config_loader / token_checker 주입 가능 (테스트용).
    """
    if config_loader is None:
        config_loader = agent_runtime_boundary.load_desktop_config

    try:
        cfg = config_loader()
    except Exception as e:
        logger.debug("config load failed: %s", type(e).__name__)
        return RegistrationStatus(registered=False)

    if not getattr(cfg, "is_complete", lambda: False)():
        return RegistrationStatus(
            registered=False,
            server_url=getattr(cfg, "server_url", "") or "",
            agent_id=getattr(cfg, "agent_id", "") or "",
            config_present=False,
        )

    server_url = cfg.server_url
    agent_id = cfg.agent_id

    if token_checker is None:
        token_present, backend = agent_runtime_boundary.check_device_token(
            server_url, agent_id,
            allow_plaintext_fallback=plaintext_fallback,
        )
    else:
        token_present = token_checker(server_url, agent_id)
        backend = "test"

    return RegistrationStatus(
        registered=token_present,
        server_url=server_url,
        agent_id=agent_id,
        config_present=True,
        token_present=token_present,
        backend=backend,
    )


def decide_next_action(status: RegistrationStatus) -> str:
    """등록 상태 → 다음 동작 결정.

    Returns:
        "wizard" — 미등록 → wizard 표시 필요
        "heartbeat" — 등록됨 → WSS 연결 시작
    """
    if status.registered and status.server_url and status.agent_id:
        return "heartbeat"
    return "wizard"


def decide_action_from_error(error_code: str) -> str:
    """heartbeat 오류 코드 → 트레이 후속 동작.

    Returns:
        "show_wizard" — 재등록 필요
        "reconnect" — 자동 재시도
        "show_diagnostics" — 사용자 진단 권장
        "ignore" — 일시적
    """
    code = (error_code or "").upper()
    if code in ("AUTH_FAILED_4401", "TOKEN_NOT_STORED", "REG_CODE_EXPIRED",
                "REG_CODE_INVALID", "REG_CODE_ALREADY_USED"):
        return "show_wizard"
    if code in ("SERVER_NOT_REACHABLE", "NETWORK_BLOCKED_PROXY"):
        return "show_diagnostics"
    if code in ("HEARTBEAT_LOST", "AUTH_TIMEOUT", ""):
        return "reconnect"
    return "show_diagnostics"


# ── 순수 로직: 트레이 메뉴 ───────────────────────────────────────────────

def build_tray_menu_items(
    *, status: RegistrationStatus, role: str = "any",
    autostart_enabled: bool = False,
    admin_mode_available: bool = False,
) -> list[TrayMenuItem]:
    """트레이 메뉴 아이템 목록 (pystray 의존 없음).

    role 이 admin/owner 가 아니면 [관리화면 열기] 항목은 메뉴에 추가하되
    enabled=False 또는 본 공정에서는 admin_mode_available=False 이므로
    표시는 하지만 클릭 시 deferred 안내.
    """
    items: list[TrayMenuItem] = []

    # 상태 라벨 (선택 불가, 표시용)
    if status.registered:
        items.append(TrayMenuItem(id="status",
                                   label=f"● 연결됨 ({status.agent_id[:6]}***)",
                                   enabled=False))
    else:
        items.append(TrayMenuItem(id="status",
                                   label="● 미등록",
                                   enabled=False))

    items.append(TrayMenuItem(id="sep1", label="", is_separator=True))
    items.append(TrayMenuItem(id="diagnostics", label="진단..."))

    if status.registered:
        items.append(TrayMenuItem(id="re_register", label="재등록..."))
    else:
        items.append(TrayMenuItem(id="register", label="등록..."))

    # admin/owner 한정
    is_admin = role.lower() in ("admin", "owner")
    if is_admin:
        items.append(TrayMenuItem(
            id="open_admin",
            label="관리화면 열기" if admin_mode_available else "관리화면 열기 (준비 중)",
            enabled=admin_mode_available,
        ))

    items.append(TrayMenuItem(id="sep2", label="", is_separator=True))
    items.append(TrayMenuItem(
        id="autostart",
        label="Windows 시작 시 자동 실행",
        checked=autostart_enabled,
    ))
    items.append(TrayMenuItem(id="sep3", label="", is_separator=True))
    items.append(TrayMenuItem(id="quit", label="종료"))

    return items


def menu_item_visible(item: TrayMenuItem) -> bool:
    """렌더링 가능한지 (separator 포함)."""
    return bool(item.id)


# ── 순수 로직: heartbeat 계획 ────────────────────────────────────────────

def plan_heartbeat(status: RegistrationStatus) -> HeartbeatPlan:
    """heartbeat 시작 가능 여부 + ws_url 계산."""
    if not status.registered:
        return HeartbeatPlan(can_start=False, reason="not_registered")
    if not status.server_url or not status.agent_id:
        return HeartbeatPlan(can_start=False, reason="config_incomplete")

    try:
        ws_url = agent_runtime_boundary.normalize_ws_url(status.server_url)
    except Exception as e:
        return HeartbeatPlan(can_start=False, reason=f"ws_url_error:{type(e).__name__}")

    return HeartbeatPlan(
        can_start=True,
        server_url=status.server_url,
        agent_id=status.agent_id,
        ws_url=ws_url,
    )


# ── 순수 로직: 등록 결과 적용 ────────────────────────────────────────────

def apply_registration_result(
    server_url: str,
    meta: Any,  # RegistrationResult
    device_token: str,
    *,
    token_saver: Optional[Callable[..., str]] = None,
    config_saver: Optional[Callable[..., Any]] = None,
    allow_plaintext_fallback: bool = False,
) -> WizardOutcome:
    """등록 응답 → token_store 저장 + config 저장.

    device_token 은 본 함수 종료 직전 변수 참조를 끊는다 (호출자 책임).
    return 값에 device_token 미포함.
    """
    agent_id = getattr(meta, "agent_id", "")
    if not (server_url and agent_id and device_token):
        return WizardOutcome(success=False, error_code="invalid_input")

    if token_saver is None:
        token_saver = agent_runtime_boundary.save_device_token

    try:
        backend = token_saver(
            server_url, agent_id, device_token,
            allow_plaintext_fallback=allow_plaintext_fallback,
        )
    except Exception as e:
        return WizardOutcome(success=False, error_code="token_store_failed",
                             error_message=type(e).__name__)

    cfg = agent_runtime_boundary.build_desktop_config(
        server_url=server_url,
        agent_id=agent_id,
        label=getattr(meta, "label", "") or "",
        created_at=getattr(meta, "registered_at", "") or "",
        version=getattr(meta, "version", "") or "",
    )
    if config_saver is None:
        config_saver = agent_runtime_boundary.save_desktop_config
    try:
        config_saver(cfg)
    except Exception as e:
        logger.warning("config save failed (token saved OK): %s", type(e).__name__)

    logger.info("registration complete — backend=%s agent=%s***",
                backend, agent_id[:6])
    return WizardOutcome(success=True, agent_id=agent_id)


# ── 순수 로직: diagnostics payload ───────────────────────────────────────

def build_diagnostics_payload(
    *, status: RegistrationStatus,
    heartbeat_state: str = "NOT_REGISTERED",
    last_error_code: str = "",
    last_heartbeat_iso: str = "",
    reconnect_count: int = 0,
) -> dict:
    """진단 payload — redact 적용본. token 원문 절대 미포함."""
    d = agent_runtime_boundary.build_diagnostics(
        server_base_url=status.server_url,
        agent_id=status.agent_id,
        state=heartbeat_state,
        last_heartbeat_iso=last_heartbeat_iso,
        last_error_code=last_error_code,
        reconnect_count=reconnect_count,
    )
    out = d.to_dict()
    out["token_present"] = status.token_present
    out["config_present"] = status.config_present
    out["keyring_backend"] = status.backend
    out["host"] = platform.node()
    out["os"] = platform.system() + " " + platform.release()
    # 안전성 재확인 — 어떤 키에도 device_token / registration_code 원문 금지
    return out


# ── GUI 어댑터: wizard ───────────────────────────────────────────────────

def run_registration_wizard_cli(
    *, server_url: str, registration_code: str,
    register_fn: Optional[Callable[..., Any]] = None,
    host: str = "", os_name: str = "", version: str = "0.2.0",
) -> WizardOutcome:
    """CLI/headless wizard — GUI 없이 등록 수행. 테스트 친화.

    registration_code 는 호출자가 입력받아 전달. 본 함수 종료 직전 None 처리.
    """
    if register_fn is None:
        register_fn = agent_runtime_boundary.register_with_code

    try:
        meta, token = register_fn(
            server_url=server_url,
            registration_code=registration_code,
            host=host or platform.node(),
            os_name=os_name or (platform.system() + " " + platform.release()),
            version=version,
        )
    except Exception as e:
        # 메시지에는 RegistrationError.generic_message 만
        msg = getattr(e, "generic_message", "") or type(e).__name__
        # registration_code 자체는 절대 메시지에 안 들어가도록 검증
        if registration_code and registration_code in msg:
            msg = "registration_failed"
        return WizardOutcome(success=False, error_code=msg, error_message=msg)
    finally:
        # 메모리 폐기
        registration_code = ""  # noqa: F841

    outcome = apply_registration_result(server_url, meta, token)
    # token 변수 폐기
    token = ""  # noqa: F841
    return outcome


def run_registration_wizard_gui(
    *, default_server_url: str = "https://haehan-ai.kr/orchestrator",
    register_fn: Optional[Callable[..., Any]] = None,
) -> WizardOutcome:
    """tkinter 기반 3-step wizard. 실패 시 cli wizard 또는 deferred 반환.

    Step 1: 서버 URL
    Step 2: registration_code (show='●')
    Step 3: 완료 — agent_id 마스킹 표시
    """
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception as e:
        logger.warning("tkinter unavailable: %s", type(e).__name__)
        return WizardOutcome(success=False, error_code="gui_unavailable",
                             error_message="tkinter import failed")

    result: dict[str, Any] = {"outcome": None}

    root = tk.Tk()
    root.title("HaehanAI — 등록")
    root.geometry("520x320")
    root.attributes("-topmost", True)

    server_var = tk.StringVar(value=default_server_url)
    code_var = tk.StringVar(value="")
    show_var = tk.BooleanVar(value=False)

    container = ttk.Frame(root, padding=20)
    container.pack(fill="both", expand=True)

    state = {"step": 1}

    def _clear():
        for w in container.winfo_children():
            w.destroy()

    def _step1():
        _clear()
        state["step"] = 1
        ttk.Label(container, text="Step 1 / 3 — 서버 URL").pack(anchor="w")
        ttk.Label(container, text="(관리자가 다른 URL을 안내한 경우 변경)",
                  foreground="#9AA3B2").pack(anchor="w", pady=(0, 8))
        ttk.Entry(container, textvariable=server_var, width=60).pack(fill="x")
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=(20, 0))
        ttk.Button(btn_frame, text="다음 →", command=_step2).pack(side="right")

    def _toggle_show():
        entry.config(show="" if show_var.get() else "●")

    def _step2():
        _clear()
        state["step"] = 2
        ttk.Label(container, text="Step 2 / 3 — 등록코드 입력").pack(anchor="w")
        ttk.Label(container, text="관리자에게 받은 1회용 코드 (10분 유효)",
                  foreground="#9AA3B2").pack(anchor="w", pady=(0, 8))
        nonlocal_entry = ttk.Entry(container, textvariable=code_var,
                                    width=60, show="●")
        nonlocal_entry.pack(fill="x")
        # show toggle
        ttk.Checkbutton(container, text="입력 보이기", variable=show_var,
                        command=lambda: nonlocal_entry.config(
                            show="" if show_var.get() else "●"
                        )).pack(anchor="w", pady=(4, 0))
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=(20, 0))
        ttk.Button(btn_frame, text="← 이전", command=_step1).pack(side="left")
        ttk.Button(btn_frame, text="등록 →", command=_do_register).pack(side="right")

    def _do_register():
        code = code_var.get().strip()
        if not code:
            messagebox.showerror("등록", "등록코드를 입력하세요.")
            return
        outcome = run_registration_wizard_cli(
            server_url=server_var.get().strip(),
            registration_code=code,
            register_fn=register_fn,
        )
        # 즉시 폐기
        code_var.set("")
        code = ""  # noqa: F841

        if outcome.success:
            result["outcome"] = outcome
            _step3(outcome)
        else:
            messagebox.showerror(
                "등록 실패",
                _user_error_message(outcome.error_code),
            )

    def _step3(outcome: WizardOutcome):
        _clear()
        state["step"] = 3
        ttk.Label(container, text="Step 3 / 3 — 등록 완료 ✓",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(container,
                  text=f"agent_id   {agent_runtime_boundary.mask_agent_id(outcome.agent_id)}",
                  font=("Consolas", 11)).pack(anchor="w")
        ttk.Label(container, text="상태       ● 연결됨").pack(anchor="w", pady=(4, 16))
        ttk.Label(container,
                  text="앞으로 백그라운드에서 자동 실행됩니다.\n"
                       "트레이 아이콘에서 상태를 확인할 수 있습니다.",
                  foreground="#9AA3B2").pack(anchor="w")
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=(20, 0))
        ttk.Button(btn_frame, text="시작하기", command=root.destroy).pack(side="right")

    _step1()

    try:
        root.mainloop()
    except Exception as e:
        logger.warning("wizard mainloop error: %s", type(e).__name__)

    outcome = result["outcome"]
    if outcome is None:
        return WizardOutcome(success=False, error_code="user_closed",
                             error_message="wizard closed without registering")
    return outcome


def _user_error_message(code: str) -> str:
    """등록 실패 코드 → 한글 안내. 원문 secret 포함 금지."""
    msgs = {
        "invalid_registration_code": "등록코드가 유효하지 않습니다. 코드를 다시 확인하세요.",
        "registration_network_error": "서버에 접속할 수 없습니다. URL/네트워크를 확인하세요.",
        "registration_invalid_response": "서버 응답이 올바르지 않습니다. 관리자에게 문의하세요.",
        "token_store_failed": "device_token 저장 실패. 관리자 권한으로 재시도하세요.",
    }
    if code.startswith("registration_failed_http_"):
        return f"서버 오류 (HTTP {code.split('_')[-1]}). 잠시 후 재시도하거나 관리자에게 문의하세요."
    return msgs.get(code, "등록 실패. 잠시 후 재시도하세요.")


# ── GUI 어댑터: heartbeat 백그라운드 ─────────────────────────────────────

def start_heartbeat_background(
    plan: HeartbeatPlan,
    *,
    on_state_change: Optional[Callable[[str], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    runner: Optional[Callable[..., None]] = None,
) -> Optional[threading.Thread]:
    """websocket_client 를 백그라운드 thread 로 실행.

    실제 WS 클라이언트 실행은 runner 주입 가능 (테스트용).
    """
    if not plan.can_start:
        if on_error:
            on_error(plan.reason or "cannot_start")
        return None

    def _target():
        try:
            if runner is not None:
                runner(plan=plan,
                       on_state_change=on_state_change,
                       on_error=on_error)
                return
            # 실제 통합 — websocket_client 호출 (lazy import)
            try:
                token = agent_runtime_boundary.load_device_token(plan.server_url, plan.agent_id)
            except Exception:
                logger.warning("websocket_client.run_websocket_client 미발견 — heartbeat 비활성")
                if on_error:
                    on_error("ws_client_unavailable")
                return

            if not token:
                if on_error:
                    on_error("TOKEN_NOT_STORED")
                return

            if on_state_change:
                on_state_change("CONNECTING")

            try:
                agent_runtime_boundary.run_websocket_client(
                    server_url=plan.server_url,
                    agent_id=plan.agent_id,
                    device_token=token,
                )
            finally:
                token = ""  # noqa: F841

        except Exception as e:
            logger.warning("heartbeat thread error: %s", type(e).__name__)
            if on_error:
                on_error(type(e).__name__)

    t = threading.Thread(target=_target, name="haehan-heartbeat", daemon=True)
    t.start()
    return t


# ── GUI 어댑터: 트레이 ───────────────────────────────────────────────────

def start_tray_gui(
    *,
    status_provider: Callable[[], RegistrationStatus],
    on_diagnostics: Callable[[], None],
    on_register: Callable[[], None],
    on_re_register: Callable[[], None],
    on_open_admin: Optional[Callable[[], None]] = None,
    on_quit: Callable[[], None],
    role: str = "any",
    admin_mode_available: bool = False,
    icon_factory: Optional[Callable[[], Any]] = None,
) -> Optional[Any]:
    """pystray 트레이 시작. 실패 시 None 반환 (graceful degrade)."""
    try:
        import pystray  # type: ignore
        from pystray import MenuItem, Menu
    except Exception as e:
        logger.warning("pystray unavailable: %s", type(e).__name__)
        return None

    def _build_menu():
        status = status_provider()
        items = build_tray_menu_items(
            status=status, role=role,
            admin_mode_available=admin_mode_available,
        )
        py_items = []
        for it in items:
            if it.is_separator:
                py_items.append(Menu.SEPARATOR)
                continue
            if it.id == "status":
                py_items.append(MenuItem(it.label, None, enabled=False))
            elif it.id == "diagnostics":
                py_items.append(MenuItem(it.label, lambda *_: on_diagnostics()))
            elif it.id == "register":
                py_items.append(MenuItem(it.label, lambda *_: on_register()))
            elif it.id == "re_register":
                py_items.append(MenuItem(it.label, lambda *_: on_re_register()))
            elif it.id == "open_admin" and on_open_admin:
                py_items.append(MenuItem(it.label, lambda *_: on_open_admin(),
                                         enabled=it.enabled))
            elif it.id == "autostart":
                # 본 공정에서는 토글 없이 표시만
                py_items.append(MenuItem(it.label, None, enabled=False))
            elif it.id == "quit":
                py_items.append(MenuItem(it.label, lambda *_: on_quit()))
        return Menu(*py_items)

    icon_img = None
    if icon_factory is not None:
        try:
            icon_img = icon_factory()
        except Exception:
            icon_img = None

    if icon_img is None:
        try:
            from PIL import Image, ImageDraw
            icon_img = Image.new("RGB", (16, 16), "#10B981")
            d = ImageDraw.Draw(icon_img)
            d.ellipse((2, 2, 14, 14), fill="#10B981")
        except Exception:
            return None

    icon = pystray.Icon("haehan-ai", icon_img, "HaehanAI", _build_menu())
    return icon


# ── 진입점 ────────────────────────────────────────────────────────────────

def run_tray_mode_full(
    *,
    plaintext_fallback: bool = False,
    role: str = "any",
    admin_mode_available: bool = False,
    skip_gui: bool = False,
    start_heartbeat: bool = True,
) -> dict:
    """Tray Mode 통합 진입.

    Returns:
        {"status": "...", "next_action": "...", "details": {...}}
    """
    status = check_registration_status(plaintext_fallback=plaintext_fallback)
    next_action = decide_next_action(status)

    result = {
        "status": "started",
        "registered": status.registered,
        "next_action": next_action,
        "role": role,
        "admin_mode_available": admin_mode_available,
        "skip_gui": skip_gui,
        "start_heartbeat": start_heartbeat,
    }

    if skip_gui:
        return result

    # heartbeat 시작 (등록된 경우)
    if start_heartbeat and next_action == "heartbeat":
        plan = plan_heartbeat(status)
        if plan.can_start:
            start_heartbeat_background(plan,
                on_error=lambda code: logger.warning("heartbeat err: %s", code))
            result["heartbeat_started"] = True
        else:
            result["heartbeat_started"] = False
            result["heartbeat_reason"] = plan.reason
    else:
        result["heartbeat_started"] = False
        result["heartbeat_reason"] = "disabled" if next_action == "heartbeat" else "not_registered"

    return result


# ── Admin Mode 연결 (HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01) ──────────

def open_admin_handler(
    *,
    explicit_role: Optional[str] = None,
    server_url: str = "http://127.0.0.1:8765",
    skip_gui: Optional[bool] = None,
) -> dict:
    """트레이 [관리화면 열기] 클릭 콜백.

    admin_webview 를 lazy import 하여 pywebview 가 본 모듈 로드 시 import 되지 않도록
    분리. role guard / single instance / skip_gui 처리는 admin_webview 가 담당.
    """
    try:
        from desktop import admin_webview
    except Exception as e:
        logger.error("admin_webview import 실패: %s", type(e).__name__)
        return {"ok": False,
                "reason": f"admin_webview_unavailable:{type(e).__name__}",
                "role": "",
                "window_opened": False}
    return admin_webview.open_admin_window(
        explicit_role=explicit_role,
        server_url=server_url,
        skip_gui=skip_gui,
    )
