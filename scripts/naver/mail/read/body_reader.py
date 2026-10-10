"""Naver Mail 본문 읽기 + PII 마스킹 + 링크/피싱 판정.

순수 함수(redact, classify_link, parse_body_payload) + CDP 호출(read_body).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from scripts.naver.mail.read import cdp

# ── PII 마스킹 ───────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"\b([A-Za-z0-9_.+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
_PHONE_RE = re.compile(r"\b01[016789][- .]?\d{3,4}[- .]?\d{4}\b")
_CARD_RE = re.compile(r"\b(\d{4})[ -](\d{4})[ -](\d{4})[ -](\d{4})\b")
_LONGNUM_RE = re.compile(r"\b\d{13,16}\b")
_RRN_RE = re.compile(r"\b\d{6}[- ]?[1-4]\d{6}\b")
_CODE_RE = re.compile(r"(인증번호|OTP|확인번호|verification code)[^\d]{0,8}(\d{4,8})")


def _mask_email(m: re.Match[str]) -> str:
    lp, dom = m.group(1), m.group(2)
    if len(lp) <= 2:
        return f"**@{dom}"
    return f"{lp[:2]}***@{dom}"


def redact(text: str) -> str:
    """PII 마스킹 — 카드/주민/전화/이메일local/인증번호."""
    if not text:
        return ""
    text = _CARD_RE.sub(lambda m: f"{m.group(1)}-****-****-{m.group(4)}", text)
    text = _LONGNUM_RE.sub("[NUMBER_MASKED]", text)
    text = _PHONE_RE.sub("010-****-****", text)
    text = _RRN_RE.sub("[RRN_MASKED]", text)
    text = _EMAIL_RE.sub(_mask_email, text)
    text = _CODE_RE.sub(lambda m: f"{m.group(1)} [CODE_MASKED]", text)
    return text


# ── 링크 도메인 / 피싱 판정 ────────────────────────────────────────

_DOMAIN_RE = re.compile(r"^https?://([^/]+)/?")

TRUSTED_DOMAINS: frozenset[str] = frozenset(
    {
        "coupang.com",
        "coupangcorp.com",
        "marketplace.coupang.com",
        "google.com",
        "search.google.com",
        "play.google.com",
        "apps.apple.com",
        "navercorp.com",
        "naver.com",
        "smartstore.naver.com",
        "wcs.naver.net",
        "search.naver.com",
        "kbcard.com",
        "kbmail.kbcard.com",
        "hyundaicard.com",
        "shinhancard.com",
        "lottecardmailcenter.net",
        "wooribank.com",
        "yes24.com",
        "x.com",
        "facebookmail.com",
        "github.com",
    }
)

_SUSPICIOUS_TLD_RE = re.compile(r"\.(tk|gq|ml|ga|cf|top|xyz|click|loan|win|work|fit|rest)$")


def link_domain(url: str) -> str:
    m = _DOMAIN_RE.match(url or "")
    return m.group(1).lower() if m else ""


def is_trusted(domain: str) -> bool:
    if not domain:
        return False
    for td in TRUSTED_DOMAINS:
        if domain == td or domain.endswith("." + td):
            return True
    return False


def is_phishing_suspect(url: str) -> bool:
    d = link_domain(url)
    if not d:
        return False
    if is_trusted(d):
        return False
    if _SUSPICIOUS_TLD_RE.search(d):
        return True
    return False


# ── 본문 데이터 ─────────────────────────────────────────────────────


@dataclass
class MailBody:
    sn: str
    final_url: str = ""
    subject: str = ""
    sender_name: str = ""
    sender_addr_redacted: str = ""
    date_text: str = ""
    body_redacted: str = ""
    body_len: int = 0
    link_domains: dict[str, int] = field(default_factory=dict)
    phishing_links: list[str] = field(default_factory=list)
    img_count: int = 0
    has_attach: bool = False
    attach_names: list[str] = field(default_factory=list)


BODY_EXPR = r"""
JSON.stringify((function(){
  const header = {
    subject: (document.querySelector('.mail_view_header .subject, .read_subject, [class*="subject"]')||{}).innerText || '',
    sender_name: (document.querySelector('.mail_view_header .sender_name, .sender_info .name, [class*="sender_name"]')||{}).innerText || '',
    sender_addr: (document.querySelector('.mail_view_header .sender_email, .sender_info .email, [class*="sender_email"]')||{}).innerText || '',
    date: (document.querySelector('.mail_view_header .date, .mail_date, [class*="date"]')||{}).innerText || '',
  };
  let body = '', links = [], img_count = 0;
  const iframe = document.querySelector('iframe#readFrame, iframe[name="readFrame"], iframe[id*="read"], iframe[class*="mail_view"]');
  if (iframe) {
    try {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      body = (doc.body && doc.body.innerText) || '';
      links = Array.from(doc.querySelectorAll('a[href]')).map(a => a.href).filter(h => h && !h.startsWith('mailto:'));
      img_count = doc.querySelectorAll('img').length;
    } catch (e) { body = '[iframe_access_denied]'; }
  } else {
    const c = document.querySelector('.mail_view_content, .read_content, [class*="mail_body"], .mail_view');
    body = c ? (c.innerText||'') : (document.body.innerText||'');
    links = Array.from(document.querySelectorAll('.mail_view_content a[href], .read_content a[href]'))
              .map(a => a.href).filter(h => h && !h.startsWith('mailto:'));
  }
  const has_attach = !!document.querySelector('.attach_area, .attachment_area, [class*="attach"]');
  const attach_names = Array.from(document.querySelectorAll('.attach_area .file_name, .attachment .name'))
    .map(e => (e.innerText||'').trim()).filter(Boolean);
  return {
    href: location.href, title: document.title,
    header, body: body.slice(0, 12000), body_len: body.length,
    links: links.slice(0, 80),
    img_count, has_attach, attach_names,
  };
})())
"""


def parse_body_payload(sn: str, payload: dict) -> MailBody:
    header = (payload or {}).get("header") or {}
    body_raw = (payload or {}).get("body") or ""
    links = (payload or {}).get("links") or []
    domains: dict[str, int] = {}
    suspect: list[str] = []
    for lk in links:
        d = link_domain(lk)
        domains[d] = domains.get(d, 0) + 1
        if is_phishing_suspect(lk):
            suspect.append(lk)
    return MailBody(
        sn=sn,
        final_url=(payload or {}).get("href", ""),
        subject=header.get("subject") or "",
        sender_name=header.get("sender_name") or "",
        sender_addr_redacted=redact(header.get("sender_addr") or ""),
        date_text=header.get("date") or "",
        body_redacted=redact(body_raw),
        body_len=int((payload or {}).get("body_len") or 0),
        link_domains=domains,
        phishing_links=suspect[:10],
        img_count=int((payload or {}).get("img_count") or 0),
        has_attach=bool((payload or {}).get("has_attach")),
        attach_names=list((payload or {}).get("attach_names") or []),
    )


def read_body(target_id: str, sn: str, *, wait_s: float = 4.0) -> MailBody:
    url = f"https://mail.naver.com/v2/popup/read/0/{sn}"
    cdp.navigate(target_id, url)
    time.sleep(wait_s)
    # iframe 또는 본문 영역 로딩 대기
    for _ in range(10):
        ok = cdp.evaluate(
            target_id,
            "!!(document.querySelector('iframe#readFrame, iframe[id*=\"read\"]') "
            "|| document.querySelector('.mail_view_content, .read_content'))",
            timeout=3.0,
        )
        if ok is True:
            break
        time.sleep(1.0)
    payload = cdp.evaluate(target_id, BODY_EXPR, timeout=8.0)
    return parse_body_payload(sn, payload if isinstance(payload, dict) else {})
