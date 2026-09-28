"""고객용 초기 설정 화면 (Tkinter, 패키징 시 단일 exe에 포함 용이).

원본 회사 내부 자동화(scripts/naver/blog/*)는 CDP 영구 프로필에 이미
로그인돼있다는 전제였지만, 이 독립 앱은 고객마다 계정이 다르므로
최초 실행 시 아래 값을 직접 입력받아 config/settings.json + .env로 저장한다.

입력 항목:
  - 네이버 블로그 ID / 표시 이름(업종)
  - OpenAI API 키 (고객 본인 키 — 이 앱은 비용을 대신 부담하지 않는다)
  - 주제/키워드 목록(콤마 구분)
  - 발행 주기(일 단위)

로그인 자체(캡차 등)는 이 화면이 대신 못 한다 — "네이버 로그인 열기" 버튼으로
실제 브라우저 창을 띄우고, 고객이 직접 로그인하게 안내한다.
"""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path
from tkinter import LEFT, Button, Entry, Frame, Label, StringVar, Tk, X, messagebox

_APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_APP_ROOT))

from core.license_check import get_machine_id, verify_license  # noqa: E402

CONFIG_DIR = _APP_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
ACCOUNTS_PATH = CONFIG_DIR / "accounts.json"
LICENSE_PATH = CONFIG_DIR / "license.txt"
ENV_PATH = _APP_ROOT / ".env"


def _load_license() -> str:
    if LICENSE_PATH.exists():
        return LICENSE_PATH.read_text(encoding="utf-8").strip()
    return ""


