"""사용자 GUI — tkinter 창 (등록 / 연결 / 진단 / 재등록 / 종료).

UI 흐름:
  화면 1) 미등록 — registration_code 입력 + [등록]
  화면 2) 등록됨 — 상태/마지막 heartbeat 표시 + [연결] [재등록] [진단] [종료]

스레드 모델:
  - 메인 = tkinter mainloop
  - 백그라운드 1 = WS 연결 + heartbeat (websocket_client.run_forever)
  - 백그라운드 2 = register_with_code 호출 (응답 빠름)
  - 통신: GuiController (lock)
"""
from __future__ import annotations

import logging
import os
import platform
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import connection_diagnostics as cd
from . import gui_state as gs
from . import registration_client as rcli
from . import token_store as ts

logger = logging.getLogger("haehan_gui")


class HaehanAgentGuiApp:
    """tkinter 메인 윈도우."""

    def __init__(self, *, controller: gs.GuiController):
        self.ctrl = controller
        self.root = tk.Tk()
        self.root.title("Haehan AI Local Agent")
        self.root.geometry("520x420")
        self._ws_thread: threading.Thread | None = None
        self._ws_stop = threading.Event()
        self._build_ui()
        self._poll_model()

    # ── UI 구성 ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)

        # 서버 URL
        ttk.Label(frm, text="서버 URL").grid(row=0, column=0, sticky="w", **pad)
        self.var_server = tk.StringVar(value=self.ctrl.model.server_url)
        ent = ttk.Entry(frm, textvariable=self.var_server, width=50)
        ent.grid(row=0, column=1, sticky="we", **pad)

        # registration_code
        ttk.Label(frm, text="등록코드").grid(row=1, column=0, sticky="w", **pad)
        self.var_code = tk.StringVar(value="")
        self.code_entry = ttk.Entry(frm, textvariable=self.var_code,
                                     width=40, show="*")  # 마스킹 입력
        self.code_entry.grid(row=1, column=1, sticky="we", **pad)

        # 등록 버튼
        self.btn_register = ttk.Button(frm, text="등록 / 재등록",
                                         command=self.on_register)
        self.btn_register.grid(row=2, column=1, sticky="w", **pad)

        # 상태
        ttk.Separator(frm).grid(row=3, column=0, columnspan=2,
                                 sticky="we", pady=8)
        ttk.Label(frm, text="agent_id").grid(row=4, column=0, sticky="w", **pad)
        self.var_agent_id = tk.StringVar(value="-")
        ttk.Label(frm, textvariable=self.var_agent_id,
                   font=("Consolas", 10)).grid(
            row=4, column=1, sticky="w", **pad)

        ttk.Label(frm, text="상태").grid(row=5, column=0, sticky="w", **pad)
        self.var_state = tk.StringVar(value=gs.STATE_NOT_REGISTERED)
        self.lbl_state = ttk.Label(frm, textvariable=self.var_state,
                                     font=("", 11, "bold"))
        self.lbl_state.grid(row=5, column=1, sticky="w", **pad)

        ttk.Label(frm, text="마지막 heartbeat").grid(row=6, column=0,
                                                       sticky="w", **pad)
        self.var_hb = tk.StringVar(value="-")
        ttk.Label(frm, textvariable=self.var_hb).grid(
            row=6, column=1, sticky="w", **pad)

        ttk.Label(frm, text="마지막 오류").grid(row=7, column=0,
                                                  sticky="w", **pad)
        self.var_err = tk.StringVar(value="-")
        ttk.Label(frm, textvariable=self.var_err,
                   foreground="#c33").grid(
            row=7, column=1, sticky="w", **pad)

        # 안내
        self.var_guidance = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.var_guidance,
                   foreground="#444", wraplength=480).grid(
            row=8, column=0, columnspan=2, sticky="w", **pad)

        # 버튼 영역
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=9, column=0, columnspan=2, sticky="we", pady=8)
        self.btn_connect = ttk.Button(btn_frm, text="연결 시작",
                                        command=self.on_connect)
        self.btn_connect.pack(side="left", padx=4)
        self.btn_diag = ttk.Button(btn_frm, text="진단 보기",
                                     command=self.on_diagnostics)
        self.btn_diag.pack(side="left", padx=4)
        self.btn_reset = ttk.Button(btn_frm, text="재등록 (token 삭제)",
                                      command=self.on_reset)
        self.btn_reset.pack(side="left", padx=4)
        self.btn_quit = ttk.Button(btn_frm, text="종료",
                                     command=self.on_quit)
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
        self.btn_register.config(state="disabled")
        # 백그라운드에서 register 호출 — UI 응답성 유지
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
            device_token = ""  # 폐기
            code = ""           # 폐기
            self.ctrl.set_agent_id(agent_id)
            self.ctrl.fire("register_success",
                            user_event=f"등록 성공: {cd.mask_agent_id(agent_id)}")
        except rcli.RegistrationError as exc:
            self.ctrl.fire("register_failed", error_code="REG_CODE_INVALID",
                            user_event="등록 실패 (코드/서버 확인)")
        except ts.TokenStoreError:
            self.ctrl.fire("register_failed", error_code="TOKEN_NOT_STORED",
                            user_event="token 저장 실패")
        except Exception as exc:
            self.ctrl.fire("register_failed", error_code="SERVER_NOT_REACHABLE",
                            user_event="등록 실패")
        finally:
            # 입력창 비우기 (UI 스레드 안전을 위해 after)
            self.root.after(0, lambda: self.var_code.set(""))
            self.root.after(0, lambda: self.btn_register.config(state="normal"))

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
        self._ws_stop.clear()
        self._ws_thread = threading.Thread(
            target=self._ws_worker, args=(server, agent_id, token), daemon=True,
        )
        self._ws_thread.start()
        token = ""

    def _ws_worker(self, server: str, agent_id: str, token: str) -> None:
        # connection_diagnostics 기반 이벤트로 상태 머신 발화
        # 실제 WS 연결은 websocket_client.run_forever 사용
        try:
            self.ctrl.fire("connect_start")
            os.environ["HAEHAN_AGENT_WS_ENABLED"] = "true"
            os.environ["HAEHAN_AGENT_SERVER"] = server
            from . import websocket_client as ws
            # NOTE: ws.connect 는 blocking. 종료 시 thread 와 함께 죽음.
            ws.connect(agent_id=agent_id, device_token=token)
        except Exception as exc:
            self.ctrl.fire("connect_failed",
                            error_code="SERVER_NOT_REACHABLE")
        finally:
            token = ""
            self.ctrl.fire("ws_closed")

    def on_diagnostics(self) -> None:
        block = self.ctrl.render_user_block()
        win = tk.Toplevel(self.root)
        win.title("진단")
        win.geometry("520x360")
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
        self._ws_stop.set()
        self.root.destroy()

    # ── 폴링 ────────────────────────────────────────────────────

    def _poll_model(self) -> None:
        m = self.ctrl.model
        self.var_agent_id.set(m.agent_id_masked or "-")
        self.var_state.set(m.state)
        self.var_hb.set(m.last_heartbeat_iso or "-")
        self.var_err.set(m.last_error_code or "-")
        self.var_guidance.set(m.last_error_message_user
                               or m.last_user_event or "")
        # 상태별 색
        col = "#080"
        if m.state in (gs.STATE_AUTH_FAILED, gs.STATE_SERVER_UNREACHABLE):
            col = "#c33"
        elif m.state in (gs.STATE_RECONNECTING, gs.STATE_CONNECTING,
                          gs.STATE_AUTHENTICATING):
            col = "#a60"
        elif m.state == gs.STATE_NOT_REGISTERED:
            col = "#666"
        self.lbl_state.config(foreground=col)
        self.root.after(500, self._poll_model)

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(server_url: str = "https://haehan-ai.kr/orchestrator") -> int:
    """GUI 앱 진입점. controller + tkinter loop."""
    ctrl = gs.GuiController(server_url=server_url)
    app = HaehanAgentGuiApp(controller=ctrl)
    app.run()
    return 0
