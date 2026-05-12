"""통합 스키마 정의 — scripts 레이어 데이터 모델.

모든 로그/이벤트/게이트 결과의 TypedDict/dataclass 정의를 한 곳에 모은다.
op_log, critical_logger, cdp_event_monitor, gate 에서 공통으로 참조한다.

사용법:
    from scripts.schemas import OpRecord, CriticalRecord, GateResult, CdpNavEvent
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict


# ── 공통 상수 ─────────────────────────────────────────────────────────

class OpStatus(str, Enum):
    OK    = "ok"
    FAIL  = "fail"
    START = "start"


class RiskLevel(str, Enum):
    """작업 위험 등급.

    AUTO   — 자동 실행 허용 (조회/탐색/읽기 등)
    NOTIFY — 실행하되 로그에 경고 기록 (파일 쓰기, URL 이동 등)
    APPROVE — 사용자 직접 승인 필요 (메일 발송, 결제 등)
    BLOCK  — 실행 금지 (민감정보 삭제, 인증서 조작 등)
    """
    AUTO    = "auto"
    NOTIFY  = "notify"
    APPROVE = "approve"
    BLOCK   = "block"


class GateVerdict(str, Enum):
    ALLOWED  = "allowed"   # 통과
    NOTIFIED = "notified"  # 통과 + 경고 기록
    PENDING  = "pending"   # 승인 대기 (외부 처리 필요)
    BLOCKED  = "blocked"   # 차단


# ── ops_log 레코드 ────────────────────────────────────────────────────

class OpRecord(TypedDict, total=False):
    """op_log.ops_log 테이블 1행."""
    id: int
    ts: str            # ISO8601 (밀리초)
    op_name: str       # 작업 이름 (예: "goto", "file_write", "cdp_nav")
    status: str        # OpStatus 값
    duration_ms: int   # 소요 시간 (ms), None 가능
    message: str       # 사람 읽기 메시지 (최대 500자)
    metadata: str      # JSON 직렬화된 추가 데이터
    created_at: str


# ── critical_logs 레코드 ─────────────────────────────────────────────

class CriticalRecord(TypedDict, total=False):
    """critical_logger.critical_logs 테이블 1행."""
    id: int
    ts: str        # ISO8601 (초)
    category: str  # critical_logger.CATEGORIES 내 값
    message: str
    metadata: str  # JSON
    created_at: str


# ── CDP 이벤트 ────────────────────────────────────────────────────────

class CdpNavEvent(TypedDict):
    """Page.frameNavigated 이벤트 기록."""
    ts: str       # ISO8601
    url: str
    tab_id: str
    domain: str


class CdpRequestEvent(TypedDict):
    """Network.requestWillBeSent 기록 (Document/XHR/Fetch 한정)."""
    ts: str
    method: str        # GET, POST, etc.
    url: str
    resource_type: str  # Document, XHR, Fetch
    tab_id: str


# ── 코드 변경 레코드 (file_write / file_edit) ────────────────────────

class FileChangeRecord(TypedDict):
    """log_code_change.py 가 기록하는 파일 변경 이벤트."""
    ts: str
    op: str        # file_write | file_edit | notebook_edit
    file: str      # 프로젝트 루트 상대 경로
    ext: str       # .py, .json 등
    size: int      # 변경 바이트 수 (Write: content 길이, Edit: diff 크기)
    tool: str      # Write | Edit | NotebookEdit


# ── 게이트 결과 ───────────────────────────────────────────────────────

@dataclass
class GateResult:
    """gate.check() 반환값."""
    verdict: GateVerdict
    risk: RiskLevel
    op_name: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.verdict in (GateVerdict.ALLOWED, GateVerdict.NOTIFIED)

    @property
    def blocked(self) -> bool:
        return self.verdict == GateVerdict.BLOCKED


# ── 팝업 이벤트 (popup_watcher / popup_monitor) ──────────────────────

class PopupEvent(TypedDict):
    """popup_watcher가 DOM에서 감지한 팝업 이벤트."""
    ts_ms: int
    marker: str
    snippet: str
    frame_url: str


class PopupDecision(TypedDict):
    """popup_classifier가 판단한 처리 방침."""
    category: str    # draft_restore | marketing_optin | destructive_confirm | ...
    severity: str    # low | medium | high
    action: str      # auto_dismiss | notify_user | block_workflow
    target: str      # 클릭할 버튼 텍스트 (auto_dismiss일 때)
    confidence: float
    reasoning: str


# ── EUM 단말기 레코드 ─────────────────────────────────────────────────

class EumDevice(TypedDict, total=False):
    """WEBMAN390M00에서 추출된 단말기 1개."""
    NO: str
    고유번호: str
    단말기번호: str
    공제가입번호: str
    공사명: str
    발주기관: str
    전자카드구분: str
    지정업체: str       # 임차인
    단말기유형: str
    운용상태: str
    설치일: str
    처리건수: str
    계약유형: str
    총비용: str
    # 행2
    단말기ID: str
    공사번호: str
    공사상태: str
    공사업체: str
    관할지사: str
    설치예외: str
    유통업체: str
    지정단말기명: str
    통신상태: str
    철거일: str
    설치일수: str
    설치유형: str
    잔존가치: str
