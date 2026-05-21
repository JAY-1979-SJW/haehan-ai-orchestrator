"""사용자 GUI — VS Code/JetBrains 스타일 사이드바 + 4탭.

탭:
  Dashboard (Ctrl+1) — 상태 카드 + heartbeat sparkline + Quick actions
  Registration (Ctrl+2) — 서버 URL + 등록코드 + Register
  Logs (Ctrl+3) — 1000 라인 ring buffer + 필터 + export (redact)
  Settings (Ctrl+4) — 서버 URL / 외관 / 토큰 저장소 / 정보

상태 source:
  gui_state.GuiController (단일) — 모든 표시 위치 동일 source

스레드:
  메인 = tkinter mainloop
  백그라운드 = register / WS 연결 / heartbeat 폴링
"""
from __future__ import annotations

import logging
import os
import platform
import random
import socket
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox

from . import connection_diagnostics as cd
from . import gui_icons as icons
from . import gui_log_buffer as lb
from . import gui_state as gs
from . import registration_client as rcli
from . import token_store as ts

logger = logging.getLogger("haehan_gui")


def _try_ctk():
    try:
        import customtkinter as ctk  # type: ignore
        return ctk
    except Exception:
        return None


_ctk = _try_ctk()
_HAS_CTK = _ctk is not None


# ── 디자인 토큰 ────────────────────────────────────────────────────

COLOR = {
    "bg_canvas":    "#0B0D11",
    "bg_panel":     "#11141A",
    "bg_surface":   "#161A22",
    "bg_card":      "#1C2129",
    "bg_card_hov":  "#222936",
    "bg_elevated":  "#252B36",
    "border_sub":   "#22272F",
    "border_def":   "#2D333D",
    "border_focus": "#6366F1",
    "fg":           "#E6E9EF",
    "fg_muted":     "#9AA3B2",
    "fg_subtle":    "#6B7484",
    "fg_faint":     "#4A5160",
    "accent":       "#6366F1",
    "accent_hi":    "#818CF8",
    "accent_lo":    "#4F46E5",
    "success":      "#10B981",
    "success_bg":   "#0E2B1F",
    "warning":      "#F59E0B",
    "warning_bg":   "#2B1F0A",
    "danger":       "#EF4444",
    "danger_bg":    "#2B1212",
    "info":         "#3B82F6",
}


def _state_color(s: str) -> str:
    if s in (gs.STATE_HEARTBEAT_OK, gs.STATE_CONNECTED):
        return COLOR["success"]
    if s in (gs.STATE_AUTH_FAILED, gs.STATE_SERVER_UNREACHABLE):
        return COLOR["danger"]
    if s in (gs.STATE_CONNECTING, gs.STATE_AUTHENTICATING,
              gs.STATE_RECONNECTING):
        return COLOR["warning"]
    return COLOR["fg_subtle"]


def _state_bg(s: str) -> str:
    if s in (gs.STATE_HEARTBEAT_OK, gs.STATE_CONNECTED):
        return COLOR["success_bg"]
    if s in (gs.STATE_AUTH_FAILED, gs.STATE_SERVER_UNREACHABLE):
        return COLOR["danger_bg"]
    if s in (gs.STATE_CONNECTING, gs.STATE_AUTHENTICATING,
              gs.STATE_RECONNECTING):
        return COLOR["warning_bg"]
    return COLOR["bg_card"]


def _state_label(s: str) -> str:
    return {
        gs.STATE_NOT_REGISTERED: "미등록",
        gs.STATE_CONNECTING: "연결 중",
        gs.STATE_AUTHENTICATING: "인증 중",
        gs.STATE_CONNECTED: "연결됨",
        gs.STATE_HEARTBEAT_OK: "정상",
        gs.STATE_DISCONNECTED: "끊김",
        gs.STATE_AUTH_FAILED: "인증 실패 — 재등록 필요",
        gs.STATE_RECONNECTING: "재연결 중",
        gs.STATE_SERVER_UNREACHABLE: "서버 접속 실패",
    }.get(s, s)


# ── 페이지 enum ────────────────────────────────────────────────────

PAGE_DASHBOARD = "dashboard"
PAGE_REGISTRATION = "registration"
PAGE_LOGS = "logs"
PAGE_SETTINGS = "settings"
ALL_PAGES = (PAGE_DASHBOARD, PAGE_REGISTRATION, PAGE_LOGS, PAGE_SETTINGS)


# ── 메인 앱 ────────────────────────────────────────────────────────


