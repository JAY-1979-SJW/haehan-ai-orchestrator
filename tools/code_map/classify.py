# module_category: audit
# primary_trade: common
"""분류 정본 생성 — 코드 파일마다 층(layer)·역할(role)·도메인(domain)을 내용·연결 근거로 판정.

경로 이름 추측(codebase_layer_audit.classify_path) 대신 파일 내용 신호와 코드맵 연결을 쓴다.
판정마다 reason 과 confidence(high|low) 를 남긴다. low = 사람 확인 필요.
사람이 확정한 값은 configs/module_registry.overrides.json 에 적으면 재생성해도 유지된다.

출력: configs/module_registry.json (git 추적 — 분류의 단일 출처)
사용: python tools/code_map/classify.py   (build.py 이후)
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
REGISTRY = ROOT / "configs" / "module_registry.json"
OVERRIDES = ROOT / "configs" / "module_registry.overrides.json"
CODE_SUFFIX = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs")

LAYERS = {
    "L1": "공용 계약·설정(스키마·모델·경로·상수·로깅)",
    "L2": "정책·게이트·보안",
    "L3": "외부 연동 커넥터(HTTP·API 클라이언트)",
    "L4": "범용 브라우저·자동화 엔진",
    "L5": "사이트 모듈(도메인별 자동화)",
    "L6": "업무 흐름(파이프라인·스케줄·러너)",
    "L7": "저장·감사(DB·로그)",
    "L8": "서버 API(라우터·앱)",
    "L9": "화면(admin-web)",
    "L10": "로컬 에이전트·PC 실행기",
    "L11": "테스트",
    "L12": "문서·운영 도구·보관(의존 방향 규칙 밖)",
}
# 층 사이 허용 의존(부르는 층 → 불러도 되는 층). 번호 크기가 아니라 역할 기준.
ALLOWED = {
    "L1": ["L1"],
    "L2": ["L1", "L2", "L3", "L7"],
    "L3": ["L1", "L3"],
    "L4": ["L1", "L2", "L3", "L4", "L7"],
    "L5": ["L1", "L2", "L3", "L4", "L5", "L7"],
    "L6": ["L1", "L2", "L3", "L4", "L5", "L6", "L7"],
    "L7": ["L1", "L7"],
    "L8": ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L10"],
    "L9": ["L9"],
    "L10": ["L1", "L2", "L3", "L4", "L7", "L10"],
}
DOMAINS = [
    ("smartstore", r"smartstore|commerce"),
    ("naver_blog", r"naver[/_]blog|blog_|/blog/|gonobi"),
    ("naver_cafe", r"cafe"),
    ("naver_mail", r"naver[/_]mail|mail_read"),
    ("naver_search", r"naver_search|searchad|naver_news|naver_kin|naver_openapi|shopping"),
    ("naver", r"naver"),
    ("youtube", r"youtube|yt_"),
    ("google", r"google|gmail|gcp"),
    ("instagram", r"instagram|\big[-_]|ig-comment"),
    ("kakao", r"kakao"),
    ("g2b", r"g2b|notice_radar|bid"),
    ("eum", r"\beum"),
    ("hanafax", r"hanafax|fax"),
    ("hiworks", r"hiworks"),
    ("gabia", r"gabia"),
    ("grant_radar", r"grant"),
    ("community", r"community"),
    ("marketing", r"marketing|mk_catalog"),
    ("video", r"/video/|manim"),
    ("local_agent", r"local_agent|agent/"),
    ("browser", r"browser|cdp|popup|page_helper"),
]
SHARED_NAMES = re.compile(
    r"^(_?bootstrap|config|settings|paths?|app_paths|data_paths|constants?|logger|logging_utils|errors?|exceptions?|types|schemas?|models?|enums?|common|utils?|helpers?)$"
)


def _domain(p: str) -> str:
    low = p.lower()
    for name, rx in DOMAINS:
        if re.search(rx, low):
            return name
    return "common"


def _signals(text: str) -> set[str]:
    s = set()
    if re.search(r"\bAPIRouter\(|FastAPI\(|@\w+\.(get|post|put|delete|patch)\(|Blueprint\(|Flask\(", text):
        s.add("api")
    if re.search(r"\bsqlite3\b|CREATE TABLE|SQLAlchemy|psycopg", text):
        s.add("db")
    if re.search(r"\b(requests|httpx|aiohttp)\b|urllib\.request|urlopen\(", text):
        s.add("http")
    if re.search(r"websocket|Runtime\.evaluate|playwright|cdp_|CDP|remote-debugging|Page\.navigate", text):
        s.add("browser")
    if re.search(r"^\s*(async\s+)?def |^\s*class ", text, re.M) is None:
        s.add("nodefs")
    if re.search(r"\bsubprocess\b|os\.system\(", text):
        s.add("proc")
    defs_only = re.search(r"^\s*(async\s+)?def \w", text, re.M) is None and re.search(r"^\s*class \w", text, re.M)
    if defs_only or (re.search(r"\bBaseModel\b|TypedDict|@dataclass", text) and "http" not in s and "db" not in s):
        s.add("contract")
    return s


def _classify_by_path(low, name):
    if (
        low.startswith("tests/")
        or "/tests/" in low
        or "/__tests__/" in low
        or name.startswith("test_")
        or name == "conftest.py"
        or ".test." in name
    ):
        return "L11", "test", "테스트 경로·이름", "high"
    if low.startswith(("docs/", "scripts/archive/")):
        return "L12", "archive", "문서·보관 경로", "high"
    if low.startswith(("scripts/ops/", ".githooks/", ".claude/", ".codex/")) or re.match(
        r"^(verify_|audit_|check_|smoke_|probe_)", name
    ):
        return "L12", "ops_tool", "운영·감사 도구", "high"
    return None


def _classify_by_name(pp, low, name, stem, sig):
    if low.startswith("admin-web/"):
        return "L9", "ui_bff" if "/api/" in low and name.startswith("route.") else "ui", "admin-web", "high"
    if "api" in sig and pp.suffix == ".py":
        return "L8", "api", "FastAPI/Flask 라우터·앱 정의", "high"
    if SHARED_NAMES.match(stem):
        return "L1", "shared", f"공용 기반 이름({stem})", "high"
    if "db" in sig or re.search(r"(^|_)(db|store|repository|audit_log|op_log|cache)(_|$)", stem):
        return "L7", "persistence", "DB·저장 신호", "high" if "db" in sig else "low"
    if re.search(r"workflow|pipeline|scheduler|runner|campaign|daily|batch|orchestrat", stem):
        return "L6", "workflow", "업무 흐름 이름", "high"
    return None


def _classify_by_domain(low, stem, dom, sig):
    if re.search(r"polic|gate|approval|allowlist|guard|permission|safety|risk|consent|auth", stem):
        return "L2", "policy", "정책·게이트 이름", "high"
    if low.startswith(("local_agent/", "agent/")) and dom in ("local_agent", "common", "browser"):
        return "L10", "local_agent", "로컬 에이전트 패키지", "high"
    if dom not in ("common", "browser", "local_agent") and (
        sig & {"browser", "http"} or low.startswith(("scripts/", "ai_orchestrator/connectors/"))
    ):
        return "L5", "site_module", f"도메인({dom}) 자동화", "high" if sig & {"browser", "http"} else "low"
    return None


def classify_one(p: str, text: str, main_file: bool) -> tuple[str, str, str, str]:
    """(layer, role, reason, confidence)."""
    pp = PurePosixPath(p)
    name, stem, low = pp.name, pp.stem, p.lower()
    sig = _signals(text) if text else set()
    _early = _classify_by_path(low, name)
    if _early is not None:
        return _early
    _early = _classify_by_name(pp, low, name, stem, sig)
    if _early is not None:
        return _early
    dom = _domain(p)
    _early = _classify_by_domain(low, stem, dom, sig)
    if _early is not None:
        return _early
    if "browser" in sig or dom == "browser":
        return "L4", "browser_engine", "범용 브라우저·CDP", "high"
    if "http" in sig:
        return "L3", "connector", "HTTP 클라이언트", "high"
    if "contract" in sig:
        return "L1", "contract", "정의 위주(모델·스키마·dataclass)", "high"
    if main_file:
        return "L6", "script_cli", "직접 실행 스크립트", "low"
    return "L4", "generic", "근거 부족 — 기본값", "low"


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    m = json.loads((ROOT / "data" / "code_map" / "map.json").read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    main_files = {p for p, v in m["files"].items() if v.get("own_main") or v["class"] == "CLI"}
    reg = {}
    for p in sorted(m["all_nodes"]):
        if PurePosixPath(p).suffix not in CODE_SUFFIX:
            continue
        try:
            text = (ROOT / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        layer, role, reason, conf = classify_one(p, text, p in main_files)
        entry = {
            "layer": layer,
            "role": role,
            "domain": _domain(p),
            "reason": reason,
            "confidence": conf,
            "source": "rule",
        }
        if p in overrides:
            entry.update(overrides[p])
            entry["source"] = "confirmed"
            entry["confidence"] = "high"
        reg[p] = entry
    out = {
        "_doc": "분류 정본 — 코드 파일별 층·역할·도메인. tools/code_map/classify.py 가 생성, "
        "사람 확정값은 module_registry.overrides.json 에. 교차 검증·게이트는 이 파일을 기준으로 한다.",
        "layers": LAYERS,
        "allowed_deps": ALLOWED,
        "allowed_note": "부르는 층 → 불러도 되는 층. L11(테스트)·L12(문서·도구)는 규칙 밖, __init__.py 대상은 제외.",
        "files": reg,
    }
    REGISTRY.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    lc = Counter(v["layer"] for v in reg.values())
    cc = Counter(v["confidence"] for v in reg.values())
    print(
        json.dumps(
            {
                "files": len(reg),
                "layers": dict(sorted(lc.items(), key=lambda x: int(x[0][1:]) if x[0][1:].isdigit() else 999)),
                "confidence": dict(cc),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
