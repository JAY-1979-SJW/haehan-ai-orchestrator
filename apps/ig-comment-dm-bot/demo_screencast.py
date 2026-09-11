"""검수 제출용 스크린캐스트 데모 — 실제 GUI를 자동 조작하며 화면에 표시한다."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

# 데모 실행 전 환경변수로 넘길 것: IG_DEMO_TOKEN=xxx python demo_screencast.py
# 토큰을 코드에 하드코딩하지 않는다(실수로 커밋/공유 시 노출 방지).
TOKEN = os.environ.get("IG_DEMO_TOKEN", "")


def run_demo():
    if not TOKEN:
        print("IG_DEMO_TOKEN 환경변수를 설정하세요. 예: IG_DEMO_TOKEN=xxx python demo_screencast.py")
        sys.exit(1)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(620, 700)
    win.show()

    def step1():
        win.token_input.setText(TOKEN)
        win._on_test_connection()

    def step2():
        win.keyword_input.setText("문의")
        win.match_type_combo.setCurrentText("부분포함")
        win._on_add_keyword()
        win.dm_message_input.setPlainText(
            "안녕하세요! 문의 주셔서 감사합니다. 반딧불 전파사입니다. 설치 공간 사진 보내주시면 확인 도와드릴게요 :)"
        )

    def step3():
        win.interval_spin.setValue(1)
        win._on_start()

    def step4():
        win.close()
        app.quit()

    QTimer.singleShot(1500, step1)
    QTimer.singleShot(4000, step2)
    QTimer.singleShot(6500, step3)
    QTimer.singleShot(18000, step4)

    app.exec()


if __name__ == "__main__":
    run_demo()
