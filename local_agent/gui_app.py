"""HaehanAI-Agent.exe GUI — Wizard + 3탭 미니창 + AI Settings modal.

구조:
  - 첫 실행 or 미등록: Wizard (3 step) 자동 표시
  - 등록 완료 후: 메인 윈도우 (760×640) — Chat / Status / Diagnostics 3탭
  - Chat 탭 기본
  - 우상단 [⚙ AI 설정] → modal (placeholder)
  - [X] 닫기 → 트레이 최소화 (종료 아님)

본 공정 정책:
  - 실제 OpenAI API 호출 0
  - API key 저장 0
  - chat history 디스크 저장 0
  - device_token / registration_code / API key 화면 표시 0
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import threading
import tkinter as tk
from tkinter import messagebox

from . import ai_chat_adapter as _adp
from . import ai_chat_client as _aic
from . import connection_diagnostics as cd
from . import gui_chat_state as cs
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


# ── 디자인 토큰 ────────────────────────────────────────────────

COLOR = {
    "bg": "#0B0D11",
    "panel": "#11141A",
    "surface": "#161A22",
    "card": "#1C2129",
    "card_hov": "#222936",
    "border": "#2D333D",
    "border_sub": "#22272F",
    "fg": "#E6E9EF",
    "fg_muted": "#9AA3B2",
    "fg_subtle": "#6B7484",
    "fg_faint": "#4A5160",
    "accent": "#6366F1",
    "accent_hi": "#818CF8",
    "ok": "#10B981",
    "warn": "#F59E0B",
    "err": "#EF4444",
    "user_bg": "#2D3A85",  # 사용자 메시지 bubble
    "assist_bg": "#1C2129",  # AI 응답 bubble
    "task_bg": "#2B1F0A",  # 작업 위임 카드 배경
}


# ── 페이지 enum (회귀 호환) ────────────────────────────────────

PAGE_CHAT = "chat"
PAGE_STATUS = "status"
PAGE_DIAGNOSTICS = "diagnostics"
ALL_PAGES = (PAGE_CHAT, PAGE_STATUS, PAGE_DIAGNOSTICS)

# 회귀 호환 alias — 직전 audit/tests 가 4탭 enum 을 검사하므로 유지
PAGE_DASHBOARD = PAGE_CHAT  # alias (Dashboard 의 역할은 Chat 이 흡수)
PAGE_REGISTRATION = "registration_wizard"  # wizard 모드
PAGE_LOGS = PAGE_DIAGNOSTICS  # alias (Logs 탭 제거 → Diagnostics 가 흡수)
PAGE_SETTINGS = "ai_settings_modal"  # modal 키워드


def _state_color(s: str) -> str:
    if s in (gs.STATE_HEARTBEAT_OK, gs.STATE_CONNECTED):
        return COLOR["ok"]
    if s in (gs.STATE_AUTH_FAILED, gs.STATE_SERVER_UNREACHABLE):
        return COLOR["err"]
    if s in (gs.STATE_CONNECTING, gs.STATE_AUTHENTICATING, gs.STATE_RECONNECTING):
        return COLOR["warn"]
    return COLOR["fg_subtle"]


def _state_label(s: str) -> str:
    return {
        gs.STATE_NOT_REGISTERED: "미등록",
        gs.STATE_CONNECTING: "연결 중",
        gs.STATE_AUTHENTICATING: "인증 중",
        gs.STATE_CONNECTED: "연결됨",
        gs.STATE_HEARTBEAT_OK: "정상",
        gs.STATE_DISCONNECTED: "끊김",
        gs.STATE_AUTH_FAILED: "인증 실패",
        gs.STATE_RECONNECTING: "재연결 중",
        gs.STATE_SERVER_UNREACHABLE: "서버 접속 실패",
    }.get(s, s)


def _ai_status_color(s: str) -> str:
    if s == cs.AI_READY_PLACEHOLDER:
        return COLOR["ok"]
    if s == cs.AI_ERROR:
        return COLOR["err"]
    return COLOR["fg_subtle"]


# ── 메인 앱 ────────────────────────────────────────────────────


class HaehanAgentGuiApp:
    """Wizard + 3탭 + AI Settings modal."""

    def __init__(
        self,
        *,
        controller: gs.GuiController,
        chat_controller: cs.ChatUiController | None = None,
        adapter: _adp.AiChatAdapter | None = None,
    ):
        self.ctrl = controller
        self.chat = chat_controller or cs.ChatUiController()
        # adapter — controller 의 server_url + agent_id 로 초기화
        self.adapter = adapter or _adp.make_default_adapter(
            mode=cs.MODE_SERVER_PROXY,
            server_url=controller.model.server_url,
            agent_id=controller.model.agent_id,
        )
        self.current_page = PAGE_CHAT
        self._ws_thread: threading.Thread | None = None
        self._tabs: dict[str, object] = {}
        self._tab_buttons: dict[str, object] = {}

        if _HAS_CTK:
            _ctk.set_appearance_mode("dark")
            _ctk.set_default_color_theme("blue")
            self.root = _ctk.CTk()
        else:
            self.root = tk.Tk()
            self.root.configure(bg=COLOR["bg"])
        self.root.title("Haehan AI · Local Agent")
        self.root.geometry("760x640")
        self.root.minsize(680, 560)
        # [X] 닫기 → 트레이 최소화
        self.root.protocol("WM_DELETE_WINDOW", self.on_minimize_to_tray)

        self._build_layout()
        self._bind_shortcuts()
        self._poll_model()

        # 미등록이면 wizard 자동 표시
        if not self.ctrl.model.agent_id:
            self.root.after(200, self.open_wizard)

    # ── 레이아웃 ─────────────────────────────────────────────

    def _build_layout(self) -> None:
        if _HAS_CTK:
            self._build_layout_ctk()
        else:
            self._build_layout_fallback()

    def _build_layout_ctk(self) -> None:
        ctk = _ctk
        # 상단 탭바
        topbar = ctk.CTkFrame(self.root, height=48, corner_radius=0, fg_color=COLOR["panel"])
        topbar.pack(side="top", fill="x")
        topbar.pack_propagate(False)

        # 탭 버튼
        for key, label in (
            (PAGE_CHAT, "Chat"),
            (PAGE_STATUS, "Status"),
            (PAGE_DIAGNOSTICS, "Diagnostics"),
        ):
            btn = ctk.CTkButton(
                topbar,
                text=label,
                width=110,
                height=32,
                corner_radius=6,
                fg_color="transparent",
                hover_color=COLOR["card_hov"],
                text_color=COLOR["fg_muted"],
                font=("Segoe UI", 12),
                command=lambda k=key: self.show_page(k),
            )
            btn.pack(side="left", padx=4, pady=8)
            self._tab_buttons[key] = btn

        # 우측 [AI 설정] [≡]
        ctk.CTkButton(
            topbar,
            text="⚙ AI 설정",
            width=110,
            height=32,
            corner_radius=6,
            fg_color=COLOR["card"],
            hover_color=COLOR["card_hov"],
            text_color=COLOR["fg"],
            border_color=COLOR["border"],
            border_width=1,
            font=("Segoe UI", 11),
            command=self.open_ai_settings,
        ).pack(side="right", padx=(4, 12), pady=8)

        # 메인 영역
        self.main = ctk.CTkFrame(self.root, fg_color=COLOR["surface"], corner_radius=0)
        self.main.pack(side="top", fill="both", expand=True)

        # 페이지 생성
        self._tabs[PAGE_CHAT] = self._build_chat_tab(self.main)
        self._tabs[PAGE_STATUS] = self._build_status_tab(self.main)
        self._tabs[PAGE_DIAGNOSTICS] = self._build_diagnostics_tab(self.main)

        # 하단 상태바
        self.statusbar = ctk.CTkFrame(self.root, height=28, corner_radius=0, fg_color=COLOR["panel"])
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.pack_propagate(False)
        self.var_statusbar = tk.StringVar(value="●  미등록")
        ctk.CTkLabel(
            self.statusbar, textvariable=self.var_statusbar, text_color=COLOR["fg_subtle"], font=("Segoe UI", 11)
        ).pack(side="left", padx=14)
        ctk.CTkLabel(
            self.statusbar, text="v0.1.0 · unsigned", text_color=COLOR["fg_faint"], font=("Segoe UI", 10)
        ).pack(side="right", padx=14)

        self.show_page(PAGE_CHAT)

    def _build_layout_fallback(self) -> None:
        from tkinter import ttk

        ttk.Label(self.root, text="customtkinter 미설치 — pip install customtkinter").pack(pady=20)
        for key, cb in (("등록", self.open_wizard), ("AI 설정", self.open_ai_settings), ("종료", self.on_quit)):
            ttk.Button(self.root, text=key, command=cb).pack(pady=4)
        # 회귀 호환 — 변수 존재
        self.var_server = tk.StringVar(value=self.ctrl.model.server_url)
        self.var_code = tk.StringVar(value="")
        self.var_statusbar = tk.StringVar(value="●  미등록")

    # ── Chat 탭 ───────────────────────────────────────────────

    def _build_chat_tab(self, parent):
        ctk = _ctk
        frame = ctk.CTkFrame(parent, fg_color=COLOR["surface"])

        # AI 상태 badge (상단)
        top = ctk.CTkFrame(frame, fg_color="transparent", height=44)
        top.pack(fill="x", padx=20, pady=(16, 8))
        top.pack_propagate(False)
        self.var_ai_badge = tk.StringVar(value="● AI 미설정")
        self.lbl_ai_badge = ctk.CTkLabel(
            top,
            textvariable=self.var_ai_badge,
            text_color=COLOR["fg_subtle"],
            font=("Segoe UI", 12, "bold"),
        )
        self.lbl_ai_badge.pack(side="left")
        ctk.CTkButton(
            top,
            text="[ ⚙ AI 설정 ]",
            width=110,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=COLOR["card_hov"],
            text_color=COLOR["fg_muted"],
            border_color=COLOR["border"],
            border_width=1,
            font=("Segoe UI", 10),
            command=self.open_ai_settings,
        ).pack(side="right")

        # 메시지 영역 (scroll)
        self.chat_messages = ctk.CTkScrollableFrame(
            frame,
            fg_color=COLOR["card"],
            border_color=COLOR["border_sub"],
            border_width=1,
            corner_radius=10,
        )
        self.chat_messages.pack(fill="both", expand=True, padx=20, pady=4)

        # 첫 안내 메시지
        self._add_system_message("안녕하세요. 무엇을 도와드릴까요?\n(현재 AI 연결은 placeholder 단계 — 실제 호출 0)")

        # 민감정보 경고 배너
        ctk.CTkLabel(
            frame,
            text="⚠ 비밀번호 · 주민번호 · API key 등 민감정보 입력 금지",
            text_color=COLOR["warn"],
            font=("Segoe UI", 10),
        ).pack(fill="x", padx=20, pady=(8, 4))

        # 입력 영역
        input_row = ctk.CTkFrame(frame, fg_color="transparent")
        input_row.pack(fill="x", padx=20, pady=(4, 16))

        self.chat_input = ctk.CTkTextbox(
            input_row,
            height=64,
            fg_color=COLOR["card"],
            text_color=COLOR["fg"],
            border_color=COLOR["border"],
            border_width=1,
            corner_radius=8,
            font=("Segoe UI", 12),
        )
        self.chat_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        # Enter / Shift+Enter
        self.chat_input.bind("<Return>", self._on_chat_enter)
        self.chat_input.bind("<Shift-Return>", lambda e: None)
        # placeholder text
        self._chat_placeholder = "메시지를 입력하세요…  (Enter 전송, Shift+Enter 줄바꿈)"
        self.chat_input.insert("1.0", self._chat_placeholder)
        self.chat_input.configure(text_color=COLOR["fg_subtle"])
        self.chat_input.bind("<FocusIn>", self._chat_focus_in)
        self.chat_input.bind("<FocusOut>", self._chat_focus_out)

        self.btn_send = ctk.CTkButton(
            input_row,
            text="전송",
            width=80,
            height=64,
            corner_radius=8,
            fg_color=COLOR["accent"],
            hover_color=COLOR["accent_hi"],
            font=("Segoe UI", 12, "bold"),
            command=self.on_send_chat,
        )
        self.btn_send.pack(side="right")

        return frame

    def _chat_focus_in(self, _e):
        if self.chat_input.get("1.0", "end-1c") == self._chat_placeholder:
            self.chat_input.delete("1.0", "end")
            self.chat_input.configure(text_color=COLOR["fg"])

    def _chat_focus_out(self, _e):
        if not self.chat_input.get("1.0", "end-1c").strip():
            self.chat_input.delete("1.0", "end")
            self.chat_input.insert("1.0", self._chat_placeholder)
            self.chat_input.configure(text_color=COLOR["fg_subtle"])

    def _on_chat_enter(self, event):
        # Shift 가 눌리지 않은 Enter 만 전송 (Shift+Enter 는 기본 줄바꿈)
        if event.state & 0x0001:  # Shift
            return None
        self.on_send_chat()
        return "break"

    def on_send_chat(self) -> None:
        text = self.chat_input.get("1.0", "end-1c").strip()
        if not text or text == self._chat_placeholder:
            return
        # validate
        ok, reason = self.adapter.validate_message(text)
        if not ok:
            messagebox.showwarning("전송 불가", reason)
            return
        # 민감정보 감지
        if self.adapter.detect_sensitive_input(text):
            self.chat.inc_pii_warning()
            if not messagebox.askyesno(
                "민감정보 감지",
                "입력에 민감정보(토큰/비밀번호/주민번호 등) 가 포함된 것 같습니다.\n그래도 전송하시겠어요?",
            ):
                return
        # 표시는 redact 적용본만
        text_redacted = _aic.redact_input(text)
        self._add_user_message(text_redacted)
        self.chat_input.delete("1.0", "end")
        # adapter 호출 (placeholder)
        resp = self.adapter.send_message(text_raw=text)
        text = ""  # 원문 즉시 폐기
        if resp.ok:
            self._add_assistant_message(resp.text_redacted)
        else:
            self._add_system_message(f"[오류] {resp.error_code or '응답 실패'}")

    # ── 메시지 bubble ────────────────────────────────────────

    def _add_user_message(self, text_redacted: str) -> None:
        ctk = _ctk
        if not _HAS_CTK:
            return
        row = ctk.CTkFrame(self.chat_messages, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row, text="나", text_color=COLOR["fg_subtle"], font=("Segoe UI", 9)).pack(
            side="right", padx=(0, 12)
        )
        bubble = ctk.CTkLabel(
            row,
            text=text_redacted,
            fg_color=COLOR["user_bg"],
            text_color="white",
            font=("Segoe UI", 11),
            wraplength=520,
            justify="left",
            corner_radius=10,
            padx=12,
            pady=8,
        )
        bubble.pack(side="right", anchor="e")
        self.chat.append_message(cs.ChatUiMessage(role="user", text_redacted=text_redacted))
        self._scroll_chat_to_bottom()

    def _add_assistant_message(self, text_redacted: str) -> None:
        ctk = _ctk
        if not _HAS_CTK:
            return
        row = ctk.CTkFrame(self.chat_messages, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row, text="AI", text_color=COLOR["accent_hi"], font=("Segoe UI", 9, "bold")).pack(
            side="left", padx=(12, 0)
        )
        bubble = ctk.CTkLabel(
            row,
            text=text_redacted,
            fg_color=COLOR["assist_bg"],
            text_color=COLOR["fg"],
            font=("Segoe UI", 11),
            wraplength=520,
            justify="left",
            corner_radius=10,
            padx=12,
            pady=8,
        )
        bubble.pack(side="left", anchor="w")
        self.chat.append_message(cs.ChatUiMessage(role="assistant", text_redacted=text_redacted))
        self._scroll_chat_to_bottom()

    def _add_system_message(self, text_redacted: str) -> None:
        ctk = _ctk
        if not _HAS_CTK:
            return
        ctk.CTkLabel(
            self.chat_messages,
            text=text_redacted,
            text_color=COLOR["fg_subtle"],
            fg_color="transparent",
            font=("Segoe UI", 10),
            wraplength=560,
            justify="center",
        ).pack(pady=8)
        self.chat.append_message(cs.ChatUiMessage(role="system", text_redacted=text_redacted))

    def _add_task_card(self, summary: str) -> None:
        """작업 위임 카드 placeholder (다음 공정에서 실제 데이터 연결)."""
        ctk = _ctk
        if not _HAS_CTK:
            return
        card = ctk.CTkFrame(
            self.chat_messages, fg_color=COLOR["task_bg"], border_color=COLOR["warn"], border_width=1, corner_radius=10
        )
        card.pack(fill="x", padx=24, pady=6)
        ctk.CTkLabel(card, text=f"[작업 위임] {summary}", text_color=COLOR["warn"], font=("Segoe UI", 11, "bold")).pack(
            anchor="w", padx=12, pady=(8, 4)
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=(0, 8), padx=12)
        ctk.CTkButton(row, text="승인", width=80, height=28, fg_color=COLOR["ok"], hover_color="#0EA372").pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            row,
            text="거절",
            width=80,
            height=28,
            fg_color=COLOR["card"],
            hover_color=COLOR["card_hov"],
            text_color=COLOR["fg"],
            border_color=COLOR["border"],
            border_width=1,
        ).pack(side="left", padx=4)
        self.chat.append_message(
            cs.ChatUiMessage(role="system", text_redacted=summary, is_task_card=True, task_card_text=summary)
        )

    def _scroll_chat_to_bottom(self) -> None:
        try:
            self.root.update_idletasks()
            self.chat_messages._parent_canvas.yview_moveto(1.0)
        except Exception:  # noqa: S110
            pass

    # ── Status 탭 ─────────────────────────────────────────────

    def _build_status_tab(self, parent):
        ctk = _ctk
        frame = ctk.CTkFrame(parent, fg_color=COLOR["surface"])
        ctk.CTkLabel(frame, text="Status", text_color=COLOR["fg"], font=("Segoe UI", 18, "bold")).pack(
            anchor="w", padx=24, pady=(20, 4)
        )
        ctk.CTkLabel(frame, text="연결 상태 + AI mode", text_color=COLOR["fg_subtle"], font=("Segoe UI", 11)).pack(
            anchor="w", padx=24, pady=(0, 16)
        )

        card = ctk.CTkFrame(
            frame, fg_color=COLOR["card"], border_color=COLOR["border_sub"], border_width=1, corner_radius=12
        )
        card.pack(fill="x", padx=24)

        self.var_status_state = tk.StringVar(value="● 미등록")
        self.lbl_status_state = ctk.CTkLabel(
            card,
            textvariable=self.var_status_state,
            text_color=COLOR["fg_subtle"],
            font=("Segoe UI", 14, "bold"),
        )
        self.lbl_status_state.pack(anchor="w", padx=18, pady=(14, 8))

        self.var_status_aid = tk.StringVar(value="agent_id        —")
        self.var_status_srv = tk.StringVar(value="서버            —")
        self.var_status_ws = tk.StringVar(value="WS              —")
        self.var_status_hb = tk.StringVar(value="last heartbeat  —")
        self.var_status_rc = tk.StringVar(value="reconnect       0")
        self.var_status_ai = tk.StringVar(value="AI mode         미설정")
        for var in (
            self.var_status_aid,
            self.var_status_srv,
            self.var_status_ws,
            self.var_status_hb,
            self.var_status_rc,
            self.var_status_ai,
        ):
            ctk.CTkLabel(card, textvariable=var, text_color=COLOR["fg_muted"], font=("Consolas", 11)).pack(
                anchor="w", padx=18, pady=2
            )

        ctk.CTkLabel(card, text="", fg_color="transparent").pack(pady=4)

        # 버튼
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(anchor="w", padx=24, pady=16)
        ctk.CTkButton(
            row,
            text="재연결",
            command=self.on_reconnect,
            width=110,
            height=34,
            corner_radius=8,
            fg_color=COLOR["ok"],
            hover_color="#0EA372",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="재등록",
            command=self.on_reset,
            width=110,
            height=34,
            corner_radius=8,
            fg_color="transparent",
            hover_color=COLOR["card_hov"],
            text_color=COLOR["warn"],
            border_color=COLOR["warn"],
            border_width=1,
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="⚙ AI 설정",
            command=self.open_ai_settings,
            width=110,
            height=34,
            corner_radius=8,
            fg_color=COLOR["card"],
            hover_color=COLOR["card_hov"],
            text_color=COLOR["fg"],
            border_color=COLOR["border"],
            border_width=1,
            font=("Segoe UI", 11),
        ).pack(side="left")
        return frame

    # ── Diagnostics 탭 ────────────────────────────────────────

    def _build_diagnostics_tab(self, parent):
        ctk = _ctk
        frame = ctk.CTkFrame(parent, fg_color=COLOR["surface"])
        ctk.CTkLabel(frame, text="Diagnostics", text_color=COLOR["fg"], font=("Segoe UI", 18, "bold")).pack(
            anchor="w", padx=24, pady=(20, 4)
        )
        ctk.CTkLabel(
            frame, text="진단 (마스킹 적용 · 복사 시 redact)", text_color=COLOR["fg_subtle"], font=("Segoe UI", 11)
        ).pack(anchor="w", padx=24, pady=(0, 16))

        self.diag_textbox = ctk.CTkTextbox(
            frame,
            wrap="word",
            fg_color=COLOR["card"],
            text_color=COLOR["fg"],
            border_color=COLOR["border_sub"],
            border_width=1,
            corner_radius=10,
            font=("Consolas", 11),
        )
        self.diag_textbox.pack(fill="both", expand=True, padx=24, pady=4)
        self._refresh_diagnostics_text()

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(anchor="w", padx=24, pady=16)
        ctk.CTkButton(
            row,
            text="복사",
            command=self.on_copy_diagnostics,
            width=100,
            height=32,
            corner_radius=8,
            fg_color=COLOR["accent"],
            hover_color=COLOR["accent_hi"],
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="재등록",
            command=self.on_reset,
            width=100,
            height=32,
            corner_radius=8,
            fg_color="transparent",
            hover_color=COLOR["card_hov"],
            text_color=COLOR["warn"],
            border_color=COLOR["warn"],
            border_width=1,
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="⚙ AI 설정",
            command=self.open_ai_settings,
            width=110,
            height=32,
            corner_radius=8,
            fg_color=COLOR["card"],
            hover_color=COLOR["card_hov"],
            text_color=COLOR["fg"],
            border_color=COLOR["border"],
            border_width=1,
            font=("Segoe UI", 11),
        ).pack(side="left")
        return frame

    def _refresh_diagnostics_text(self) -> None:
        block = self.ctrl.render_user_block()
        # AI mode 정보 추가 1행
        m = self.chat.state.ai_mode
        ai_line = (
            f"\nOpenAI    {m.fingerprint or '—'} (mode={cs.mode_label_kr(m.mode)}, last_test={m.last_test_iso or '—'})"
        )
        full = block + ai_line
        try:
            self.diag_textbox.configure(state="normal")
            self.diag_textbox.delete("1.0", "end")
            self.diag_textbox.insert("1.0", full)
            self.diag_textbox.configure(state="disabled")
        except Exception:  # noqa: S110
            pass

    def on_copy_diagnostics(self) -> None:
        block = self.ctrl.render_user_block()
        m = self.chat.state.ai_mode
        ai_line = f"\nOpenAI    {m.fingerprint or '—'} (mode={m.mode}, last_test={m.last_test_iso or '—'})"
        # redact 한 번 더 안전
        text = _aic.redact_input(block + ai_line)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("복사됨", "진단 텍스트가 복사되었습니다 (마스킹 적용).")
        except Exception:  # noqa: S110
            pass

    # ── Tab 전환 ──────────────────────────────────────────────

    def show_page(self, page: str) -> None:
        # alias 매핑
        if page in (PAGE_REGISTRATION,):
            self.open_wizard()
            return
        if page in (PAGE_SETTINGS,):
            self.open_ai_settings()
            return
        if page not in ALL_PAGES:
            # alias 처리 — Dashboard/Logs → Chat/Diagnostics
            if page == "dashboard":
                page = PAGE_CHAT
            elif page == "logs":
                page = PAGE_DIAGNOSTICS
            else:
                return
        # 모든 탭 숨기기
        for k, w in self._tabs.items():  # noqa: B007
            try:
                w.pack_forget()
            except Exception:  # noqa: S110
                pass
        # 활성 탭 표시
        try:
            self._tabs[page].pack(fill="both", expand=True)
        except Exception:  # noqa: S110
            pass
        self.current_page = page
        # 탭 버튼 강조
        for k, b in self._tab_buttons.items():
            active = k == page
            try:
                b.configure(
                    text_color=COLOR["fg"] if active else COLOR["fg_muted"],
                    fg_color=COLOR["card"] if active else "transparent",
                )
            except Exception:  # noqa: S110
                pass
        if page == PAGE_DIAGNOSTICS:
            self._refresh_diagnostics_text()

    # ── Wizard ────────────────────────────────────────────────

    def open_wizard(self) -> None:
        if not _HAS_CTK:
            return
        ctk = _ctk
        win = ctk.CTkToplevel(self.root)
        win.title("Haehan AI Local Agent — 첫 등록")
        win.geometry("560x480")
        win.configure(fg_color=COLOR["bg"])
        win.grab_set()

        state = {"step": 1, "server": self.ctrl.model.server_url, "code": ""}
        body = ctk.CTkFrame(win, fg_color=COLOR["bg"])
        body.pack(fill="both", expand=True, padx=24, pady=24)

        title = ctk.CTkLabel(body, text="Step 1 of 3 — 서버 URL", text_color=COLOR["fg"], font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w", pady=(0, 8))
        subtitle = ctk.CTkLabel(
            body, text="기본값을 사용하거나 관리자 안내 URL 입력", text_color=COLOR["fg_subtle"], font=("Segoe UI", 11)
        )
        subtitle.pack(anchor="w", pady=(0, 16))

        content = ctk.CTkFrame(body, fg_color=COLOR["bg"])
        content.pack(fill="both", expand=True)

        # Step 1 widgets
        var_server = tk.StringVar(value=state["server"])
        ent_server = ctk.CTkEntry(
            content,
            textvariable=var_server,
            width=460,
            height=36,
            fg_color=COLOR["card"],
            border_color=COLOR["border"],
            text_color=COLOR["fg"],
        )

        # Step 2 widgets — env HAEHAN_AGENT_CODE 가 있으면 자동 주입
        _env_code = os.environ.get("HAEHAN_AGENT_CODE", "").strip()
        var_code = tk.StringVar(value=_env_code)
        _auto_submit = bool(_env_code)
        ent_code = ctk.CTkEntry(
            content,
            textvariable=var_code,
            width=460,
            height=36,
            show="●",
            fg_color=COLOR["card"],
            border_color=COLOR["border"],
            text_color=COLOR["fg"],
            placeholder_text="관리자에게 받은 1회용 코드",
        )

        # Step 3 result label
        var_result = tk.StringVar(value="등록 진행 중…")
        lbl_result = ctk.CTkLabel(content, textvariable=var_result, text_color=COLOR["fg"], font=("Segoe UI", 13))

        # Footer buttons
        footer = ctk.CTkFrame(body, fg_color=COLOR["bg"])
        footer.pack(fill="x", pady=(16, 0))
        btn_prev = ctk.CTkButton(
            footer,
            text="← 이전",
            width=100,
            height=34,
            fg_color="transparent",
            hover_color=COLOR["card_hov"],
            text_color=COLOR["fg_muted"],
            border_color=COLOR["border"],
            border_width=1,
        )
        btn_next = ctk.CTkButton(
            footer,
            text="다음 →",
            width=140,
            height=34,
            fg_color=COLOR["accent"],
            hover_color=COLOR["accent_hi"],
            font=("Segoe UI", 12, "bold"),
        )

        def render():
            # clear content
            for w in content.winfo_children():
                w.pack_forget()
            if state["step"] == 1:
                title.configure(text="Step 1 of 3 — 서버 URL")
                ent_server.pack(anchor="w", pady=8)
                btn_prev.configure(state="disabled")
                btn_next.configure(text="다음 →", command=on_next)
            elif state["step"] == 2:
                title.configure(text="Step 2 of 3 — 등록코드")
                ctk.CTkLabel(
                    content,
                    text="관리자에게 받은 1회용 코드 (10분 유효)",
                    text_color=COLOR["fg_muted"],
                    font=("Segoe UI", 10),
                ).pack(anchor="w", pady=(0, 4))
                ent_code.pack(anchor="w", pady=4)
                btn_prev.configure(state="normal", command=on_prev)
                btn_next.configure(text="등록 →", command=on_register)
            else:
                title.configure(text="Step 3 of 3 — 완료")
                lbl_result.pack(pady=24)
                btn_prev.configure(state="disabled")
                btn_next.configure(text="시작하기", command=lambda: (win.destroy(), self.show_page(PAGE_CHAT)))

        def on_next():
            state["server"] = (var_server.get() or "").strip()
            if not state["server"]:
                messagebox.showwarning("필요", "서버 URL 을 입력하세요.")
                return
            state["step"] = 2
            render()
            # env code 있으면 Step 2 진입 직후 자동 등록 (사용자 클릭 불필요)
            if _auto_submit:
                win.after(300, on_register)

        def on_prev():
            state["step"] = max(1, state["step"] - 1)
            render()

        def on_register():
            code = (var_code.get() or "").strip()
            if not code:
                messagebox.showwarning("필요", "등록코드를 입력하세요.")
                return
            self.ctrl.set_server_url(state["server"])
            state["step"] = 3
            var_result.set("등록 중… 잠시만 기다려 주세요.")
            render()
            threading.Thread(
                target=self._wizard_register_worker, args=(state["server"], code, var_result, win), daemon=True
            ).start()
            # immediately wipe code (variable scope)
            var_code.set("")

        # env code 자동 진행 — Step 1 도 기본 server_url 로 자동 통과
        if _auto_submit:
            win.after(200, on_next)
        btn_prev.pack(side="left")
        btn_next.pack(side="right")
        render()

    def _wizard_register_worker(self, server: str, code: str, var_result: tk.StringVar, win) -> None:
        try:
            host = socket.gethostname() or "unknown-host"
            os_name = platform.system() + " " + platform.release()
            meta, device_token = rcli.register_with_code(
                server_url=server,
                registration_code=code,
                host=host,
                os_name=os_name,
                version="0.1.0",
            )
            ts.save_device_token(server_url=server, agent_id=meta.agent_id, token=device_token)
            device_token = ""
            code = ""
            self.ctrl.set_agent_id(meta.agent_id)
            self.ctrl.fire("register_success", user_event=f"등록 성공 · {cd.mask_agent_id(meta.agent_id)}")
            # adapter 가 새 server_url/agent_id 를 인지하도록 context 갱신
            try:
                if hasattr(self.adapter, "set_context"):
                    self.adapter.set_context(server_url=server, agent_id=meta.agent_id)
            except Exception:  # noqa: S110
                pass
            self.root.after(0, lambda: var_result.set(f"✓ 등록 성공\nagent_id: {cd.mask_agent_id(meta.agent_id)}"))
        except rcli.RegistrationError:
            self.root.after(0, lambda: var_result.set("✗ 등록 실패: 코드가 유효하지 않거나 서버 오류"))
        except ts.TokenStoreError:
            self.root.after(0, lambda: var_result.set("✗ 등록 실패: token 저장 실패"))
        except Exception as exc:
            exc_name = type(exc).__name__
            self.root.after(0, lambda: var_result.set(f"✗ 등록 실패: {exc_name}"))

    # ── AI Settings modal ──────────────────────────────────

    def open_ai_settings(self) -> None:
        if not _HAS_CTK:
            return
        ctk = _ctk
        win = ctk.CTkToplevel(self.root)
        win.title("AI 설정")
        win.geometry("520x440")
        win.configure(fg_color=COLOR["bg"])
        win.grab_set()

        body = ctk.CTkFrame(win, fg_color=COLOR["bg"])
        body.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(body, text="AI 연결 방식", text_color=COLOR["fg"], font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(0, 4)
        )
        ctk.CTkLabel(
            body,
            text="현재 공정은 UI 만 — 실제 AI 연결은 다음 공정에서 활성화",
            text_color=COLOR["fg_subtle"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 12))

        var_mode = tk.StringVar(value=self.chat.state.ai_mode.mode)
        for mode_key, label in (
            (cs.MODE_SERVER_PROXY, "Production Server Proxy (상용 기본)"),
            (cs.MODE_DEV_TEST_KEY, "Developer Test Key (개발 테스트)"),
            (cs.MODE_USER_BYOK, "User BYOK Advanced (사용자 자기 키)"),
        ):
            ctk.CTkRadioButton(
                body,
                text=label,
                variable=var_mode,
                value=mode_key,
                command=lambda m=mode_key: self._on_mode_change(m, key_frame),
                text_color=COLOR["fg"],
                fg_color=COLOR["accent"],
                hover_color=COLOR["accent_hi"],
                font=("Segoe UI", 11),
            ).pack(anchor="w", pady=4)

        # key 입력 frame (mode 가 dev/byok 일 때만 표시)
        key_frame = ctk.CTkFrame(
            body, fg_color=COLOR["card"], border_color=COLOR["border_sub"], border_width=1, corner_radius=8
        )
        key_frame.pack(fill="x", pady=(16, 8))

        ctk.CTkLabel(key_frame, text="OpenAI API key", text_color=COLOR["fg_muted"], font=("Segoe UI", 10)).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        var_key = tk.StringVar(value="")
        ent_key = ctk.CTkEntry(
            key_frame,
            textvariable=var_key,
            show="●",
            width=440,
            height=34,
            fg_color=COLOR["card_hov"],
            border_color=COLOR["border"],
            text_color=COLOR["fg"],
            placeholder_text="sk-… (이번 공정에서는 저장 안 됨)",
        )
        ent_key.pack(anchor="w", padx=12, pady=(0, 6))
        # 저장 상태 (live fingerprint)
        from . import openai_key_store as _ks

        var_save_state = tk.StringVar(value="")

        def _refresh_save_state():
            try:
                fp = _ks.get_key_fingerprint()
                if fp:
                    var_save_state.set(f"저장됨 · {fp}")
                else:
                    var_save_state.set("저장 안 됨")
            except Exception:
                var_save_state.set("저장소 접근 실패")

        ctk.CTkLabel(
            key_frame,
            textvariable=var_save_state,
            text_color=COLOR["fg_subtle"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=12, pady=(0, 10))
        _refresh_save_state()

        self._key_frame_widget = key_frame
        self._on_mode_change(var_mode.get(), key_frame)

        # ── 버튼 (DEV_TEST_KEY 모드만 활성) ──
        from . import gui_chat_state as _cs2
        from . import openai_chat_client as _occ

        def _on_save():
            raw = (var_key.get() or "").strip()
            if not raw:
                messagebox.showwarning("입력 필요", "API key 를 입력하세요.")
                return
            ok_v, code = _ks.validate_key_format(raw)  # noqa: RUF059
            if not ok_v:
                messagebox.showwarning("형식 오류", "API key 형식이 올바르지 않습니다.")
                # raw 즉시 폐기
                var_key.set("")
                return
            r = _ks.save_dev_key(raw)
            # 입력값 즉시 폐기
            var_key.set("")
            raw = ""
            if r.ok:
                messagebox.showinfo("저장됨", f"API key 가 저장되었습니다.\n{r.fingerprint}")
                _refresh_save_state()
                self.chat.set_fingerprint(r.fingerprint)
            else:
                messagebox.showerror("저장 실패", f"저장 실패: {r.error_code}")

        def _on_test():
            self.btn_modal_test.configure(state="disabled", text="테스트 중…")
            self.root.update_idletasks()
            try:
                mode = var_mode.get()
                if mode == _cs2.MODE_DEV_TEST_KEY:
                    client = _occ.OpenAiDirectTestClient()
                    if not client.is_configured():
                        messagebox.showwarning("키 없음", "먼저 API key 를 저장하세요.")
                        return
                    resp = client.health_check(timeout=15)
                    ok = resp.ok
                    model = resp.usage_summary.get("model", "?")
                    err_code = resp.error_code
                    err_msg = resp.user_message_kr
                    duration = resp.duration_ms
                    rlen = len(resp.text_redacted)
                elif mode == _cs2.MODE_SERVER_PROXY:
                    from . import server_proxy_chat_client as _spc

                    if not self.ctrl.model.agent_id:
                        messagebox.showwarning("등록 필요", "먼저 등록을 완료하세요. (agent_id 가 없습니다.)")
                        return
                    client = _spc.ServerProxyChatClient(
                        server_url=self.ctrl.model.server_url,
                        agent_id=self.ctrl.model.agent_id,
                    )
                    resp = client.health_check(timeout=10)
                    ok = resp.ok
                    model = resp.model or "(server default)"
                    err_code = resp.error_code
                    err_msg = resp.user_message_kr
                    duration = resp.duration_ms
                    rlen = len(resp.text_redacted)
                else:
                    messagebox.showinfo("준비 중", "USER_BYOK 모드는 별도 공정에서 활성화 예정입니다.")
                    return

                if ok:
                    self.chat.set_ai_status(_cs2.AI_READY_PLACEHOLDER)
                    messagebox.showinfo(
                        "연결 테스트 PASS",
                        f"OK\n모델: {model}\n응답 길이: {rlen}자\n소요: {duration}ms",
                    )
                else:
                    self.chat.set_ai_status(_cs2.AI_ERROR, error_code=err_code)
                    messagebox.showerror(
                        "연결 테스트 실패",
                        f"{err_code}\n{err_msg}",
                    )
            finally:
                self.btn_modal_test.configure(state="normal", text="연결 테스트")

        def _on_delete():
            if not messagebox.askyesno(
                "삭제 확인",
                "저장된 API key 를 Credential Manager 에서 삭제합니다. 계속할까요?",
            ):
                return
            try:
                _ks.delete_dev_key()
            except Exception:  # noqa: S110
                pass
            self.chat.set_fingerprint("")
            _refresh_save_state()
            messagebox.showinfo("삭제됨", "API key 가 삭제되었습니다.")

        # mode 가 DEV_TEST_KEY 또는 USER_BYOK 일 때 활성
        dev_mode = var_mode.get() == _cs2.MODE_DEV_TEST_KEY

        row = ctk.CTkFrame(body, fg_color=COLOR["bg"])
        row.pack(fill="x", pady=12)
        self.btn_modal_save = ctk.CTkButton(
            row,
            text="저장",
            width=100,
            height=32,
            fg_color=COLOR["accent"],
            hover_color=COLOR["accent_hi"],
            text_color="white",
            font=("Segoe UI", 11),
            state="normal" if dev_mode else "disabled",
            command=_on_save,
        )
        self.btn_modal_save.pack(side="left", padx=(0, 6))

        self.btn_modal_test = ctk.CTkButton(
            row,
            text="연결 테스트",
            width=110,
            height=32,
            fg_color=COLOR["card"],
            hover_color=COLOR["card_hov"],
            text_color=COLOR["fg"],
            border_color=COLOR["border"],
            border_width=1,
            font=("Segoe UI", 11),
            state="normal" if dev_mode else "disabled",
            command=_on_test,
        )
        self.btn_modal_test.pack(side="left", padx=(0, 6))

        self.btn_modal_delete = ctk.CTkButton(
            row,
            text="삭제",
            width=100,
            height=32,
            fg_color="transparent",
            hover_color=COLOR["card_hov"],
            text_color=COLOR["err"],
            border_color=COLOR["err"],
            border_width=1,
            font=("Segoe UI", 11),
            state="normal" if dev_mode else "disabled",
            command=_on_delete,
        )
        self.btn_modal_delete.pack(side="left")

        # mode 변경 시 버튼 활성 토글
        def _toggle_buttons(*_args):
            mode = var_mode.get()
            is_dev = mode == _cs2.MODE_DEV_TEST_KEY
            is_proxy = mode == _cs2.MODE_SERVER_PROXY
            # 저장/삭제는 dev 모드 한정
            for btn in (self.btn_modal_save, self.btn_modal_delete):
                btn.configure(state="normal" if is_dev else "disabled")
            # 연결 테스트는 dev or proxy 모두 활성
            self.btn_modal_test.configure(state="normal" if (is_dev or is_proxy) else "disabled")

        var_mode.trace_add("write", _toggle_buttons)
        _toggle_buttons()

        ctk.CTkLabel(
            body,
            text="ⓘ Developer Test Key 모드 — 저장된 key 로 실제 OpenAI 호출.\n"
            "   상용 기본은 Production Server Proxy — 사용자 입력 불필요.",
            text_color=COLOR["fg_faint"],
            font=("Segoe UI", 9),
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        ctk.CTkButton(
            body,
            text="닫기",
            width=80,
            height=32,
            fg_color=COLOR["accent"],
            hover_color=COLOR["accent_hi"],
            command=lambda: (var_key.set(""), win.destroy()),
        ).pack(side="right", pady=(8, 0))

    def _on_mode_change(self, mode: str, key_frame) -> None:
        self.chat.set_mode(mode)
        # SERVER_PROXY 모드일 때는 key 입력칸 숨김
        try:
            if mode == cs.MODE_SERVER_PROXY:
                key_frame.pack_forget()
            else:
                key_frame.pack(fill="x", pady=(16, 8))
        except Exception:  # noqa: S110
            pass

    # ── 액션 ────────────────────────────────────────────────

    def on_reconnect(self) -> None:
        if not self.ctrl.model.agent_id:
            messagebox.showinfo("등록 필요", "먼저 등록하세요.")
            return
        if self._ws_thread and self._ws_thread.is_alive():
            messagebox.showinfo("이미 연결됨", "이미 WebSocket 연결 중입니다.")
            return
        token = ts.load_device_token(server_url=self.ctrl.model.server_url, agent_id=self.ctrl.model.agent_id)
        if not token:
            self.ctrl.fire("reset_token", error_code="TOKEN_NOT_STORED")
            messagebox.showwarning("재등록 필요", "device_token 이 없습니다. 재등록하세요.")
            return
        self._ws_thread = threading.Thread(
            target=self._ws_worker,
            args=(self.ctrl.model.server_url, self.ctrl.model.agent_id, token),
            daemon=True,
        )
        self._ws_thread.start()
        token = ""

    def _ws_worker(self, server: str, agent_id: str, token: str) -> None:
        try:
            self.ctrl.fire("connect_start")
            os.environ["HAEHAN_AGENT_WS_ENABLED"] = "true"
            os.environ["HAEHAN_AGENT_SERVER"] = server
            from . import websocket_client as ws

            ws.connect(agent_id=agent_id, device_token=token)
        except Exception:
            self.ctrl.fire("connect_failed", error_code="SERVER_NOT_REACHABLE")
        finally:
            token = ""
            self.ctrl.fire("ws_closed")

    def on_reset(self) -> None:
        m = self.ctrl.model
        if not m.agent_id:
            messagebox.showinfo("정보", "저장된 token 이 없습니다.")
            return
        if not messagebox.askyesno("재등록 확인", "저장된 token 을 삭제하고 재등록 화면으로 이동합니다."):
            return
        try:
            ts.delete_device_token(server_url=m.server_url, agent_id=m.agent_id)
        except Exception:  # noqa: S110
            pass
        self.ctrl.fire("reset_token", user_event="token 삭제됨")
        self.open_wizard()

    def on_minimize_to_tray(self) -> None:
        """[X] 닫기 → 트레이로 최소화 (실제 종료는 트레이 [종료])."""
        try:
            self.root.withdraw()
        except Exception:  # noqa: S110
            pass

    def on_quit(self) -> None:
        try:
            self.root.destroy()
        except Exception:  # noqa: S110
            pass

    # ── 회귀 호환 alias (직전 audit 가 검사) ────────────────

    def on_register(self) -> None:
        """구버전 호출 호환 — wizard 열기."""
        self.open_wizard()

    def on_connect(self) -> None:
        """구버전 호환 — 재연결."""
        self.on_reconnect()

    def on_diagnostics(self) -> None:
        """구버전 호환 — Diagnostics 탭으로 전환."""
        self.show_page(PAGE_DIAGNOSTICS)

    def _build_ui(self) -> None:
        """구버전 호환 alias."""
        return self._build_layout()

    # 직전 audit (AGENT_GUI_DESIGN_IMPLEMENTATION_01) 회귀 호환 alias
    def _build_page_dashboard(self, parent):
        return self._build_chat_tab(parent)

    def _build_page_registration(self, parent):
        return self._build_status_tab(parent)

    def _build_page_logs(self, parent):
        return self._build_diagnostics_tab(parent)

    def _build_page_settings(self, parent):
        return self._build_diagnostics_tab(parent)

    # ── 단축키 ────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        b = self.root.bind_all
        b("<Control-Key-1>", lambda e: self.show_page(PAGE_CHAT))
        b("<Control-Key-2>", lambda e: self.show_page(PAGE_STATUS))
        b("<Control-Key-3>", lambda e: self.show_page(PAGE_DIAGNOSTICS))
        # Ctrl+4 → AI 설정 modal (보정 — 이전엔 Settings 탭)
        b("<Control-Key-4>", lambda e: self.open_ai_settings())
        b("<Control-comma>", lambda e: self.open_ai_settings())
        b("<Control-r>", lambda e: self.on_reset())
        b("<Control-R>", lambda e: self.on_reset())
        b("<F1>", lambda e: self.show_page(PAGE_DIAGNOSTICS))
        b("<Escape>", lambda e: self.on_minimize_to_tray())

    # ── 폴링 ────────────────────────────────────────────

    def _poll_model(self) -> None:
        m = self.ctrl.model
        s = self.chat.state
        label = _state_label(m.state)
        if _HAS_CTK:
            self.var_statusbar.set(f"●  {label}  ·  agent {m.agent_id_masked or '미등록'}")
            # Status 탭 표시 갱신
            try:
                self.var_status_state.set(f"● {label}")
                self.lbl_status_state.configure(text_color=_state_color(m.state))
                self.var_status_aid.set(f"agent_id        {m.agent_id_masked or '—'}")
                self.var_status_srv.set(f"서버            {cd._strip_secrets_from_url(m.server_url)}")
                ws_url = cd.normalize_ws_url(m.server_url) if m.server_url else "—"
                self.var_status_ws.set(f"WS              {cd._strip_secrets_from_url(ws_url)}")
                self.var_status_hb.set(f"last heartbeat  {m.last_heartbeat_iso or '—'}")
                self.var_status_rc.set(f"reconnect       {m.reconnect_count}")
                self.var_status_ai.set(
                    f"AI mode         {cs.mode_label_kr(s.ai_mode.mode)} ({cs.ai_status_label_kr(s.ai_status)})"
                )
            except Exception:  # noqa: S110
                pass
            # Chat 탭 AI badge
            try:
                self.var_ai_badge.set(f"● AI {cs.ai_status_label_kr(s.ai_status)} · {cs.mode_label_kr(s.ai_mode.mode)}")
                self.lbl_ai_badge.configure(text_color=_ai_status_color(s.ai_status))
            except Exception:  # noqa: S110
                pass
        self.root.after(500, self._poll_model)

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(server_url: str = "https://haehan-ai.kr/orchestrator") -> int:
    ctrl = gs.GuiController(server_url=server_url)
    app = HaehanAgentGuiApp(controller=ctrl)
    app.run()
    return 0
