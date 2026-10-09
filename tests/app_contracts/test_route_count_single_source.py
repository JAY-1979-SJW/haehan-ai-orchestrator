"""백엔드 라우트 개수 단일 정본(configs/route_count_expectation.json) 검증.

라우트를 추가·삭제하면 그 JSON 한 줄만 고치면 된다. 이 시험은 ① 정본 형식 ② 실제 런타임 개수 == 정본 ③ 시험·감사 스크립트에
개수 숫자가 다시 박히지 않았는지를 확인한다(숫자를 여러 파일에 중복해 적으면 병합마다 충돌한다).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.app_routes import http_routes, runtime_routes, websocket_routes
from tools.audits.backend import audit_backend_runtime_contract as audit

ROOT = Path(__file__).resolve().parents[2]
EXPECTATION = ROOT / "configs" / "route_count_expectation.json"


def _measured() -> dict[str, int]:
    http = http_routes()
    return {
        "total": len(runtime_routes()),
        "http": len(http),
        "websocket": len(websocket_routes()),
        "post": sum(1 for r in http if "POST" in r.method.split(",")),
    }


# ── ① 정본 형식 ──────────────────────────────────────────────────────────────


def test_expectation_file_is_well_formed():
    counts = audit.load_route_count_expectation(EXPECTATION)
    assert set(counts) == {"total", "http", "websocket", "post"}
    assert counts["total"] == counts["http"] + counts["websocket"]


@pytest.mark.parametrize(
    "payload",
    [
        {"total": 10, "http": 8, "websocket": 1, "post": 3},  # total != http + websocket
        {"total": "10", "http": 8, "websocket": 2, "post": 3},  # 문자열
        {"total": 10, "http": 8, "websocket": 2},  # post 없음
        {"total": 10, "http": 8, "websocket": 2, "post": -1},  # 음수
        {"total": True, "http": 1, "websocket": 0, "post": 0},  # bool 은 정수로 보지 않는다
    ],
)
def test_malformed_expectation_fails_loudly(tmp_path, payload):
    path = tmp_path / "route_count_expectation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        audit.load_route_count_expectation(path)


def test_audit_constants_come_from_the_single_source():
    counts = audit.load_route_count_expectation(EXPECTATION)
    assert audit.EXPECTED_RUNTIME_ROUTES == counts["total"]
    assert audit.EXPECTED_HTTP_ROUTES == counts["http"]
    assert audit.EXPECTED_WEBSOCKET_ROUTES == counts["websocket"]
    assert audit.EXPECTED_POST_ROUTES == counts["post"]


# ── ② 실제 런타임 개수 == 정본 ───────────────────────────────────────────────


def test_runtime_route_counts_match_the_single_source():
    expected = audit.load_route_count_expectation(EXPECTATION)
    measured = _measured()
    assert measured == expected, (
        "라우트 개수가 정본(configs/route_count_expectation.json)과 다릅니다. 라우트를 추가·삭제했다면 그 파일을 실측값으로 고치세요: "
        + json.dumps(measured)
    )


# ── ③ 숫자 직접 기재 금지 ────────────────────────────────────────────────────

_SCAN_DIRS = ("tests", "ai_orchestrator/tests", "scripts/ops")
_HARDCODED = [
    # assert len(routes) == 428 같은 직접 비교(세 자리 이상 = 라우트 총수 규모)
    re.compile(r"len\((?:routes|posts|http|gets|ws|http_routes|runtime)\)\s*==\s*\d{3,}"),
    # RUNTIME_HTTP_ENDPOINT_COUNT = 426 같은 상수
    re.compile(r"(?:ENDPOINT|ROUTE|ROUTES)_COUNT\s*=\s*\d{3,}"),
    # 시험 본문에 개수 문자열이 있는지 보던 옛 방식: assert "== 428" in domain_test
    re.compile(r"[\"'](?:== |= )\d{3}[\"']\s+in\b"),
    # 감사 스크립트의 기준값 상수
    re.compile(r"^EXPECTED_\w*ROUTES\s*=\s*\d+", re.MULTILINE),
]


def test_no_hardcoded_route_counts_in_tests_or_audit_scripts():
    offenders: list[str] = []
    for rel in _SCAN_DIRS:
        for path in sorted((ROOT / rel).rglob("*.py")):
            if path.name == Path(__file__).name:
                continue  # 이 시험은 패턴 정의에 숫자 예시를 가진다
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in _HARDCODED:
                match = pattern.search(text)
                if match:
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}: {match.group(0)}")
    assert not offenders, (
        "라우트 개수를 직접 적지 말고 configs/route_count_expectation.json 을 읽으세요:\n" + "\n".join(offenders)
    )


def test_scan_pattern_detects_hardcoded_examples():
    # 패턴이 실제로 옛 방식을 잡는지(검사기가 조용히 무력해지지 않았는지)
    samples = [
        "assert len(routes) == 428",
        "RUNTIME_HTTP_ENDPOINT_COUNT = 426",
        'assert "== 428" in domain_test',
        "EXPECTED_RUNTIME_ROUTES = 428",
    ]
    for sample in samples:
        assert any(p.search(sample) for p in _HARDCODED), sample
    for ok in [
        "assert len(routes) == EXPECTED_RUNTIME_ROUTES",
        "assert len(routes) == 13",
        "EXPECTED_RUNTIME_ROUTES = _EXPECTED['total']",
    ]:
        assert not any(p.search(ok) for p in _HARDCODED), ok