class HaehanAgentGuiApp:
    """VS Code 스타일 사이드바 + 4탭 GUI."""

    def __init__(self, *, controller: gs.GuiController,
                 log_buffer: lb.LogBuffer | None = None):
        self.ctrl = controller
        self.log = log_buffer or lb.LogBuffer()
        self.current_page = PAGE_DASHBOARD
        self._ws_thread: threading.Thread | None = None
        self._heartbeat_history: deque[float] = deque(maxlen=60)
        self._spinner_angle = 0
        self._pulse_state = 0

        if _HAS_CTK:
            _ctk.set_appearance_mode("dark")
            _ctk.set_default_color_theme("blue")
            self.root = _ctk.CTk()
        else:
            self.root = tk.Tk()
            self.root.configure(bg=COLOR["bg_canvas"])
        self.root.title("Haehan AI · Local Agent")
        self.root.geometry("820x620")
        self.root.minsize(720, 560)

        # 페이지 컨테이너 dict
        self._page_widgets: dict[str, object] = {}
        self._sidebar_buttons: dict[str, object] = {}

        self._build_layout()
        self._bind_shortcuts()
        self._poll_model()
        self._tick_motion()

        self.log.info("GUI 시작")

    # ── 레이아웃 ───────────────────────────────────────────────

    # 회귀 가드 — 구버전 API 호환 alias
    def _build_ui(self) -> None:
        """Deprecated: 구버전 호출 호환용 alias. 신규는 _build_layout 사용."""
        return self._build_layout()

    def _build_layout(self) -> None:
        ctk = _ctk
        if not _HAS_CTK:
            self._build_fallback()
            return

        # Sidebar
        self.sidebar = ctk.CTkFrame(self.root, width=72, corner_radius=0,
                                      fg_color=COLOR["bg_panel"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # 사이드바 — 상단 로고 자리
        logo = ctk.CTkLabel(self.sidebar, text="▣",
                              font=("Segoe UI", 22, "bold"),
                              text_color=COLOR["accent_hi"])
        logo.pack(pady=(16, 24))

        for key, label in (
            (PAGE_DASHBOARD, "대시보드"),
            (PAGE_REGISTRATION, "등록"),
            (PAGE_LOGS, "로그"),
            (PAGE_SETTINGS, "설정"),
        ):
            self._make_sidebar_button(key, label)

        # 상태 바 (하단)
        self.statusbar = ctk.CTkFrame(self.root, height=28, corner_radius=0,
                                        fg_color=COLOR["bg_panel"])
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.pack_propagate(False)
        self.var_status = tk.StringVar(value="●  미등록")
        self.lbl_status = ctk.CTkLabel(
            self.statusbar, textvariable=self.var_status,
            text_color=COLOR["fg_subtle"], font=("Segoe UI", 11),
        )
        self.lbl_status.pack(side="left", padx=14)
        ctk.CTkLabel(self.statusbar, text="v0.1.0 · unsigned",
                      text_color=COLOR["fg_faint"],
                      font=("Segoe UI", 10)).pack(side="right", padx=14)

        # 메인 영역
        self.main = ctk.CTkFrame(self.root, corner_radius=0,
                                   fg_color=COLOR["bg_surface"])
        self.main.pack(side="right", fill="both", expand=True)

        # 페이지들 생성 (모두 만들고 pack/forget 로 전환)
        self._page_dashboard = self._build_page_dashboard(self.main)
        self._page_registration = self._build_page_registration(self.main)
        self._page_logs = self._build_page_logs(self.main)
        self._page_settings = self._build_page_settings(self.main)
        self._page_widgets = {
            PAGE_DASHBOARD: self._page_dashboard,
            PAGE_REGISTRATION: self._page_registration,
            PAGE_LOGS: self._page_logs,
            PAGE_SETTINGS: self._page_settings,
        }
        self.show_page(PAGE_DASHBOARD)

    def _build_fallback(self) -> None:
        """ctk 미설치 시 ttk 기본."""
        from tkinter import ttk
        self.var_status = tk.StringVar(value="●  미등록")
        ttk.Label(self.root, textvariable=self.var_status).pack(pady=20)
        ttk.Label(self.root,
                   text="customtkinter 미설치 — pip install customtkinter",
                   foreground="#888").pack()
        # 기본 버튼만
        for key, cb in (("등록", self.on_register),
                         ("진단", self.on_diagnostics),
                         ("종료", self.on_quit)):
            ttk.Button(self.root, text=key, command=cb).pack(pady=4)
        # vars needed by tests / shortcuts
        self.var_server = tk.StringVar(value=self.ctrl.model.server_url)
        self.var_code = tk.StringVar(value="")

    def _make_sidebar_button(self, key: str, label: str) -> None:
        ctk = _ctk
        frame = ctk.CTkFrame(self.sidebar, fg_color="transparent",
                              corner_radius=8, height=52, width=60)
        frame.pack(pady=2, padx=6)
        frame.pack_propagate(False)
        # 활성 표시 좌측 막대
        bar = ctk.CTkFrame(frame, width=3, height=32,
                            fg_color="transparent")
        bar.place(x=0, y=10)
        # 아이콘
        glyph = icons.SIDEBAR_ICONS.get(key, "?")
        btn = ctk.CTkButton(
            frame, text=glyph, width=54, height=52, corner_radius=8,
            fg_color="transparent", hover_color=COLOR["bg_card_hov"],
            text_color=COLOR["fg_subtle"], font=("Segoe UI", 18),
            command=lambda k=key: self.show_page(k),
        )
        btn.place(x=6, y=0)
        # 작은 라벨
        ctk.CTkLabel(frame, text=label,
                      text_color=COLOR["fg_faint"],
                      font=("Segoe UI", 8)).place(x=12, y=40)
        self._sidebar_buttons[key] = (btn, bar)

    def show_page(self, page: str) -> None:
        if page not in ALL_PAGES:
            return
        # 기존 페이지 숨기기
        for k, w in self._page_widgets.items():
            try:
                w.pack_forget()
            except Exception:
                pass
        # 새 페이지 표시
        try:
            self._page_widgets[page].pack(fill="both", expand=True,
                                            padx=24, pady=20)
        except Exception:
            pass
        self.current_page = page
        # 사이드바 활성 표시
        for k, (btn, bar) in self._sidebar_buttons.items():
            active = (k == page)
            try:
                btn.configure(text_color=COLOR["fg"] if active
                               else COLOR["fg_subtle"])
                bar.configure(fg_color=COLOR["accent"] if active
                               else "transparent")
            except Exception:
                pass
        self.log.info(f"페이지 전환: {page}")

    # ── 페이지: Dashboard ──────────────────────────────────────

    def _build_page_dashboard(self, parent):
        ctk = _ctk
        frame = ctk.CTkFrame(parent, fg_color=COLOR["bg_surface"],
                              corner_radius=0)
        # 제목
        ctk.CTkLabel(frame, text="Dashboard",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ctk.CTkLabel(frame, text="현재 연결 상태와 최근 heartbeat",
                      text_color=COLOR["fg_subtle"],
                      font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 16))

        # 큰 상태 카드
        self.dash_state_card = ctk.CTkFrame(
            frame, fg_color=COLOR["bg_card"],
            border_color=COLOR["border_sub"], border_width=1,
            corner_radius=12, height=130,
        )
        self.dash_state_card.pack(fill="x", pady=(0, 16))
        self.dash_state_card.pack_propagate(False)

        self.var_dash_state_pill = tk.StringVar(value="●  미등록")
        self.dash_state_pill = ctk.CTkLabel(
            self.dash_state_card, textvariable=self.var_dash_state_pill,
            text_color=COLOR["fg_subtle"],
            font=("Segoe UI", 17, "bold"),
        )
        self.dash_state_pill.place(x=20, y=16)

        # 부정보
        self.var_dash_aid = tk.StringVar(value="agent_id        —")
        self.var_dash_hb = tk.StringVar(value="last heartbeat  —")
        self.var_dash_rc = tk.StringVar(value="reconnect       0")
        for i, var in enumerate((self.var_dash_aid, self.var_dash_hb,
                                  self.var_dash_rc)):
            ctk.CTkLabel(self.dash_state_card, textvariable=var,
                          text_color=COLOR["fg_muted"],
                          font=("Consolas", 11)).place(x=20, y=56 + i * 22)

        # heartbeat / network row
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 16))
        # Heartbeat 카드
        hb_card = ctk.CTkFrame(row, fg_color=COLOR["bg_card"],
                                 border_color=COLOR["border_sub"],
                                 border_width=1, corner_radius=12,
                                 height=110)
        hb_card.pack(side="left", fill="x", expand=True, padx=(0, 8))
        hb_card.pack_propagate(False)
        ctk.CTkLabel(hb_card, text="Heartbeat",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=14, y=10)
        self.dash_sparkline_label = ctk.CTkLabel(hb_card, text="",
                                                   fg_color="transparent")
        self.dash_sparkline_label.place(x=14, y=34)
        self.var_dash_hb_meta = tk.StringVar(value="대기 중")
        ctk.CTkLabel(hb_card, textvariable=self.var_dash_hb_meta,
                      text_color=COLOR["fg_subtle"],
                      font=("Segoe UI", 10)).place(x=14, y=82)

        # Network 카드
        net = ctk.CTkFrame(row, fg_color=COLOR["bg_card"],
                            border_color=COLOR["border_sub"],
                            border_width=1, corner_radius=12, height=110)
        net.pack(side="left", fill="x", expand=True, padx=(8, 0))
        net.pack_propagate(False)
        ctk.CTkLabel(net, text="Network",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=14, y=10)
        self.var_dash_uptime = tk.StringVar(value="uptime  00:00:00")
        ctk.CTkLabel(net, textvariable=self.var_dash_uptime,
                      text_color=COLOR["fg_muted"],
                      font=("Consolas", 11)).place(x=14, y=40)
        self.var_dash_server = tk.StringVar(value=self.ctrl.model.server_url)
        ctk.CTkLabel(net, textvariable=self.var_dash_server,
                      text_color=COLOR["fg_subtle"],
                      font=("Consolas", 10)).place(x=14, y=64)

        # Quick actions
        ctk.CTkLabel(frame, text="Quick actions",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).pack(anchor="w",
                                                            pady=(0, 8))
        qa = ctk.CTkFrame(frame, fg_color="transparent")
        qa.pack(anchor="w")
        ctk.CTkButton(qa, text="재연결", command=self.on_connect,
                       width=110, height=34, corner_radius=8,
                       fg_color=COLOR["success"], hover_color="#0EA372",
                       font=("Segoe UI", 11, "bold"),
                       ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(qa, text="진단 보기", command=self.on_diagnostics,
                       width=110, height=34, corner_radius=8,
                       fg_color=COLOR["bg_card"],
                       hover_color=COLOR["bg_card_hov"],
                       text_color=COLOR["fg"],
                       border_color=COLOR["border_def"], border_width=1,
                       font=("Segoe UI", 11),
                       ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(qa, text="등록 화면", command=lambda: self.show_page(PAGE_REGISTRATION),
                       width=110, height=34, corner_radius=8,
                       fg_color="transparent",
                       hover_color=COLOR["bg_card_hov"],
                       text_color=COLOR["fg_muted"],
                       border_color=COLOR["border_def"], border_width=1,
                       font=("Segoe UI", 11),
                       ).pack(side="left")

        return frame

    # ── 페이지: Registration ───────────────────────────────────

    def _build_page_registration(self, parent):
        ctk = _ctk
        frame = ctk.CTkFrame(parent, fg_color=COLOR["bg_surface"])
        ctk.CTkLabel(frame, text="Registration",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ctk.CTkLabel(frame,
                      text="관리자에게 발급받은 1회용 등록코드로 시작합니다",
                      text_color=COLOR["fg_subtle"],
                      font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 16))

        card = ctk.CTkFrame(frame, fg_color=COLOR["bg_card"],
                              border_color=COLOR["border_sub"],
                              border_width=1, corner_radius=12)
        card.pack(fill="both", expand=True)

        # Server
        ctk.CTkLabel(card, text="Server",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=18, y=14)
        ctk.CTkLabel(card, text="서버 URL",
                      text_color=COLOR["fg_muted"],
                      font=("Segoe UI", 10)).place(x=18, y=42)
        self.var_server = tk.StringVar(value=self.ctrl.model.server_url)
        ctk.CTkEntry(card, textvariable=self.var_server,
                      width=420, height=34, corner_radius=6,
                      fg_color=COLOR["bg_card_hov"],
                      border_color=COLOR["border_def"],
                      text_color=COLOR["fg"]).place(x=18, y=62)
        ctk.CTkLabel(card,
                      text="WebSocket: wss://.../api/v1/local-agents/ws",
                      text_color=COLOR["fg_faint"],
                      font=("Segoe UI", 9)).place(x=18, y=100)

        # Registration code
        ctk.CTkLabel(card, text="Registration code",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=18, y=130)
        ctk.CTkLabel(card,
                      text="1회용 · 10분 유효 · 관리자에게 받은 코드",
                      text_color=COLOR["fg_muted"],
                      font=("Segoe UI", 10)).place(x=18, y=156)
        self.var_code = tk.StringVar(value="")
        self.ent_code = ctk.CTkEntry(
            card, textvariable=self.var_code,
            width=420, height=34, show="●", corner_radius=6,
            fg_color=COLOR["bg_card_hov"],
            border_color=COLOR["border_def"],
            text_color=COLOR["fg"],
            placeholder_text="등록코드 붙여넣기",
        )
        self.ent_code.place(x=18, y=176)

        self.var_show_code = tk.IntVar(value=0)
        ctk.CTkCheckBox(
            card, text="입력 보이기", variable=self.var_show_code,
            command=self._toggle_code_visibility,
            text_color=COLOR["fg_muted"],
            font=("Segoe UI", 10),
            fg_color=COLOR["accent"], hover_color=COLOR["accent_hi"],
            checkbox_width=18, checkbox_height=18, corner_radius=4,
        ).place(x=18, y=214)

        # Device info
        ctk.CTkLabel(card, text="Device info",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=18, y=246)
        host = socket.gethostname() or "unknown"
        os_name = f"{platform.system()} {platform.release()}"
        ctk.CTkLabel(card,
                      text=f"host       {host}",
                      text_color=COLOR["fg_muted"],
                      font=("Consolas", 10)).place(x=18, y=272)
        ctk.CTkLabel(card,
                      text=f"os         {os_name}",
                      text_color=COLOR["fg_muted"],
                      font=("Consolas", 10)).place(x=18, y=292)
        ctk.CTkLabel(card,
                      text="version    0.1.0",
                      text_color=COLOR["fg_muted"],
                      font=("Consolas", 10)).place(x=18, y=312)

        # Register button
        self.btn_register = ctk.CTkButton(
            card, text="Register  →", command=self.on_register,
            width=180, height=40, corner_radius=8,
            fg_color=COLOR["accent"], hover_color=COLOR["accent_hi"],
            font=("Segoe UI", 12, "bold"),
        )
        self.btn_register.place(x=18, y=352)

        self.var_reg_status = tk.StringVar(value="")
        self.lbl_reg_status = ctk.CTkLabel(
            card, textvariable=self.var_reg_status,
            text_color=COLOR["fg_muted"],
            font=("Segoe UI", 10), wraplength=480, justify="left",
        )
        self.lbl_reg_status.place(x=18, y=400)

        ctk.CTkLabel(
            card,
            text="• device_token · registration_code 원문은 화면·로그·보고서에 노출되지 않습니다.",
            text_color=COLOR["fg_faint"],
            font=("Segoe UI", 9),
        ).place(x=18, rely=1.0, y=-26)

        return frame

    def _toggle_code_visibility(self) -> None:
        try:
            self.ent_code.configure(
                show="" if self.var_show_code.get() else "●")
        except Exception:
            pass

    # ── 페이지: Logs ───────────────────────────────────────────

    def _build_page_logs(self, parent):
        ctk = _ctk
        frame = ctk.CTkFrame(parent, fg_color=COLOR["bg_surface"])
        ctk.CTkLabel(frame, text="Logs",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ctk.CTkLabel(frame,
                      text="자동 redact 적용 · 1,000 라인 버퍼",
                      text_color=COLOR["fg_subtle"],
                      font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 16))

        # filter / actions
        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 10))
        self.var_log_level = tk.StringVar(value="ALL")
        ctk.CTkLabel(bar, text="Level",
                      text_color=COLOR["fg_muted"],
                      font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        ctk.CTkOptionMenu(
            bar, variable=self.var_log_level,
            values=["ALL", "INFO", "WARN", "ERR"],
            width=90, height=28, corner_radius=6,
            fg_color=COLOR["bg_card"],
            button_color=COLOR["bg_card_hov"],
            button_hover_color=COLOR["border_def"],
            text_color=COLOR["fg"],
            command=lambda _v: self._refresh_logs(),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkButton(bar, text="Clear", command=self._clear_logs,
                       width=80, height=28, corner_radius=6,
                       fg_color=COLOR["bg_card"],
                       hover_color=COLOR["bg_card_hov"],
                       text_color=COLOR["fg_muted"],
                       border_color=COLOR["border_def"], border_width=1,
                       font=("Segoe UI", 10),
                       ).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Export", command=self._export_logs,
                       width=90, height=28, corner_radius=6,
                       fg_color=COLOR["bg_card"],
                       hover_color=COLOR["bg_card_hov"],
                       text_color=COLOR["fg_muted"],
                       border_color=COLOR["border_def"], border_width=1,
                       font=("Segoe UI", 10),
                       ).pack(side="left", padx=4)

        # log text area
        self.log_textbox = ctk.CTkTextbox(
            frame, wrap="word",
            fg_color=COLOR["bg_card"],
            text_color=COLOR["fg_muted"],
            border_color=COLOR["border_sub"], border_width=1,
            corner_radius=8, font=("Consolas", 10),
        )
        self.log_textbox.pack(fill="both", expand=True)

        self.log.subscribe(lambda e: self._on_log_event(e))
        self._refresh_logs()
        return frame

    def _refresh_logs(self) -> None:
        try:
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            entries = self.log.tail(200,
                                      level_filter=self.var_log_level.get())
            for e in entries:
                self.log_textbox.insert(
                    "end", f"{e.ts}  {e.level:<4}  {e.msg}\n")
            self.log_textbox.configure(state="disabled")
            self.log_textbox.see("end")
        except Exception:
            pass

    def _on_log_event(self, _entry) -> None:
        try:
            self.root.after(0, self._refresh_logs)
        except Exception:
            pass

    def _clear_logs(self) -> None:
        self.log.clear()
        self._refresh_logs()

    def _export_logs(self) -> None:
        try:
            p = filedialog.asksaveasfilename(
                defaultextension=".jsonl",
                filetypes=[("JSON Lines", "*.jsonl"), ("All", "*.*")],
                initialfile=f"haehan_agent_logs_{int(time.time())}.jsonl",
            )
            if not p:
                return
            result = self.log.export_jsonl(Path(p))
            self.log.info(f"로그 export 완료: {result['count']} lines")
            messagebox.showinfo("로그 export",
                                  f"{result['count']} 라인 저장됨")
        except Exception as exc:
            self.log.err(f"로그 export 실패: {type(exc).__name__}")
            messagebox.showerror("실패", str(exc)[:200])

    # ── 페이지: Settings ────────────────────────────────────────

    def _build_page_settings(self, parent):
        ctk = _ctk
        frame = ctk.CTkFrame(parent, fg_color=COLOR["bg_surface"])
        ctk.CTkLabel(frame, text="Settings",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ctk.CTkLabel(frame,
                      text="서버 · 외관 · 토큰 저장소 · 정보",
                      text_color=COLOR["fg_subtle"],
                      font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 16))

        card = ctk.CTkFrame(frame, fg_color=COLOR["bg_card"],
                              border_color=COLOR["border_sub"],
                              border_width=1, corner_radius=12)
        card.pack(fill="both", expand=True)

        # 서버
        ctk.CTkLabel(card, text="서버",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=18, y=14)
        self.var_settings_server = tk.StringVar(
            value=self.ctrl.model.server_url)
        ctk.CTkEntry(card, textvariable=self.var_settings_server,
                      width=440, height=32, corner_radius=6,
                      fg_color=COLOR["bg_card_hov"],
                      border_color=COLOR["border_def"],
                      text_color=COLOR["fg"]).place(x=18, y=42)
        ctk.CTkButton(card, text="저장",
                       command=self._save_server_url,
                       width=80, height=32, corner_radius=6,
                       fg_color=COLOR["accent"],
                       hover_color=COLOR["accent_hi"],
                       font=("Segoe UI", 10, "bold")).place(x=470, y=42)

        # 토큰 저장소
        ctk.CTkLabel(card, text="토큰 저장소",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=18, y=92)
        available, name = ts.describe_backend()
        ctk.CTkLabel(card,
                      text=f"backend     {name} ({'available' if available else 'unavailable'})",
                      text_color=COLOR["fg_muted"],
                      font=("Consolas", 11)).place(x=18, y=118)
        ctk.CTkButton(card, text="토큰 삭제 — 재등록 필요",
                       command=self.on_reset,
                       width=200, height=32, corner_radius=6,
                       fg_color="transparent",
                       hover_color=COLOR["danger_bg"],
                       text_color=COLOR["danger"],
                       border_color=COLOR["danger"], border_width=1,
                       font=("Segoe UI", 10),
                       ).place(x=18, y=146)

        # 정보
        ctk.CTkLabel(card, text="정보",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=18, y=200)
        info_text = (
            "version    0.1.0\n"
            "license    MIT\n"
            "서명       unsigned (코드 서명 OUT_OF_SCOPE)"
        )
        ctk.CTkLabel(card, text=info_text,
                      text_color=COLOR["fg_muted"],
                      font=("Consolas", 11),
                      justify="left").place(x=18, y=226)

        # 단축키
        ctk.CTkLabel(card, text="단축키",
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 12, "bold")).place(x=18, y=310)
        sk = ("Ctrl+1..4   페이지 전환\n"
              "Ctrl+R      재등록 (token 삭제 + 등록 화면)\n"
              "F1          진단 보기\n"
              "Esc         종료")
        ctk.CTkLabel(card, text=sk,
                      text_color=COLOR["fg_muted"],
                      font=("Consolas", 10),
                      justify="left").place(x=18, y=336)

        return frame

    def _save_server_url(self) -> None:
        url = (self.var_settings_server.get() or "").strip()
        if not url:
            return
        self.ctrl.set_server_url(url)
        try:
            self.var_server.set(url)
        except Exception:
            pass
        self.log.info(f"서버 URL 변경: {cd._strip_secrets_from_url(url)}")
        messagebox.showinfo("저장됨", "서버 URL 이 저장되었습니다.")

    # ── 이벤트 핸들러 ──────────────────────────────────────────

    def on_register(self) -> None:
        server = (self.var_server.get() or "").strip()
        code = (self.var_code.get() or "").strip()
        if not code:
            messagebox.showwarning("등록코드 필요", "등록코드를 입력하세요.")
            return
        self.ctrl.set_server_url(server)
        try:
            self.btn_register.configure(state="disabled", text="등록 중…")
        except Exception:
            pass
        threading.Thread(target=self._register_worker,
                          args=(server, code), daemon=True).start()

    def _register_worker(self, server: str, code: str) -> None:
        try:
            self.ctrl.fire("register_started")
            self.log.info("register-with-code 요청")
            host = socket.gethostname() or "unknown-host"
            os_name = (platform.system() + " " + platform.release()) or "unknown-os"
            meta, device_token = rcli.register_with_code(
                server_url=server, registration_code=code,
                host=host, os_name=os_name, version="0.1.0",
            )
            agent_id = meta.agent_id
            ts.save_device_token(server_url=server, agent_id=agent_id,
                                  token=device_token)
            device_token = ""
            code = ""
            self.ctrl.set_agent_id(agent_id)
            self.ctrl.fire("register_success",
                            user_event=f"등록 성공 · {cd.mask_agent_id(agent_id)}")
            self.log.info(f"등록 성공: agent_id={cd.mask_agent_id(agent_id)}")
            self.root.after(0,
                             lambda: self.var_reg_status.set(
                                 f"✓ 등록 성공 · {cd.mask_agent_id(agent_id)}"))
            self.root.after(800, lambda: self.show_page(PAGE_DASHBOARD))
        except rcli.RegistrationError as exc:
            self.ctrl.fire("register_failed", error_code="REG_CODE_INVALID",
                            user_event="등록 실패")
            self.log.warn(f"등록 실패 (코드/서버): {type(exc).__name__}")
            self.root.after(0,
                             lambda: self.var_reg_status.set(
                                 "✗ 등록코드가 유효하지 않거나 서버 응답 오류"))
        except ts.TokenStoreError:
            self.ctrl.fire("register_failed", error_code="TOKEN_NOT_STORED")
            self.log.err("token 저장 실패")
            self.root.after(0,
                             lambda: self.var_reg_status.set(
                                 "✗ token 저장 실패"))
        except Exception as exc:
            self.ctrl.fire("register_failed",
                            error_code="SERVER_NOT_REACHABLE")
            self.log.err(f"register 예외: {type(exc).__name__}")
            self.root.after(0,
                             lambda: self.var_reg_status.set(
                                 "✗ 서버 접속 실패"))
        finally:
            self.root.after(0, lambda: self.var_code.set(""))
            try:
                self.root.after(0,
                                 lambda: self.btn_register.configure(
                                     state="normal", text="Register  →"))
            except Exception:
                pass

    def on_connect(self) -> None:
        agent_id = self.ctrl.model.agent_id
        server = self.ctrl.model.server_url
        if not agent_id:
            messagebox.showinfo("등록 필요", "먼저 등록하세요.")
            self.show_page(PAGE_REGISTRATION)
            return
        if self._ws_thread and self._ws_thread.is_alive():
            messagebox.showinfo("이미 연결됨", "이미 WebSocket 연결 중입니다.")
            return
        token = ts.load_device_token(server_url=server, agent_id=agent_id)
        if not token:
            self.ctrl.fire("reset_token", error_code="TOKEN_NOT_STORED")
            self.log.warn("token 미저장 — 재등록 필요")
            messagebox.showwarning("재등록 필요",
                                    "device_token 이 없습니다. 재등록하세요.")
            self.show_page(PAGE_REGISTRATION)
            return
        self._ws_thread = threading.Thread(
            target=self._ws_worker, args=(server, agent_id, token), daemon=True,
        )
        self._ws_thread.start()
        token = ""

    def _ws_worker(self, server: str, agent_id: str, token: str) -> None:
        try:
            self.ctrl.fire("connect_start")
            self.log.info(f"WebSocket 연결 시도 · {cd.mask_agent_id(agent_id)}")
            os.environ["HAEHAN_AGENT_WS_ENABLED"] = "true"
            os.environ["HAEHAN_AGENT_SERVER"] = server
            from . import websocket_client as ws
            ws.connect(agent_id=agent_id, device_token=token)
        except Exception as exc:
            self.ctrl.fire("connect_failed",
                            error_code="SERVER_NOT_REACHABLE")
            self.log.err(f"WS 연결 실패: {type(exc).__name__}")
        finally:
            token = ""
            self.ctrl.fire("ws_closed")
            self.log.info("WebSocket 종료")

    def on_diagnostics(self) -> None:
        if not _HAS_CTK:
            return
        block = self.ctrl.render_user_block()
        ctk = _ctk
        win = ctk.CTkToplevel(self.root)
        win.title("진단")
        win.geometry("620x440")
        win.configure(fg_color=COLOR["bg_canvas"])
        tb = ctk.CTkTextbox(win, wrap="word",
                              fg_color=COLOR["bg_card"],
                              text_color=COLOR["fg"],
                              border_color=COLOR["border_sub"],
                              border_width=1,
                              corner_radius=8,
                              font=("Consolas", 11))
        tb.insert("1.0", block)
        tb.configure(state="disabled")
        tb.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        ctk.CTkButton(win, text="닫기", command=win.destroy,
                        width=100, height=32, corner_radius=8,
                        fg_color=COLOR["accent"],
                        hover_color=COLOR["accent_hi"]).pack(pady=10)

    def on_reset(self) -> None:
        m = self.ctrl.model
        if not m.agent_id:
            messagebox.showinfo("정보", "저장된 token 이 없습니다.")
            return
        if not messagebox.askyesno("재등록 확인",
                                     "저장된 token 을 삭제하고 재등록 화면으로 이동합니다. 계속할까요?"):
            return
        try:
            ts.delete_device_token(server_url=m.server_url,
                                    agent_id=m.agent_id)
        except Exception:
            pass
        self.ctrl.fire("reset_token", user_event="token 삭제됨")
        self.log.warn("token 삭제 — 재등록 필요")
        self.show_page(PAGE_REGISTRATION)

    def on_quit(self) -> None:
        try:
            self.log.info("GUI 종료")
            self.root.destroy()
        except Exception:
            pass

    # ── 단축키 ────────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        b = self.root.bind_all
        b("<Control-Key-1>", lambda e: self.show_page(PAGE_DASHBOARD))
        b("<Control-Key-2>", lambda e: self.show_page(PAGE_REGISTRATION))
        b("<Control-Key-3>", lambda e: self.show_page(PAGE_LOGS))
        b("<Control-Key-4>", lambda e: self.show_page(PAGE_SETTINGS))
        b("<Control-r>", lambda e: self.on_reset())
        b("<Control-R>", lambda e: self.on_reset())
        b("<F1>", lambda e: self.on_diagnostics())
        b("<Escape>", lambda e: self.on_quit())

    # ── 폴링 + 모션 ──────────────────────────────────────────

    def _poll_model(self) -> None:
        m = self.ctrl.model
        label = _state_label(m.state)
        if _HAS_CTK:
            # 상태 바
            self.var_status.set(f"●  {label}  ·  {m.agent_id_masked or '미등록'}")
            try:
                self.lbl_status.configure(text_color=_state_color(m.state))
            except Exception:
                pass
            # Dashboard 상태 카드
            try:
                self.var_dash_state_pill.set(f"●  {label}")
                self.dash_state_pill.configure(text_color=_state_color(m.state))
                self.dash_state_card.configure(fg_color=_state_bg(m.state))
            except Exception:
                pass
            self.var_dash_aid.set(
                f"agent_id        {m.agent_id_masked or '—'}")
            self.var_dash_hb.set(
                f"last heartbeat  {m.last_heartbeat_iso or '—'}")
            self.var_dash_rc.set(f"reconnect       {m.reconnect_count}")
            try:
                self.var_dash_server.set(
                    cd._strip_secrets_from_url(m.server_url))
            except Exception:
                pass
            self.var_dash_hb_meta.set(
                f"{len(self._heartbeat_history)} heartbeats · {m.last_error_code or '안정'}")
            # sparkline 갱신
            if self._heartbeat_history and _HAS_CTK:
                try:
                    img = icons.make_sparkline(list(self._heartbeat_history),
                                                 width=240, height=36,
                                                 line_color=_state_color(m.state),
                                                 fill_color=_state_color(m.state),
                                                 bg=COLOR["bg_card"])
                    if img is not None:
                        from customtkinter import CTkImage  # type: ignore
                        self._sparkline_img = CTkImage(light_image=img,
                                                         dark_image=img,
                                                         size=(240, 36))
                        self.dash_sparkline_label.configure(
                            image=self._sparkline_img, text="")
                except Exception:
                    pass
        else:
            try:
                self.var_status.set(f"●  {label}")
            except Exception:
                pass
        self.root.after(500, self._poll_model)

    def _tick_motion(self) -> None:
        # heartbeat 시뮬 — 실제 ws heartbeat 가 fire 시 controller 가 갱신.
        # 본 데모는 last_heartbeat_iso 변화 감지하여 history 에 1 push.
        m = self.ctrl.model
        if m.last_heartbeat_iso:
            self._heartbeat_history.append(random.uniform(0.6, 1.0))
        self._spinner_angle = (self._spinner_angle + 30) % 360
        self.root.after(1000, self._tick_motion)

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(server_url: str = "https://haehan-ai.kr/orchestrator") -> int:
    ctrl = gs.GuiController(server_url=server_url)
    app = HaehanAgentGuiApp(controller=ctrl)
    app.run()
    return 0
