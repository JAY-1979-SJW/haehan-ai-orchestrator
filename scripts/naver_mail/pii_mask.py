"""확장 PII 마스킹 — body_reader.redact 의 superset.

마스킹 대상:
  - 이메일 주소 (local-part)
  - 전화번호 (휴대폰 / 일반 / 국제)
  - 주민등록번호
  - 사업자등록번호 (123-45-67890)
  - 카드번호 (4×4 / 13~16자리 연속)
  - 계좌번호 (대형 은행 패턴 + 연속 8~14자리)
  - 주소 (도/시/구/동 + 번지) — 보수적
  - 라벨 기반 값 (예: '이름: ', '비밀번호: ')
  - 인증번호 / OTP

출력:
  PIIMaskResult(masked_text, detected_count, types: {type: count}, masked_text_hash)
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field


# 패턴 정의 — 각 (이름, regex, 치환자)
_PATTERNS = [
    ("CARD_4x4", re.compile(r"\b(\d{4})[ -](\d{4})[ -](\d{4})[ -](\d{4})\b"),
     lambda m: f"{m.group(1)}-****-****-{m.group(4)}"),
    ("RRN", re.compile(r"\b\d{6}[- ]?[1-4]\d{6}\b"), "[RRN_MASKED]"),
    ("BIZ_REG", re.compile(r"\b\d{3}-\d{2}-\d{5}\b"), "[BIZREG_MASKED]"),
    ("PHONE_MOBILE",
     re.compile(r"\b01[016789][- .]?\d{3,4}[- .]?\d{4}\b"),
     "010-****-****"),
    ("PHONE_LANDLINE",
     re.compile(r"\b0\d{1,2}[- ]\d{3,4}[- ]\d{4}\b"),
     "[PHONE_MASKED]"),
    ("PHONE_INTL",
     re.compile(r"\b\+?82[- ]?1\d[- ]?\d{3,4}[- ]?\d{4}\b"),
     "[PHONE_MASKED]"),
    ("LONG_NUM_13_16", re.compile(r"\b\d{13,16}\b"), "[NUMBER_MASKED]"),
    ("ACCOUNT_8_14", re.compile(r"\b\d{3,6}-\d{2,6}-\d{2,8}\b"),
     "[ACCOUNT_MASKED]"),
    ("AUTH_CODE", re.compile(r"(인증번호|OTP|확인번호|verification code)[^\d]{0,8}(\d{4,8})"),
     lambda m: f"{m.group(1)} [CODE_MASKED]"),
]


_EMAIL_RE = re.compile(r"\b([A-Za-z0-9_.+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")


def _mask_email(m: "re.Match[str]") -> str:
    lp, dom = m.group(1), m.group(2)
    if len(lp) <= 2:
        return f"**@{dom}"
    return f"{lp[:2]}***@{dom}"


# 주소 — 시/도 + 시/군/구 + 동/읍 + 번지 패턴 (보수적)
_ADDR_RE = re.compile(
    r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
    r"[가-힣\s]{2,40}[가-힣]+(?:동|읍|면|리|로|길)\s*\d{1,4}(?:[-]\d{1,4})?"
)


_LABEL_RE = re.compile(
    r"(이름|성명|주소|배송지|패스워드|비밀번호|password|아이디|ID|로그인 ?ID)"
    r"\s*[:：=]\s*([^\n,]{1,40})",
    re.IGNORECASE,
)


@dataclass
class PIIMaskResult:
    masked_text: str
    detected_count: int
    types: dict = field(default_factory=dict)
    masked_text_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "masked_text": self.masked_text,
            "detected_count": self.detected_count,
            "types": dict(self.types),
            "masked_text_hash": self.masked_text_hash,
        }


def mask(text: str, *, hash_only: bool = False) -> PIIMaskResult:
    """문자열에서 PII 검출 + 마스킹.

    hash_only=True 면 masked_text 는 빈 문자열, hash 만 반환 (감사용).
    """
    if not text:
        return PIIMaskResult("", 0, {}, "")
    counts: Counter[str] = Counter()
    out = text

    # 1) 라벨 기반 (먼저 — 다른 패턴이 먹기 전)
    def _label_sub(m):
        counts["LABEL_VALUE"] += 1
        return f"{m.group(1)}: [VALUE_MASKED]"
    out = _LABEL_RE.sub(_label_sub, out)

    # 2) 카드/주민/사업자/전화/장숫자/계좌/OTP
    for name, pat, repl in _PATTERNS:
        if callable(repl):
            def _f(m, _n=name, _r=repl):
                counts[_n] += 1
                return _r(m)
            out = pat.sub(_f, out)
        else:
            def _f(m, _n=name, _r=repl):
                counts[_n] += 1
                return _r
            out = pat.sub(_f, out)

    # 3) 이메일
    def _email_sub(m):
        counts["EMAIL"] += 1
        return _mask_email(m)
    out = _EMAIL_RE.sub(_email_sub, out)

    # 4) 주소
    def _addr_sub(m):
        counts["ADDRESS"] += 1
        return "[ADDRESS_MASKED]"
    out = _ADDR_RE.sub(_addr_sub, out)

    total = sum(counts.values())
    h = hashlib.sha256(out.encode("utf-8")).hexdigest()[:16]
    return PIIMaskResult(
        masked_text="" if hash_only else out,
        detected_count=total,
        types=dict(counts),
        masked_text_hash=h,
    )


def assert_no_raw_pii(masked_text: str, *, original_samples: list[str]) -> list[str]:
    """masked_text 안에 원본 PII 가 그대로 남았는지 자기검증.

    Returns 발견된 원본 PII 목록 (있으면 leak).
    """
    leaks = []
    for s in original_samples:
        if not s:
            continue
        if s in masked_text:
            leaks.append(s)
    return leaks
