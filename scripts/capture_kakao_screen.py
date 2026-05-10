"""카카오워크/카카오톡 화면 캡처 — 다운로드 버튼 위치 탐지용.

실행 전: 카카오워크 또는 카카오톡 채팅방(파일/사진 있는 방)을 열어두세요.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pyautogui
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "reports" / "local_agent"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def capture_app_window(app_name: str) -> Path | None:
    """앱 창 영역만 캡처."""
    import psutil
    import uiautomation as auto

    pids = {p.info["pid"] for p in psutil.process_iter(["pid", "name"])
            if app_name.lower() in (p.info.get("name") or "").lower()}
    if not pids:
        print(f"  {app_name} 프로세스 없음")
        return None

    desktop = auto.GetRootControl()
    for w in desktop.GetChildren():
        try:
            if w.ProcessId in pids and (w.Name or "").strip():
                r = w.BoundingRectangle
                print(f"  창: {w.Name!r} rect=({r.left},{r.top},{r.right},{r.bottom})")
                # 창 활성화
                try:
                    w.SetActive()
                except Exception:
                    pass
                import time; time.sleep(0.5)
                # 캡처
                img = pyautogui.screenshot(region=(r.left, r.top,
                                                    r.right - r.left,
                                                    r.bottom - r.top))
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                out = OUT_DIR / f"screen_{app_name}_{ts}.png"
                img.save(out)
                print(f"  저장: {out}")
                return out
        except Exception as e:
            print(f"  오류: {e}")
    return None


def main():
    print("=" * 60)
    print("  카카오 화면 캡처")
    print("=" * 60)

    print("\n[카카오워크]")
    capture_app_window("Kakaowork")

    print("\n[카카오톡]")
    capture_app_window("KakaoTalk")

    print("\n전체 화면 캡처")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    full = OUT_DIR / f"screen_full_{ts}.png"
    pyautogui.screenshot().save(full)
    print(f"  저장: {full}")


if __name__ == "__main__":
    main()
