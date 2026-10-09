"""배포 후 1회 점검(D-2): 감사 로그(JSONL)에 민감정보가 평문으로 남아있는지 점검한다.

대상: 데스크톱 userData\\storage\\audit_logs.jsonl(및 회전 파일, 예: audit_logs.jsonl.1)
— 경로는 인자로 지정한다(이 PC 고정 경로를 가정하지 않는다).

규칙(비밀번호·토큰·API 키·쿠키·주민번호·카드번호)은 ai_orchestrator.core.security_utils
(9a48754b 에서 만든 마스킹 모듈)를 그대로 재사용한다 — 새 정규식·규칙을 여기서
다시 정의하지 않는다.

**값은 절대 출력하지 않는다.** 보고는 건수·줄 번호·필드 이름(또는 규칙명)만이다.

사용:
  python tools/audits/backend/audit_log_sensitive_scan.py <로그파일...> [--rewrite]

읽기 전용(기본): 발견 건수를 표로 출력하고 끝난다(아무 것도 고치지 않음).
--rewrite: 각 대상 파일을 <파일>.bak-<타임스탬프>로 먼저 백업한 뒤, 민감정보를
마스킹한 내용으로 원자적(tmp+rename)으로 재작성한다. 회전 파일(<path>.N)이
같은 폴더에 있으면 자동으로 같이 검사한다(별도로 안 적어도 됨).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(
    0, str(next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()))
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

from ai_orchestrator.core.security_utils import (
    AWS_KEY_RE,
    BEARER_RE,
    CARD_RE,
    GITHUB_TOKEN_RE,
    JWT_RE,
    OPENAI_KEY_RE,
    REDACTED,
    RRN_RE,
    SLACK_TOKEN_RE,
    is_sensitive_key,
)

# 값 패턴 규칙 — ai_orchestrator.core.security_utils 의 기존 정규식을 그대로 가리킨다(재사용).
_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("RRN", RRN_RE),
    ("CARD", CARD_RE),
    ("BEARER_TOKEN", BEARER_RE),
    ("JWT", JWT_RE),
    ("OPENAI_KEY", OPENAI_KEY_RE),
    ("GITHUB_TOKEN", GITHUB_TOKEN_RE),
    ("SLACK_TOKEN", SLACK_TOKEN_RE),
    ("AWS_KEY", AWS_KEY_RE),
)
_REDACTION_LABELS: dict[str, str] = {
    "RRN": "[RRN_REDACTED]",
    "CARD": "[CARD_REDACTED]",
}


def _redact_value_patterns(text: str) -> str:
    for rule_name, pattern in _VALUE_PATTERNS:
        text = pattern.sub(_REDACTION_LABELS.get(rule_name, "[TOKEN_REDACTED]"), text)
    return text


@dataclass(frozen=True)
class Finding:
    line: int
    field: str
    rule: str


def _collect_in_value(key: str, value: object, line: int, path: str) -> list[Finding]:
    """값 하나를 점검한다 — 민감 키 이름이면 SENSITIVE_KEY, 문자열이면 값 패턴도 본다.
    재귀 구조(dict/list/tuple)는 ai_orchestrator.core.security_utils.redact_obj 와 같은
    모양으로 내려간다(실제 마스킹은 redact_obj 에 위임, 여기서는 '찾기'만)."""
    field = path or key
    if isinstance(value, Mapping):
        out: list[Finding] = []
        for k, v in value.items():
            out.extend(_collect_in_value(str(k), v, line, f"{field}.{k}" if field else str(k)))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_collect_in_value(key, item, line, f"{field}[]"))
        return out
    if isinstance(value, str):
        findings: list[Finding] = []
        if is_sensitive_key(key):
            findings.append(Finding(line, field, f"SENSITIVE_KEY:{key}"))
            return findings  # 민감 키는 전체가 가려질 대상이라 값 패턴 중복 보고 안 함
        for rule_name, pattern in _VALUE_PATTERNS:
            if pattern.search(value):
                findings.append(Finding(line, field, rule_name))
        return findings
    return []


def scan_line(line_no: int, raw_line: str) -> list[Finding]:
    """한 줄(JSON 객체 1개 또는 평문)의 민감정보 발견 목록. 값은 어디에도 담지 않는다."""
    text = raw_line.rstrip("\n")
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except ValueError:
        # JSONL이 아닌 줄(손상·다른 형식) — 값 패턴만 평문 전체에서 찾는다.
        findings = []
        for rule_name, pattern in _VALUE_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(line_no, "(freeform line)", rule_name))
        return findings
    if isinstance(data, Mapping):
        return _collect_in_value("", data, line_no, "")
    return []


def scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for i, raw_line in enumerate(f, start=1):
            findings.extend(scan_line(i, raw_line))
    return findings


def rotated_siblings(path: Path) -> list[Path]:
    """<path>와 같은 폴더의 회전 파일(<path>.1, <path>.2, ...)을 함께 찾는다."""
    out = [path] if path.is_file() else []
    n = 1
    while True:
        candidate = path.with_name(f"{path.name}.{n}")
        if not candidate.is_file():
            break
        out.append(candidate)
        n += 1
    return out


def _mask_value(key: str, value: object) -> object:
    """scan_line/_collect_in_value과 정확히 같은 판정으로 값을 가린다(재작성이 점검 결과보다
    더 많이/다르게 가리지 않도록). 민감 키가 아닌 식별 필드(task_id·actor 등)의 이메일까지
    통째로 지우는 건 범위 밖이다(9a48754b에서 겪은 "식별 필드 훼손" 회귀와 같은 문제)."""
    if isinstance(value, Mapping):
        return {k: _mask_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(key, item) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_value(key, item) for item in value)
    if isinstance(value, str):
        if is_sensitive_key(key):
            return REDACTED
        return _redact_value_patterns(value)
    return value


def _mask_line(raw_line: str) -> str:
    text = raw_line.rstrip("\n")
    if not text.strip():
        return raw_line
    try:
        data = json.loads(text)
    except ValueError:
        # JSON이 아닌 줄도 값 패턴만큼은 가린다(민감 키 판단은 구조가 없어 불가).
        return _redact_value_patterns(text) + "\n"
    if isinstance(data, Mapping):
        masked = _mask_value("", data)
        return json.dumps(masked, ensure_ascii=False) + "\n"
    return raw_line


def rewrite_file(path: Path) -> Path:
    """백업(.bak-타임스탬프) 후 마스킹된 내용으로 원자적(tmp+rename) 재작성. 백업 경로를 반환."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    backup_path.write_bytes(path.read_bytes())

    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with (
        path.open("r", encoding="utf-8", errors="replace") as src,
        tmp_path.open("w", encoding="utf-8", newline="") as dst,
    ):
        for raw_line in src:
            dst.write(_mask_line(raw_line))
    os.replace(tmp_path, path)
    return backup_path


