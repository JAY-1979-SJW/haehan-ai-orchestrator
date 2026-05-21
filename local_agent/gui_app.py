"""사용자 GUI — customtkinter 기반 모던 디자인.

디자인:
  - dark mode 기본 (light 토글 가능)
  - 카드 레이아웃 (서버/상태/액션 3섹션)
  - 상태 pill (둥근 모서리 + 색)
  - 큰 입력창 + show='*' registration_code 마스킹
  - Segoe UI / Pretendard 계열 폰트

fallback:
  customtkinter 미설치 시 tk + ttk 기본 위젯으로 fallback.

스레드 모델:
  - 메인 = tkinter mainloop
  - 백그라운드 = register / WS 연결 (GuiController 공유)
"""
from __future__ import annotations

import logging
import os
import platform
import socket
import threading
import tkinter as tk
from tkinter import messagebox

from . import connection_diagnostics as cd
from . import gui_state as gs
from . import registration_client as rcli
from . import token_store as ts

logger = logging.getLogger("haehan_gui")


# ── customtkinter optional import ─────────────────────────────────

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
    # 배경
    "bg":        "#0F1115",
    "card":      "#1A1D24",
    "card_alt":  "#22262F",
    "border":    "#2A2F39",
    # 텍스트
    "fg":        "#E8ECF1",
    "fg_dim":    "#8A93A6",
    "fg_muted":  "#5B6478",
    # 강조
    "accent":    "#6366F1",   # indigo 500
    "accent_hi": "#818CF8",
    # 상태
    "ok":        "#10B981",   # emerald 500
    "warn":      "#F59E0B",   # amber 500
    "err":       "#EF4444",   # red 500
    "neutral":   "#64748B",   # slate 500
}


def _state_color(state: str) -> str:
    if state in (gs.STATE_HEARTBEAT_OK, gs.STATE_CONNECTED):
        return COLOR["ok"]
    if state in (gs.STATE_AUTH_FAILED, gs.STATE_SERVER_UNREACHABLE):
        return COLOR["err"]
    if state in (gs.STATE_RECONNECTING, gs.STATE_CONNECTING,
                  gs.STATE_AUTHENTICATING):
        return COLOR["warn"]
    return COLOR["neutral"]


def _state_label_kr(state: str) -> str:
    return {
        gs.STATE_NOT_REGISTERED: "미등록",
        gs.STATE_CONNECTING: "연결 중",
        gs.STATE_AUTHENTICATING: "인증 중",
        gs.STATE_CONNECTED: "연결됨",
        gs.STATE_HEARTBEAT_OK: "정상 (heartbeat)",
        gs.STATE_DISCONNECTED: "끊김",
        gs.STATE_AUTH_FAILED: "인증 실패",
        gs.STATE_RECONNECTING: "재연결 중",
        gs.STATE_SERVER_UNREACHABLE: "서버 접속 실패",
    }.get(state, state)


# ── 메인 앱 ────────────────────────────────────────────────────────


