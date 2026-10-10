"""벤더 공식 API 조회 — CDP 착수 전에 '살 수 있는 것을 만들고 있지 않은지' 확인한다.

2026-08-15 실제 사고:
    스마트스토어 상품등록을 CDP 브라우저 자동화로 구현했다. 검색태그에 다섯 번,
    옵션 그리드에 여러 번 헛짚었고 접힌 섹션 때문에 네 번 오판했다.
    그런데 네이버 커머스API가 **무료로** 그 기능을 전부 제공하고 있었다.

    capability_check 는 '저장소 안의 구현' 을 찾는 도구다. 그래서 이걸 못 잡았다.
    CLAUDE.md 의 "API가 있으면 API 호출, CDP는 최후 수단" 규칙을 실제로 지키려면
    벤더 API 목록이 따로 필요하다.

이 모듈은 판단하지 않는다. **경고만 한다.**
목록이 낡을 수 있으므로(벤더가 API를 추가/폐지한다) 최종 확인은 사람이 문서를 본다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
REGISTRY_FILE = _ROOT / "configs" / "vendor_apis.json"

STATUS_AVAILABLE = "available"  # 이미 쓸 수 있음
STATUS_REGISTERED = "registered"  # 앱 등록 완료
STATUS_NOT_REGISTERED = "not_registered"  # API 는 있는데 우리가 미신청
STATUS_UNKNOWN = "unknown"  # API 존재 여부 미확인


@dataclass
class VendorAPI:
    name: str
    keywords: list[str] = field(default_factory=list)
    docs: str = ""
    cost: str = ""
    status: str = STATUS_UNKNOWN
    auth: str = ""
    supported: list[str] = field(default_factory=list)
    not_supported: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """API 로 대체할 수 있는 기능이 하나라도 있는가."""
        return bool(self.supported)

    @property
    def needs_signup(self) -> bool:
        return self.status == STATUS_NOT_REGISTERED

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "docs": self.docs,
            "cost": self.cost,
            "status": self.status,
            "supported": list(self.supported),
            "not_supported": list(self.not_supported),
            "caveats": list(self.caveats),
        }


def _load(path: Path | None = None) -> list[VendorAPI]:
    f = Path(path) if path else REGISTRY_FILE
    if not f.exists():
        return []
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[VendorAPI] = []
    for v in raw.get("vendors") or []:
        out.append(
            VendorAPI(
                name=v.get("name", ""),
                keywords=[k.lower() for k in (v.get("keywords") or [])],
                docs=v.get("docs", ""),
                cost=v.get("cost", ""),
                status=v.get("status", STATUS_UNKNOWN),
                auth=v.get("auth", ""),
                supported=list(v.get("supported") or []),
                not_supported=list(v.get("not_supported") or []),
                caveats=list(v.get("caveats") or []),
            )
        )
    return out


@lru_cache(maxsize=1)
def load_registry() -> tuple[VendorAPI, ...]:
    return tuple(_load())


def find(terms: list[str], registry: list[VendorAPI] | None = None) -> list[VendorAPI]:
    """검색어와 겹치는 벤더를 찾는다. 부분일치를 허용한다.

    '스마트스토어' 로 찾든 'smartstore' 로 찾든 걸려야 실효가 있다.
    """
    reg = list(registry) if registry is not None else list(load_registry())
    wanted = [t.strip().lower() for t in terms if t and t.strip()]
    if not wanted:
        return []
    hits: list[VendorAPI] = []
    for v in reg:
        for t in wanted:
            if any(t in kw or kw in t for kw in v.keywords):
                hits.append(v)
                break
    return hits


def format_report(vendors: list[VendorAPI]) -> str:
    """capability_check 출력용. 없으면 빈 문자열."""
    if not vendors:
        return ""
    lines: list[str] = []
    for v in vendors:
        if not v.usable and not v.not_supported:
            continue
        lines.append(f"  {v.name}")
        if v.docs:
            lines.append(f"    문서: {v.docs}   비용: {v.cost or '미확인'}   상태: {v.status}")
        if v.auth:
            lines.append(f"    인증: {v.auth}")
        for s in v.supported:
            lines.append(f"    ✅ {s}")
        for s in v.not_supported:
            lines.append(f"    ❌ {s}")
        for c in v.caveats:
            lines.append(f"    ⚠  {c}")
        lines.append("")
    return "\n".join(lines)


def cdp_warning(vendors: list[VendorAPI]) -> str | None:
    """CDP 로 만들려는 것을 API 가 이미 하고 있으면 경고 문구를 돌려준다."""
    usable = [v for v in vendors if v.usable]
    if not usable:
        return None
    names = ", ".join(v.name for v in usable)
    msg = [
        f"⚠  이 도메인에는 벤더 공식 API 가 있습니다: {names}",
        "   CDP 브라우저 자동화로 만들기 전에 API 로 되는지 먼저 확인하세요.",
        "   (2026-08-15: 커머스API 로 되는 상품등록을 CDP 로 만들다 하루를 썼습니다)",
    ]
    todo = [v for v in usable if v.needs_signup]
    if todo:
        msg.append(f"   미신청: {', '.join(v.name for v in todo)} — 신청부터 검토하세요.")
    return "\n".join(msg)