def _save_license(key: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LICENSE_PATH.write_text(key.strip(), encoding="utf-8")


def ensure_licensed() -> bool:
    """저장된 라이선스가 유효하면 True. 없거나 무효면 입력 창을 띄우고 결과를 반환."""
    existing = _load_license()
    if existing and verify_license(existing):
        return True

    result = {"ok": False}
    win = Tk()
    win.title("라이선스 인증")
    win.geometry("480x260")

    mid = get_machine_id()
    Label(win, text="라이선스 인증이 필요합니다", font=("Malgun Gothic", 13, "bold")).pack(pady=(16, 6))
    Label(
        win,
        text="아래 PC 코드를 판매자에게 보내 라이선스 키를 발급받아 입력해주세요.",
        font=("Malgun Gothic", 9),
        fg="#555",
        wraplength=440,
    ).pack(pady=(0, 10))

    code_frame = Frame(win)
    code_frame.pack(fill=X, padx=16, pady=4)
    Label(code_frame, text="PC 코드", width=10, anchor="w").pack(side=LEFT)
    mid_var = StringVar(value=mid)
    mid_entry = Entry(code_frame, textvariable=mid_var, state="readonly")
    mid_entry.pack(side=LEFT, fill=X, expand=True)

    key_frame = Frame(win)
    key_frame.pack(fill=X, padx=16, pady=10)
    Label(key_frame, text="라이선스 키", width=10, anchor="w").pack(side=LEFT)
    key_var = StringVar()
    Entry(key_frame, textvariable=key_var).pack(side=LEFT, fill=X, expand=True)

    def on_activate():
        key = key_var.get().strip()
        if verify_license(key):
            _save_license(key)
            result["ok"] = True
            win.destroy()
        else:
            messagebox.showerror("인증 실패", "라이선스 키가 이 PC와 맞지 않습니다. 판매자에게 문의해주세요.")

    Button(win, text="인증", command=on_activate, bg="#03C75A", fg="white", width=16).pack(pady=8)
    win.mainloop()
    return result["ok"]


def _load_existing() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - GUI 설정 파일 로드 실패 시 빈 dict 반환 - 기본값으로 폴백, 데스크톱 설정 UI 초기화 로직일 뿐 위험 조작 없음
            return {}
    return {}


def _load_api_key() -> str:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def save_settings(blog_id: str, label: str, domain: str, api_key: str, topics: str, interval_days: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    settings = {
        "blog_id": blog_id.strip(),
        "label": label.strip(),
        "domain": domain.strip(),
        "topics": [t.strip() for t in topics.split(",") if t.strip()],
        "interval_days": int(interval_days) if interval_days.strip().isdigit() else 1,
    }
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

    accounts = {
        settings["blog_id"] or "example": {
            "blog_id": settings["blog_id"],
            "domain": settings["domain"],
            "label": settings["label"],
            "cache_file": f"data/blog_topic_cache_{settings['blog_id'] or 'example'}.json",
            "public_alias": settings["blog_id"],
        }
    }
    ACCOUNTS_PATH.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8")

    # API 키는 .env로 분리 저장 (settings.json에 평문 키 안 남기기)
    env_lines = []
    if ENV_PATH.exists():
        env_lines = [
            ln for ln in ENV_PATH.read_text(encoding="utf-8").splitlines() if not ln.startswith("OPENAI_API_KEY=")
        ]
    env_lines.append(f"OPENAI_API_KEY={api_key.strip()}")
    ENV_PATH.write_text("\n".join(env_lines) + "\n", encoding="utf-8")


def open_naver_login() -> None:
    webbrowser.open("https://nid.naver.com/nidlogin.login")
    messagebox.showinfo(
        "네이버 로그인",
        "브라우저에서 네이버 계정으로 로그인해주세요.\n"
        "로그인 완료 후 이 창으로 돌아와 '저장' 버튼을 눌러주세요.\n\n"
        "(캡차/2단계 인증은 자동화할 수 없어 직접 진행이 필요합니다.)",
    )


def main() -> None:
    if not ensure_licensed():
        return

    existing = _load_existing()
    existing_key = _load_api_key()

    root = Tk()
    root.title("네이버 블로그 AI 자동포스팅 — 초기 설정")
    root.geometry("520x420")

    def row(label_text: str, initial: str = "", show: str | None = None) -> StringVar:
        frame = Frame(root)
        frame.pack(fill=X, padx=16, pady=6)
        Label(frame, text=label_text, width=16, anchor="w").pack(side=LEFT)
        var = StringVar(value=initial)
        Entry(frame, textvariable=var, show=show).pack(side=LEFT, fill=X, expand=True)
        return var

    Label(root, text="네이버 블로그 AI 자동포스팅 설정", font=("Malgun Gothic", 14, "bold")).pack(pady=(16, 4))
    Label(
        root,
        text="아래 정보를 입력하면 자동으로 주제에 맞는 글을 작성해 발행합니다.",
        font=("Malgun Gothic", 9),
        fg="#555",
    ).pack(pady=(0, 12))

    blog_id_var = row("네이버 블로그ID", existing.get("blog_id", ""))
    label_var = row("표시 이름/업종", existing.get("label", ""))
    domain_var = row("업종 카테고리", existing.get("domain", ""))
    api_key_var = row("OpenAI API 키", existing_key, show="*")
    topics_var = row("주제(콤마구분)", ", ".join(existing.get("topics", [])))
    interval_var = row("발행 주기(일)", str(existing.get("interval_days", 1)))

    Button(root, text="네이버 로그인 열기", command=open_naver_login).pack(pady=(16, 4))

    def on_save():
        if not blog_id_var.get().strip():
            messagebox.showerror("입력 오류", "네이버 블로그ID를 입력해주세요.")
            return
        if not api_key_var.get().strip():
            messagebox.showerror("입력 오류", "OpenAI API 키를 입력해주세요.")
            return
        save_settings(
            blog_id_var.get(),
            label_var.get(),
            domain_var.get(),
            api_key_var.get(),
            topics_var.get(),
            interval_var.get(),
        )
        messagebox.showinfo("저장 완료", f"설정이 저장되었습니다.\n{SETTINGS_PATH}")

    Button(root, text="저장", command=on_save, bg="#03C75A", fg="white", width=20).pack(pady=8)

    root.mainloop()


if __name__ == "__main__":
    main()
