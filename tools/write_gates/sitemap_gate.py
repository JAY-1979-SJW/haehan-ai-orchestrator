"""사이트 자동화 코드 작성 시 사이트맵(HTML 스냅샷) 확인 게이트 — 경고 전용.

셀렉터·로그인 판정을 쓰는 사이트 자동화 코드를 작성할 때, 그 사이트의 스냅샷
(`data/sitemap/<주소>.json`, scripts/explorer/page_snapshot 이 수집)이 있는지 본다.
없으면 "먼저 수집하라"는 경고를 낸다. 차단하지 않는다(오탐률을 로그로 측정한 뒤 승격 결정).
로그: data/logs/sitemap_gate.jsonl (발동/통과/경고).
한계: PreToolUse(Write) 입력에는 '이 세션에서 스냅샷을 읽었는가' 기록이 없어 존재 여부만 본다.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from tools.write_gates.duplicate_impl_gate import is_automation_path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
SITEMAP_DIR = ROOT / "data" / "sitemap"
LOG_PATH = ROOT / "data" / "logs" / "sitemap_gate.jsonl"

# 셀렉터·로그인 판정을 다루는 코드인지 가르는 표지
_TRIGGERS = ("query_selector", "locator(", "logged_in", "login")
_URL_HOST = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PATH_DOMAIN_HINTS = {"scripts/naver/": "naver.com", "scripts/eum": "eum.cw.or.kr"}
_PUBLIC_SUFFIXES = {"or.kr", "co.kr", "go.kr", "ne.kr", "com", "net", "kr"}


def _slug_host(name: str) -> str:
    return name.lower()


def _domains(file_path: str, content: str) -> list[str]:
    """코드가 다루는 도메인 — 내용의 URL 호스트 + 경로 힌트."""
    p = file_path.replace("\\", "/")
    found: list[str] = []
    for host in _URL_HOST.findall(content):
        h = host.lower().removeprefix("www.")
        if h not in found:
            found.append(h)
    for hint, domain in _PATH_DOMAIN_HINTS.items():
        if (p.startswith(hint) or f"/{hint}" in p) and domain not in found:
            found.append(domain)
    return found


def _candidates(domain: str) -> list[str]:
    """사이트맵 파일명에 들어 있어야 할 후보 조각 — 전체 호스트와, 공용 접미사가 아닌 상위 도메인."""
    parts = domain.split(".")
    out = [domain]
    for i in range(1, len(parts) - 1):
        suffix = ".".join(parts[i:])
        if suffix not in _PUBLIC_SUFFIXES and suffix not in out:
            out.append(suffix)
    return out


def _has_sitemap(domain: str, sitemap_dir: Path | None = None) -> bool:
    # 기본값을 인자에 직접 쓰면 함수를 정의할 때 값이 굳어 SITEMAP_DIR 을 바꿔도(시험·설정) 반영되지 않는다
    sitemap_dir = SITEMAP_DIR if sitemap_dir is None else sitemap_dir
    if not sitemap_dir.is_dir():
        return False
    names = [_slug_host(f.name) for f in sitemap_dir.glob("*.json")]
    return any(c in n for c in _candidates(domain) for n in names)


def _log(entry: dict) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(
                json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **entry}, ensure_ascii=False) + "\n"
            )
    except OSError:
        pass  # 로그 실패가 작성 흐름을 막으면 안 된다


def check(file_path: str, content: str) -> str | None:
    """차단 게이트 자리 — 경고 모드에서는 항상 None."""
    return None


def warn(file_path: str, content: str) -> str | None:
    """경고 문구(없으면 None). 발동/통과/경고를 로그로 남긴다."""
    if not is_automation_path(file_path):
        return None
    if not any(t in content for t in _TRIGGERS):
        return None
    domains = _domains(file_path, content)
    missing = [d for d in domains if not _has_sitemap(d)]
    _log(
        {
            "file": file_path.replace("\\", "/"),
            "domains": domains,
            "result": "warn" if missing else "pass",
            "missing": missing,
        }
    )
    if not missing:
        return None
    return (
        f"사이트맵(HTML 스냅샷) 없음: {', '.join(missing)} — 셀렉터·로그인 판정을 추측으로 쓰지 말고 먼저 수집하세요. "
        "로그인된 CDP 탭에서: py -3.14 -c \"from scripts.explorer import run; run('page', [])\" → data/sitemap/ 에 저장됨. "
        "(경고 전용 — 작성은 막지 않음)"
    )