class HaehanAgentGuiApp:
    """customtkinter 기반 사용자 윈도우. ctk 미설치 시 tk fallback."""

    def __init__(self, *, controller: gs.GuiController):
        self.ctrl = controller
        self._ws_thread: threading.Thread | None = None
        if _HAS_CTK:
            _ctk.set_appearance_mode("dark")
            _ctk.set_default_color_theme("blue")
            self.root = _ctk.CTk()
        else:
            self.root = tk.Tk()
            self.root.configure(bg=COLOR["bg"])

        self.root.title("Haehan AI Local Agent")
        self.root.geometry("680x620")
        self.root.minsize(560, 540)
        self._build_ui()
        self._poll_model()

    # ── UI 구성 ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        if _HAS_CTK:
            self._build_ui_ctk()
        else:
            self._build_ui_fallback()

    def _build_ui_ctk(self) -> None:
        ctk = _ctk
        # 헤더
        header = ctk.CTkFrame(self.root, height=72, corner_radius=0,
                               fg_color=COLOR["card"])
        header.pack(fill="x", side="top")
        ctk.CTkLabel(header, text="Haehan AI", text_color=COLOR["accent_hi"],
                      font=("Segoe UI", 20, "bold")).place(x=24, y=18)
        ctk.CTkLabel(header, text="Local Agent", text_color=COLOR["fg_dim"],
                      font=("Segoe UI", 13)).place(x=24, y=44)
        # 상태 pill (오른쪽)
        self.pill = ctk.CTkLabel(header, text="●  미등록",
                                   text_color="white",
                                   fg_color=COLOR["neutral"],
                                   corner_radius=14,
                                   width=140, height=28,
                                   font=("Segoe UI", 12, "bold"))
        self.pill.place(relx=1.0, x=-24, y=22, anchor="ne")

        # 본문 컨테이너
        main = ctk.CTkFrame(self.root, fg_color=COLOR["bg"],
                              corner_radius=0)
        main.pack(fill="both", expand=True, padx=20, pady=20)

        # ── 카드 1: 서버 / 등록 ──
        card1 = ctk.CTkFrame(main, fg_color=COLOR["card"],
                              corner_radius=14, border_width=1,
                              border_color=COLOR["border"])
        card1.pack(fill="x", pady=(0, 14))
        self._section_title(card1, "서버 · 등록", 12, 12)

        ctk.CTkLabel(card1, text="서버 URL",
                      text_color=COLOR["fg_dim"],
                      font=("Segoe UI", 11)).place(x=20, y=46)
        self.var_server = tk.StringVar(value=self.ctrl.model.server_url)
        self.ent_server = ctk.CTkEntry(card1, textvariable=self.var_server,
                                         width=400, height=34,
                                         fg_color=COLOR["card_alt"],
                                         border_color=COLOR["border"],
                                         text_color=COLOR["fg"])
        self.ent_server.place(x=20, y=64)

        ctk.CTkLabel(card1, text="등록코드",
                      text_color=COLOR["fg_dim"],
                      font=("Segoe UI", 11)).place(x=20, y=112)
        self.var_code = tk.StringVar(value="")
        self.ent_code = ctk.CTkEntry(card1, textvariable=self.var_code,
                                       width=400, height=34, show="●",
                                       fg_color=COLOR["card_alt"],
                                       border_color=COLOR["border"],
                                       text_color=COLOR["fg"],
                                       placeholder_text="관리자에게 받은 1회용 코드")
        self.ent_code.place(x=20, y=130)

        self.btn_register = ctk.CTkButton(
            card1, text="등록 / 재등록", command=self.on_register,
            width=140, height=34, corner_radius=8,
            fg_color=COLOR["accent"], hover_color=COLOR["accent_hi"],
            font=("Segoe UI", 12, "bold"),
        )
        self.btn_register.place(x=440, y=130)

        card1.configure(height=190)
        card1.pack_propagate(False)

        # ── 카드 2: 연결 상태 ──
        card2 = ctk.CTkFrame(main, fg_color=COLOR["card"],
                              corner_radius=14, border_width=1,
                              border_color=COLOR["border"])
        card2.pack(fill="x", pady=(0, 14))
        self._section_title(card2, "연결 상태", 12, 12)

        # agent_id
        ctk.CTkLabel(card2, text="agent_id",
                      text_color=COLOR["fg_dim"],
                      font=("Segoe UI", 11)).place(x=20, y=46)
        self.var_agent_id = tk.StringVar(value="—")
        self.lbl_agent_id = ctk.CTkLabel(card2, textvariable=self.var_agent_id,
                                           text_color=COLOR["fg"],
                                           font=("Consolas", 13, "bold"))
        self.lbl_agent_id.place(x=110, y=44)

        # last heartbeat
        ctk.CTkLabel(card2, text="마지막 heartbeat",
                      text_color=COLOR["fg_dim"],
                      font=("Segoe UI", 11)).place(x=20, y=74)
        self.var_hb = tk.StringVar(value="—")
        ctk.CTkLabel(card2, textvariable=self.var_hb,
                      text_color=COLOR["fg"],
                      font=("Segoe UI", 11)).place(x=160, y=74)

        # last error
        ctk.CTkLabel(card2, text="마지막 오류",
                      text_color=COLOR["fg_dim"],
                      font=("Segoe UI", 11)).place(x=20, y=100)
        self.var_err = tk.StringVar(value="—")
        ctk.CTkLabel(card2, textvariable=self.var_err,
                      text_color=COLOR["err"],
                      font=("Segoe UI", 11)).place(x=160, y=100)

        # guidance
        self.var_guidance = tk.StringVar(value="")
        self.lbl_guidance = ctk.CTkLabel(
            card2, textvariable=self.var_guidance,
            text_color=COLOR["fg_dim"],
            wraplength=580, justify="left", anchor="w",
            font=("Segoe UI", 11),
        )
        self.lbl_guidance.place(x=20, y=128)

        card2.configure(height=176)
        card2.pack_propagate(False)

        # ── 카드 3: 액션 버튼 ──
        card3 = ctk.CTkFrame(main, fg_color=COLOR["card"],
                              corner_radius=14, border_width=1,
                              border_color=COLOR["border"])
        card3.pack(fill="x")
        self._section_title(card3, "액션", 12, 12)

        self.btn_connect = ctk.CTkButton(
            card3, text="연결 시작", command=self.on_connect,
            width=130, height=36, corner_radius=8,
            fg_color=COLOR["ok"], hover_color="#0EA372",
            font=("Segoe UI", 12, "bold"),
        )
        self.btn_connect.place(x=20, y=46)

        self.btn_diag = ctk.CTkButton(
            card3, text="진단 보기", command=self.on_diagnostics,
            width=130, height=36, corner_radius=8,
            fg_color=COLOR["card_alt"], hover_color=COLOR["border"],
            text_color=COLOR["fg"],
            font=("Segoe UI", 12),
        )
        self.btn_diag.place(x=160, y=46)

        self.btn_reset = ctk.CTkButton(
            card3, text="재등록 (token 삭제)", command=self.on_reset,
            width=170, height=36, corner_radius=8,
            fg_color=COLOR["card_alt"], hover_color=COLOR["border"],
            text_color=COLOR["warn"],
            font=("Segoe UI", 12),
        )
        self.btn_reset.place(x=300, y=46)

        self.btn_quit = ctk.CTkButton(
            card3, text="종료", command=self.on_quit,
            width=80, height=36, corner_radius=8,
            fg_color="transparent", border_width=1,
            border_color=COLOR["border"], hover_color=COLOR["border"],
            text_color=COLOR["fg_dim"],
            font=("Segoe UI", 12),
        )
        self.btn_quit.place(relx=1.0, x=-100, y=46, anchor="nw")

        card3.configure(height=110)
        card3.pack_propagate(False)

        # 푸터
        footer = ctk.CTkLabel(
            self.root,
            text="• device_token / registration_code 원문은 화면·로그·보고서에 노출되지 않습니다.",
            text_color=COLOR["fg_muted"], font=("Segoe UI", 10),
        )
        footer.pack(side="bottom", pady=8)

    def _section_title(self, parent, text: str, x: int, y: int) -> None:
        ctk = _ctk
        if not _HAS_CTK:
            return
        ctk.CTkLabel(parent, text=text, text_color=COLOR["accent_hi"],
                      font=("Segoe UI", 13, "bold")).place(x=x, y=y)

    def _build_ui_fallback(self) -> None:
        """customtkinter 미설치 시 기본 tk/ttk 위젯."""
        from tkinter import ttk
        pad = {"padx": 8, "pady": 6}
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Haehan AI Local Agent",
                   font=("", 13, "bold")).grid(row=0, column=0, columnspan=2,
                                                 sticky="w", **pad)
        ttk.Label(frm, text="서버 URL").grid(row=1, column=0, sticky="w", **pad)
        self.var_server = tk.StringVar(value=self.ctrl.model.server_url)
        ttk.Entry(frm, textvariable=self.var_server, width=50).grid(
            row=1, column=1, sticky="we", **pad)
        ttk.Label(frm, text="등록코드").grid(row=2, column=0, sticky="w", **pad)
        self.var_code = tk.StringVar(value="")
        ttk.Entry(frm, textvariable=self.var_code, width=40,
                   show="*").grid(row=2, column=1, sticky="we", **pad)
        self.btn_register = ttk.Button(frm, text="등록 / 재등록",
                                         command=self.on_register)
        self.btn_register.grid(row=3, column=1, sticky="w", **pad)
        self.var_agent_id = tk.StringVar(value="—")
        ttk.Label(frm, text="agent_id").grid(row=4, column=0, sticky="w", **pad)
        ttk.Label(frm, textvariable=self.var_agent_id).grid(
            row=4, column=1, sticky="w", **pad)
        self.var_state_pill_text = tk.StringVar(value="미등록")
        ttk.Label(frm, text="상태").grid(row=5, column=0, sticky="w", **pad)
        self.lbl_state = ttk.Label(frm, textvariable=self.var_state_pill_text,
                                     font=("", 11, "bold"))
        self.lbl_state.grid(row=5, column=1, sticky="w", **pad)
        self.var_hb = tk.StringVar(value="—")
        ttk.Label(frm, text="last heartbeat").grid(row=6, column=0,
                                                     sticky="w", **pad)
        ttk.Label(frm, textvariable=self.var_hb).grid(row=6, column=1,
                                                        sticky="w", **pad)
        self.var_err = tk.StringVar(value="—")
        ttk.Label(frm, text="last error").grid(row=7, column=0,
                                                 sticky="w", **pad)
        ttk.Label(frm, textvariable=self.var_err,
                   foreground="#c33").grid(row=7, column=1, sticky="w", **pad)
        self.var_guidance = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.var_guidance,
                   wraplength=480).grid(row=8, column=0, columnspan=2,
                                          sticky="w", **pad)
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=9, column=0, columnspan=2, sticky="we", pady=8)
        self.btn_connect = ttk.Button(btn_frm, text="연결 시작",
                                        command=self.on_connect)
        self.btn_connect.pack(side="left", padx=4)
        self.btn_diag = ttk.Button(btn_frm, text="진단 보기",
                                     command=self.on_diagnostics)
        self.btn_diag.pack(side="left", padx=4)
        self.btn_reset = ttk.Button(btn_frm, text="재등록",
                                      command=self.on_reset)
        self.btn_reset.pack(side="left", padx=4)
        self.btn_quit = ttk.Button(btn_frm, text="종료", command=self.on_quit)
        self.btn_quit.pack(side="right", padx=4)
        frm.columnconfigure(1, weight=1)

    # ── 이벤트 핸들러 ──────────────────────────────────────────

    def on_register(self) -> None:
        server = (self.var_server.get() or "").strip()
        code = (self.var_code.get() or "").strip()
        if not code:
            messagebox.showwarning("등록코드 필요", "등록코드를 입력하세요.")
            return
        self.ctrl.set_server_url(server)
        self.btn_register.configure(state="disabled")
        threading.Thread(target=self._register_worker,
                          args=(server, code), daemon=True).start()

    def _register_worker(self, server: str, code: str) -> None:
        try:
            self.ctrl.fire("register_started")
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
                            user_event=f"등록 성공: {cd.mask_agent_id(agent_id)}")
        except rcli.RegistrationError:
            self.ctrl.fire("register_failed", error_code="REG_CODE_INVALID",
                            user_event="등록 실패 (코드/서버 확인)")
        except ts.TokenStoreError:
            self.ctrl.fire("register_failed", error_code="TOKEN_NOT_STORED",
                            user_event="token 저장 실패")
        except Exception:
            self.ctrl.fire("register_failed",
                            error_code="SERVER_NOT_REACHABLE",
                            user_event="등록 실패")
        finally:
            self.root.after(0, lambda: self.var_code.set(""))
            self.root.after(0,
                             lambda: self.btn_register.configure(state="normal"))

    def on_connect(self) -> None:
        agent_id = self.ctrl.model.agent_id
        server = self.ctrl.model.server_url
        if not agent_id:
            messagebox.showinfo("등록 필요", "먼저 등록하세요.")
            return
        if self._ws_thread and self._ws_thread.is_alive():
            messagebox.showinfo("이미 연결됨", "이미 WebSocket 연결 중입니다.")
            return
        token = ts.load_device_token(server_url=server, agent_id=agent_id)
        if not token:
            self.ctrl.fire("reset_token", error_code="TOKEN_NOT_STORED")
            messagebox.showwarning("재등록 필요",
                                    "device_token 이 없습니다. 재등록하세요.")
            return
        self._ws_thread = threading.Thread(
            target=self._ws_worker, args=(server, agent_id, token), daemon=True,
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
            self.ctrl.fire("connect_failed",
                            error_code="SERVER_NOT_REACHABLE")
        finally:
            token = ""
            self.ctrl.fire("ws_closed")

    def on_diagnostics(self) -> None:
        block = self.ctrl.render_user_block()
        if _HAS_CTK:
            ctk = _ctk
            win = ctk.CTkToplevel(self.root)
            win.title("진단")
            win.geometry("620x440")
            win.configure(fg_color=COLOR["bg"])
            tb = ctk.CTkTextbox(win, wrap="word",
                                  fg_color=COLOR["card"],
                                  text_color=COLOR["fg"],
                                  border_width=1,
                                  border_color=COLOR["border"],
                                  font=("Consolas", 11))
            tb.insert("1.0", block)
            tb.configure(state="disabled")
            tb.pack(fill="both", expand=True, padx=14, pady=(14, 8))
            ctk.CTkButton(win, text="닫기", command=win.destroy,
                            width=100, height=32, corner_radius=8,
                            fg_color=COLOR["accent"],
                            hover_color=COLOR["accent_hi"]).pack(pady=10)
        else:
            from tkinter import ttk
            win = tk.Toplevel(self.root)
            win.title("진단")
            win.geometry("560x400")
            txt = tk.Text(win, wrap="word", font=("Consolas", 10))
            txt.insert("1.0", block)
            txt.config(state="disabled")
            txt.pack(fill="both", expand=True, padx=8, pady=8)
            ttk.Button(win, text="닫기", command=win.destroy).pack(pady=6)

    def on_reset(self) -> None:
        m = self.ctrl.model
        if not m.agent_id:
            messagebox.showinfo("정보", "저장된 token 이 없습니다.")
            return
        if not messagebox.askyesno("재등록 확인",
                                     "저장된 token 을 삭제하고 재등록 화면으로 이동합니다."):
            return
        try:
            ts.delete_device_token(server_url=m.server_url,
                                    agent_id=m.agent_id)
        except Exception:
            pass
        self.ctrl.fire("reset_token", user_event="token 삭제됨")

    def on_quit(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass

    # ── 폴링 ───────────────────────────────────────────────────

    def _poll_model(self) -> None:
        m = self.ctrl.model
        self.var_agent_id.set(m.agent_id_masked or "—")
        self.var_hb.set(m.last_heartbeat_iso or "—")
        self.var_err.set(m.last_error_code or "—")
        self.var_guidance.set(m.last_error_message_user
                               or m.last_user_event or "")
        # pill 색/텍스트 (ctk) 또는 lbl_state (fallback)
        if _HAS_CTK:
            self.pill.configure(
                text=f"●  {_state_label_kr(m.state)}",
                fg_color=_state_color(m.state),
            )
        else:
            self.var_state_pill_text.set(_state_label_kr(m.state))
            try:
                self.lbl_state.configure(foreground=_state_color(m.state))
            except Exception:
                pass
        self.root.after(500, self._poll_model)

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(server_url: str = "https://haehan-ai.kr/orchestrator") -> int:
    ctrl = gs.GuiController(server_url=server_url)
    app = HaehanAgentGuiApp(controller=ctrl)
    app.run()
    return 0
