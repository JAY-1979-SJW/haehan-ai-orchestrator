"""site_engine capability detector — DOM snapshot 기반 작업 가능성 감지.

실제 브라우저 실행 없이 텍스트/버튼/메타데이터 스냅샷만으로 판단한다.
기존 scripts/explorer/page_classifier.py를 대체하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.site_engine.site_types import GateDecision, SiteCapability

_SUBMIT_BUTTON_KEYWORDS = frozenset(
    {
        "submit",
        "save",
        "저장",
        "확인",
        "등록",
        "신청",
        "완료",
        "apply",
        "confirm",
        "상신",
        "결재",
        "투찰",
    }
)

_PUBLISH_BUTTON_KEYWORDS = frozenset(
    {
        "publish",
        "post",
        "게시",
        "발행",
        "공개",
        "등록",
    }
)

_SEND_BUTTON_KEYWORDS = frozenset(
    {
        "send",
        "mail",
        "전송",
        "보내기",
        "발송",
        "메일",
    }
)

_DELETE_BUTTON_KEYWORDS = frozenset(
    {
        "delete",
        "remove",
        "삭제",
        "제거",
        "취소",
        "cancel",
    }
)

_SIGN_BUTTON_KEYWORDS = frozenset(
    {
        "sign",
        "서명",
        "전자서명",
        "공동인증",
        "인증서",
    }
)

_UPLOAD_BUTTON_KEYWORDS = frozenset(
    {
        "upload",
        "attach",
        "첨부",
        "업로드",
        "파일",
    }
)

_DOWNLOAD_BUTTON_KEYWORDS = frozenset(
    {
        "download",
        "다운로드",
        "내려받기",
        "저장",
    }
)

_LOGIN_REQUIRED_KEYWORDS = frozenset(
    {
        "login",
        "로그인",
        "sign in",
        "sign_in",
        "로그인 후",
    }
)

_APPROVAL_CAPABILITIES = frozenset(
    {
        SiteCapability.SUBMIT,
        SiteCapability.PUBLISH,
        SiteCapability.SEND,
        SiteCapability.DELETE,
        SiteCapability.SIGN,
        SiteCapability.UPLOAD,
    }
)


@dataclass
class PageCapability:
    capability: SiteCapability
    detected: bool
    confidence: float  # 0.0 ~ 1.0
    evidence: list[str] = field(default_factory=list)
    requires_approval: bool = False
    required_gate: GateDecision = GateDecision.READ_ONLY_ALLOWED


@dataclass
class CapabilityDetectionInput:
    page_url: str
    page_title: str = ""
    button_labels: list[str] = field(default_factory=list)
    input_types: list[str] = field(default_factory=list)
    has_file_input: bool = False
    has_form: bool = False
    has_table: bool = False
    has_search_input: bool = False
    page_text_snippet: str = ""


@dataclass
class CapabilityDetectionResult:
    capabilities: list[PageCapability]
    login_required: bool
    user_direct_required: bool
    detected_set: frozenset[SiteCapability] = field(default_factory=frozenset)


def _match_keywords(labels: list[str], keywords: frozenset[str]) -> list[str]:
    matched = []
    for label in labels:
        lower = label.lower()
        for kw in keywords:
            if kw in lower:
                matched.append(label)
                break
    return matched


def _make_cap(
    capability: SiteCapability,
    evidence: list[str],
    gate: GateDecision,
) -> PageCapability:
    confidence = min(len(evidence) * 0.4, 1.0)
    return PageCapability(
        capability=capability,
        detected=bool(evidence),
        confidence=confidence,
        evidence=evidence,
        requires_approval=(capability in _APPROVAL_CAPABILITIES),
        required_gate=gate,
    )


def _append_keyword_caps(caps, labels):
    # SUBMIT
    submit_ev = _match_keywords(labels, _SUBMIT_BUTTON_KEYWORDS)
    if submit_ev:
        caps.append(_make_cap(SiteCapability.SUBMIT, submit_ev, GateDecision.APPROVAL_REQUIRED))

    # PUBLISH
    pub_ev = _match_keywords(labels, _PUBLISH_BUTTON_KEYWORDS)
    if pub_ev:
        caps.append(_make_cap(SiteCapability.PUBLISH, pub_ev, GateDecision.APPROVAL_REQUIRED))

    # SEND
    send_ev = _match_keywords(labels, _SEND_BUTTON_KEYWORDS)
    if send_ev:
        caps.append(_make_cap(SiteCapability.SEND, send_ev, GateDecision.APPROVAL_REQUIRED))

    # DELETE
    del_ev = _match_keywords(labels, _DELETE_BUTTON_KEYWORDS)
    if del_ev:
        caps.append(_make_cap(SiteCapability.DELETE, del_ev, GateDecision.APPROVAL_REQUIRED))


def detect_capabilities_from_snapshot(
    detection_input: CapabilityDetectionInput,
) -> CapabilityDetectionResult:
    caps: list[PageCapability] = []
    labels = detection_input.button_labels
    all_text = [detection_input.page_text_snippet, detection_input.page_title]  # noqa: F841

    # READ — 항상 감지 (페이지가 있으면 읽기 가능)
    caps.append(
        PageCapability(
            capability=SiteCapability.READ,
            detected=True,
            confidence=1.0,
            evidence=["page_exists"],
            requires_approval=False,
            required_gate=GateDecision.READ_ONLY_ALLOWED,
        )
    )

    # SEARCH
    if detection_input.has_search_input:
        caps.append(_make_cap(SiteCapability.SEARCH, ["search_input"], GateDecision.SERVER_BROWSER_ALLOWED))

    # FORM_FILL
    if detection_input.has_form or detection_input.input_types:
        caps.append(_make_cap(SiteCapability.FORM_FILL, ["form_or_input"], GateDecision.SERVER_BROWSER_ALLOWED))

    # DOWNLOAD
    dl = _match_keywords(labels, _DOWNLOAD_BUTTON_KEYWORDS)
    if dl:
        caps.append(_make_cap(SiteCapability.DOWNLOAD, dl, GateDecision.SERVER_BROWSER_ALLOWED))

    # UPLOAD
    upload_ev = []
    if detection_input.has_file_input:
        upload_ev.append("file_input")
    upload_ev += _match_keywords(labels, _UPLOAD_BUTTON_KEYWORDS)
    if upload_ev:
        caps.append(_make_cap(SiteCapability.UPLOAD, upload_ev, GateDecision.APPROVAL_REQUIRED))

    _append_keyword_caps(caps, labels)

    # SIGN
    sign_ev = _match_keywords(labels, _SIGN_BUTTON_KEYWORDS)
    if sign_ev:
        caps.append(_make_cap(SiteCapability.SIGN, sign_ev, GateDecision.USER_DIRECT_REQUIRED))

    # LOGIN_REQUIRED 감지
    login_ev = _match_keywords(
        labels + [detection_input.page_text_snippet],  # noqa: RUF005
        _LOGIN_REQUIRED_KEYWORDS,
    )
    login_required = bool(login_ev)

    # USER_DIRECT_REQUIRED: sign 또는 login_required
    user_direct = login_required or any(c.required_gate == GateDecision.USER_DIRECT_REQUIRED for c in caps)

    detected_set = frozenset(c.capability for c in caps if c.detected)

    return CapabilityDetectionResult(
        capabilities=caps,
        login_required=login_required,
        user_direct_required=user_direct,
        detected_set=detected_set,
    )