def _print_report(path: Path, findings: list[Finding]) -> None:
    print(f"=== {path} ===")
    if not findings:
        print("  발견 없음")
        return
    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
    print(f"  총 {len(findings)}건")
    for rule, count in sorted(by_rule.items()):
        print(f"    - {rule}: {count}건")
    print("  위치(줄:필드):")
    for f in findings[:50]:
        print(f"    {f.line}:{f.field} [{f.rule}]")
    if len(findings) > 50:
        print(f"    ... 외 {len(findings) - 50}건")


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    with contextlib.suppress(AttributeError, ValueError):
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path, help="감사 로그 파일 경로(들)")
    ap.add_argument("--rewrite", action="store_true", help="백업 후 마스킹 재작성(기본은 읽기만)")
    args = ap.parse_args(argv)

    targets: list[Path] = []
    for p in args.paths:
        for sibling in rotated_siblings(p):
            if sibling not in targets:
                targets.append(sibling)

    missing = [p for p in args.paths if not p.is_file()]
    if missing:
        for p in missing:
            print(f"[audit_log_sensitive_scan] 파일 없음: {p}", file=sys.stderr)
    if not targets:
        print("[audit_log_sensitive_scan] 점검할 파일이 없습니다.", file=sys.stderr)
        return 2

    total = 0
    for path in targets:
        findings = scan_file(path)
        _print_report(path, findings)
        total += len(findings)
        if args.rewrite and findings:
            backup = rewrite_file(path)
            print(f"  재작성 완료 — 백업: {backup}")

    print(f"\n합계: {len(targets)}개 파일, {total}건 발견")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
