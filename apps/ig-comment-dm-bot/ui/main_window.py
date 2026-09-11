"""메인 윈도우 — 토큰/키워드/DM메시지 설정 + 실행/중지 + 상태 로그."""

from __future__ import annotations

from connectors.ig_api import IgApiError, verify_token
from core.keyword_matcher import KeywordRule
from core.poller import CommentPoller, PollerConfig
from core.settings_store import load_settings, save_settings
from core.token_store import load_token, save_token
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Instagram 댓글 → DM 자동발송")
        self.resize(560, 640)

        self.poller: CommentPoller | None = None
        self.rules: list[KeywordRule] = []

        self._build_ui()
        self._load_saved_token()
        self._load_saved_settings()

    # ---------- UI 구성 ----------

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        layout.addWidget(self._build_account_group())
        layout.addWidget(self._build_keyword_group())
        layout.addWidget(self._build_dm_group())
        layout.addWidget(self._build_control_group())

        layout.addWidget(QLabel("실행 로그"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        self.setCentralWidget(central)

    def _build_account_group(self) -> QGroupBox:
        group = QGroupBox("계정 설정")
        form = QFormLayout(group)

        self.ig_user_id_input = QLineEdit()
        self.ig_user_id_input.setPlaceholderText("Instagram-scoped 사용자 ID (연결 테스트 시 자동 확인 가능)")
        form.addRow("계정 ID", self.ig_user_id_input)

        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Meta for Developers 액세스 토큰")
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("액세스 토큰", self.token_input)

        test_btn = QPushButton("연결 테스트 + 저장")
        test_btn.clicked.connect(self._on_test_connection)
        form.addRow("", test_btn)

        return group

    def _build_keyword_group(self) -> QGroupBox:
        group = QGroupBox("키워드 설정")
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 문의, 가격")
        row.addWidget(self.keyword_input)

        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["부분포함", "정확일치"])
        row.addWidget(self.match_type_combo)

        add_btn = QPushButton("추가")
        add_btn.clicked.connect(self._on_add_keyword)
        row.addWidget(add_btn)
        layout.addLayout(row)

        self.keyword_list = QListWidget()
        layout.addWidget(self.keyword_list)

        remove_btn = QPushButton("선택 항목 삭제")
        remove_btn.clicked.connect(self._on_remove_keyword)
        layout.addWidget(remove_btn)

        return group

    def _build_dm_group(self) -> QGroupBox:
        group = QGroupBox("DM 메시지")
        layout = QVBoxLayout(group)
        self.dm_message_input = QPlainTextEdit()
        self.dm_message_input.setPlaceholderText("댓글 작성자에게 보낼 DM 내용을 입력하세요.")
        self.dm_message_input.setMaximumHeight(80)
        layout.addWidget(self.dm_message_input)
        return group

    def _build_control_group(self) -> QGroupBox:
        group = QGroupBox("실행 제어")
        form = QFormLayout(group)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(5)
        self.interval_spin.setSuffix(" 분")
        form.addRow("폴링 간격", self.interval_spin)

        self.media_limit_spin = QSpinBox()
        self.media_limit_spin.setRange(1, 50)
        self.media_limit_spin.setValue(5)
        form.addRow("확인할 최근 게시물 수", self.media_limit_spin)

        row = QHBoxLayout()
        self.status_label = QLabel("● 중지됨")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        row.addWidget(self.status_label)
        row.addStretch()

        self.start_btn = QPushButton("시작")
        self.start_btn.clicked.connect(self._on_start)
        row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("중지")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        row.addWidget(self.stop_btn)

        form.addRow("", row)
        return group

    # ---------- 동작 ----------

    def _load_saved_token(self) -> None:
        token = load_token()
        if token:
            self.token_input.setText(token)
            self._log("저장된 토큰을 불러왔습니다.")

    def _load_saved_settings(self) -> None:
        settings = load_settings()
        if not settings:
            return
        if settings.get("ig_user_id"):
            self.ig_user_id_input.setText(settings["ig_user_id"])
        for rule in settings.get("rules", []):
            display = "부분포함" if rule["match_type"] == "contains" else "정확일치"
            self.rules.append(KeywordRule(keyword=rule["keyword"], match_type=rule["match_type"]))
            self.keyword_list.addItem(f"[{display}] {rule['keyword']}")
        if settings.get("dm_message"):
            self.dm_message_input.setPlainText(settings["dm_message"])
        if settings.get("interval_minutes"):
            self.interval_spin.setValue(settings["interval_minutes"])
        if settings.get("media_limit"):
            self.media_limit_spin.setValue(settings["media_limit"])
        self._log("저장된 설정을 불러왔습니다.")

    def _save_current_settings(self) -> None:
        save_settings(
            ig_user_id=self.ig_user_id_input.text().strip(),
            rules=list(self.rules),
            dm_message=self.dm_message_input.toPlainText().strip(),
            interval_minutes=self.interval_spin.value(),
            media_limit=self.media_limit_spin.value(),
        )

    def _on_test_connection(self) -> None:
        ig_user_id = self.ig_user_id_input.text().strip() or "me"
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "입력 필요", "액세스 토큰을 입력하세요.")
            return
        try:
            info = verify_token(ig_user_id, token)
            save_token(token)
            self.ig_user_id_input.setText(info["id"])
            self._log(f"연결 성공: @{info.get('username', '?')} (ID: {info['id']}) — 토큰 저장 완료")
            QMessageBox.information(self, "성공", f"연결 성공: @{info.get('username', '?')}")
        except IgApiError as e:
            QMessageBox.critical(self, "연결 실패", str(e))

    def _on_add_keyword(self) -> None:
        keyword = self.keyword_input.text().strip()
        if not keyword:
            return
        match_type = "contains" if self.match_type_combo.currentText() == "부분포함" else "exact"
        rule = KeywordRule(keyword=keyword, match_type=match_type)
        self.rules.append(rule)
        self.keyword_list.addItem(f"[{self.match_type_combo.currentText()}] {keyword}")
        self.keyword_input.clear()
        self._save_current_settings()

    def _on_remove_keyword(self) -> None:
        row = self.keyword_list.currentRow()
        if row < 0:
            return
        self.keyword_list.takeItem(row)
        del self.rules[row]
        self._save_current_settings()

    def _on_start(self) -> None:
        ig_user_id = self.ig_user_id_input.text().strip()
        token = self.token_input.text().strip()
        dm_message = self.dm_message_input.toPlainText().strip()

        if not ig_user_id or not token:
            QMessageBox.warning(self, "입력 필요", "계정 ID와 액세스 토큰을 입력하세요.")
            return
        if not self.rules:
            QMessageBox.warning(self, "입력 필요", "키워드를 하나 이상 등록하세요.")
            return
        if not dm_message:
            QMessageBox.warning(self, "입력 필요", "DM 메시지를 입력하세요.")
            return

        config = PollerConfig(
            ig_user_id=ig_user_id,
            token=token,
            interval_seconds=self.interval_spin.value() * 60,
            media_limit=self.media_limit_spin.value(),
            rules=list(self.rules),
            dm_message=dm_message,
        )
        self._save_current_settings()

        self.poller = CommentPoller(config)
        self.poller.log_message.connect(self._log)
        self.poller.dm_sent.connect(self._on_dm_sent)
        self.poller.error_occurred.connect(self._on_error)
        self.poller.start()

        self.status_label.setText("● 실행 중")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._log("폴링 시작됨. 이 프로그램이 켜져 있는 동안만 작동합니다.")

    def _on_stop(self) -> None:
        if self.poller:
            self.poller.stop()
            self.poller.wait()
            self.poller = None

        self.status_label.setText("● 중지됨")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._log("폴링 중지됨.")

    def _on_dm_sent(self, username: str, comment_text: str) -> None:
        self._log(f"DM 발송 완료 → @{username} (댓글: {comment_text[:30]})")

    def _on_error(self, message: str) -> None:
        self._log(f"오류: {message}")

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def closeEvent(self, event) -> None:
        if self.poller:
            self.poller.stop()
            self.poller.wait()
        event.accept()
