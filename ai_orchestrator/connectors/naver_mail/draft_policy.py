"""L2 Policy/Gate — 메일 AI 초안 정책(순수 판정). 저장·전송·네트워크 부작용 없음.

기준서: docs/specs/2026-10-02_mailbox_ai_window.md §3
AI(에이전트)는 초안만 만들 수 있고, 보내기는 사람이 카드 버튼으로 한다. 이 모듈은 그 사이의 판정만 한다:
- 초안 생성 한도(대기 초안 수, 수신자 수)
- 보내기 한도(유효 기간, 하루 발송 상한)와 초안 상태 전이 규칙
- AI 가 준 첨부 파일 경로의 안전 검사(허용 폴더 안의 일반 파일만, 비밀·앱 내부 파일 거부)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ai_orchestrator.connectors.naver_mail.draft_states import CANCELLED, DRAFT_TTL_DAYS, EXPIRED, FAILED, OPEN_STATUSES, PENDING, SENDING, SENT, STATUSES, UNKNOWN, can_transition  # noqa: F401  (정책을 거쳐 쓰던 기존 이름을 그대로 다시 내보낸다)

MAX_PENDING_DRAFTS = 50
MAX_RECIPIENTS = 20
DEFAULT_DAILY_SEND_CAP = 100
INSTRUCTIONS_MAX_CHARS = 4000
MAX_ATTACH_FILES = 10
MAX_ATTACH_BYTES = 20 * 1024 * 1024

@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


def daily_cap() -> int:
    """하루 발송 상한 — 환경변수 HAEHAN_MAIL_DAILY_CAP 로 바꿀 수 있다(1~1000)."""
    try:
        value = int(os.environ.get("HAEHAN_MAIL_DAILY_CAP", DEFAULT_DAILY_SEND_CAP))
    except ValueError:
        return DEFAULT_DAILY_SEND_CAP
    return max(1, min(value, 1000))


def check_create(*, pending_count: int, recipient_count: int, attachment_count: int = 0) -> Decision:
    if recipient_count < 1:
        return Decision(False, "받는 사람이 없습니다")
    if recipient_count > MAX_RECIPIENTS:
        return Decision(False, f"받는 사람은 참조·숨은참조를 합쳐 {MAX_RECIPIENTS}명 이하여야 합니다")
    if attachment_count > MAX_ATTACH_FILES:
        return Decision(False, f"첨부는 최대 {MAX_ATTACH_FILES}개입니다")
    if pending_count >= MAX_PENDING_DRAFTS:
        return Decision(
            False, f"승인 대기 초안이 너무 많습니다(최대 {MAX_PENDING_DRAFTS}개). 이전 초안을 보내거나 취소하세요"
        )
    return Decision(True)


def check_send(*, status: str, expired: bool, sent_today: int, cap: int | None = None) -> Decision:
    """사람이 '승인하고 보내기'를 눌렀을 때의 판정."""
    if status not in OPEN_STATUSES:
        reasons = {
            SENDING: "지금 전송 중입니다",
            SENT: "이미 보낸 메일입니다",
            UNKNOWN: "이전 전송 결과가 불확실합니다 — 보낸편지함에서 확인한 뒤 필요하면 새 초안을 만드세요(중복 발송 방지)",
            CANCELLED: "취소된 초안입니다",
            EXPIRED: "만료된 초안입니다",
        }
        return Decision(False, reasons.get(status, f"보낼 수 없는 상태입니다({status})"))
    if expired:
        return Decision(False, f"초안이 {DRAFT_TTL_DAYS}일이 지나 만료되었습니다")
    limit = cap if cap is not None else daily_cap()
    if sent_today >= limit:
        return Decision(False, f"오늘 발송 상한({limit}통)에 도달했습니다")
    return Decision(True)


# ── 첨부 파일 경로 안전 ─────────────────────────────────────────────────

SECRET_SUFFIXES = frozenset(
    {".pem", ".key", ".pfx", ".p12", ".ppk", ".jks", ".keystore", ".kdbx", ".db", ".sqlite", ".sqlite3", ".env"}
)
SECRET_NAMES = frozenset(
    {
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "credentials",
        "credentials.json",
        "secrets.json",
        "token.json",
        "client_secret.json",
        "authorized_user.json",
    }
)
SECRET_WORDS = ("secret", "password", "passwd", "credential", "private_key", "apikey", "api_key", "비밀번호")
DENIED_PARTS = frozenset({".git", ".ssh", ".aws", ".gnupg", "appdata", "node_modules", "secrets"})


class PathRejected(ValueError):
    """AI 가 준 첨부 경로를 거부한 이유(사용자에게 그대로 보일 수 있는 문구)."""


def allowed_attachment_dirs(home: Path | None = None, extra_env: str | None = None) -> list[Path]:
    """첨부로 쓸 수 있는 폴더: 사용자 문서·다운로드·바탕화면(+OneDrive 아래 같은 이름) + 환경변수 HAEHAN_MAIL_ATTACH_DIRS."""
    home = home or Path.home()
    names = ("Documents", "Downloads", "Desktop", "문서", "다운로드", "바탕 화면")
    roots = [home, *sorted(home.glob("OneDrive*"))]
    dirs = [r / n for r in roots for n in names]
    raw = os.environ.get("HAEHAN_MAIL_ATTACH_DIRS", "") if extra_env is None else extra_env
    dirs += [Path(p) for p in raw.split(os.pathsep) if p.strip()]
    return [d for d in dirs if d.is_dir()]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_file(raw: str) -> Path:
    if not raw or "\x00" in raw:
        raise PathRejected("첨부 파일 경로가 비어 있거나 올바르지 않습니다")
    given = Path(raw)
    if not given.is_absolute():
        raise PathRejected(f"첨부 파일은 전체 경로로 지정해야 합니다: {raw}")
    try:
        real = given.resolve(strict=True)  # 심볼릭 링크를 푼 실제 경로로 이후 검사를 한다
    except (OSError, RuntimeError) as e:
        raise PathRejected(f"첨부 파일을 찾을 수 없습니다: {raw}") from e
    if not real.is_file():
        raise PathRejected(f"파일이 아닙니다: {raw}")
    return real


def _check_location(real: Path, allowed_dirs: list[Path], deny_roots: list[Path]) -> None:
    roots = [d.resolve() for d in allowed_dirs if d.exists()]
    root = next((r for r in roots if _inside(real, r)), None)
    if root is None:
        raise PathRejected(
            "허용된 폴더(문서·다운로드·바탕화면) 밖의 파일은 첨부할 수 없습니다. 필요하면 환경변수 HAEHAN_MAIL_ATTACH_DIRS 로 폴더를 추가하세요"
        )
    if any(deny.exists() and _inside(real, deny.resolve()) for deny in deny_roots):
        raise PathRejected("앱 내부 폴더의 파일은 첨부할 수 없습니다")
    # 허용 폴더 '안쪽' 경로만 본다 — 허용 폴더 자체가 어디에 있든(예: 사용자 폴더 아래 AppData) 안의 파일 판정에는 영향 없다
    inner = [p.lower() for p in real.relative_to(root).parts]
    if set(inner) & DENIED_PARTS or any(p.startswith("_backup") for p in inner):
        raise PathRejected("민감할 수 있는 폴더(.git·.ssh·AppData 등)의 파일은 첨부할 수 없습니다")


def _check_secret_name(real: Path) -> None:
    name = real.name.lower()
    if (
        name in SECRET_NAMES
        or name.startswith(".env")
        or real.suffix.lower() in SECRET_SUFFIXES
        or any(w in name for w in SECRET_WORDS)
    ):
        raise PathRejected(f"비밀번호·키·인증 정보로 보이는 파일은 첨부할 수 없습니다: {real.name}")


def _check_size(real: Path) -> None:
    try:
        size = real.stat().st_size
    except OSError as e:
        raise PathRejected(f"파일 정보를 읽을 수 없습니다: {real.name}") from e
    if size == 0:
        raise PathRejected(f"빈 파일입니다: {real.name}")
    if size > MAX_ATTACH_BYTES:
        raise PathRejected(f"파일 하나는 {MAX_ATTACH_BYTES // 1024 // 1024}MB 이하여야 합니다: {real.name}")


def validate_attachment_path(raw: str, *, allowed_dirs: list[Path], deny_roots: list[Path] | None = None) -> Path:
    """AI 가 준 첨부 경로를 검사해 실제 경로(심볼릭 링크를 푼 뒤)를 돌려준다. 문제가 있으면 PathRejected."""
    real = _resolve_file(raw)
    _check_location(real, allowed_dirs, deny_roots or [])
    _check_secret_name(real)
    _check_size(real)
    return real
