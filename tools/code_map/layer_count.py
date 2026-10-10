# module_category: audit
# primary_trade: common
"""층간 위반 집계 정본 — 이 스크립트 1곳만이 '층간 위반 N' 의 출처다.

기준(관리 기준): map.json 의 import_edges(실제 import 만, 문자열 언급 제외), __init__ 제외,
코드 파일(.py/.ts/.tsx/.js), 층 L1~L10, 판정 = classify_path 층번호 하위→상위(numeric).
보조 지표(참고): 레지스트리 층 + allowed_deps 방향모델(modules.py 의 '역전'; 과거 커밋 메시지의 51 이 이것).
출력: data/code_map/layer_baseline.json + stdout 한 줄. 읽기 전용.
사용: python tools/code_map/layer_count.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map.layer_rules import classify_path  # noqa: E402

OUT_DIR = ROOT / "data" / "code_map"
CODE_SUFFIX = (".py", ".ts", ".tsx", ".js")
CODE_LAYERS = {f"L{i}" for i in range(1, 11)}


def _num(layer: str) -> int:
    return int(layer[1:]) if layer[1:].isdigit() else -1


def _count(import_edges: dict, layer_of, bad_fn) -> dict:
    pairs: Counter = Counter()
    files: set[str] = set()
    for s, ts in import_edges.items():
        if PurePosixPath(s).suffix not in CODE_SUFFIX or PurePosixPath(s).name == "__init__.py":
            continue
        ls = layer_of(s)
        if ls not in CODE_LAYERS:
            continue
        for t in ts:
            if PurePosixPath(t).suffix not in CODE_SUFFIX or PurePosixPath(t).name == "__init__.py":
                continue
            lt = layer_of(t)
            if lt in CODE_LAYERS and bad_fn(ls, lt):
                pairs[f"{ls}->{lt}"] += 1
                files.add(s)
    return {"edges": sum(pairs.values()), "files": len(files), "by_pair": dict(pairs.most_common())}


def measure() -> dict:
    m = json.loads((OUT_DIR / "map.json").read_text(encoding="utf-8"))
    edges = m.get("import_edges") or m["all_edges"]
    reg_doc = json.loads((ROOT / "configs" / "module_registry.json").read_text(encoding="utf-8"))
    reg, allowed = reg_doc.get("files", {}), reg_doc.get("allowed_deps") or {}
    legacy = lambda f: classify_path(f)[0]  # noqa: E731
    registry = lambda f: reg[f]["layer"] if f in reg else classify_path(f)[0]  # noqa: E731
    return {
        "meta": {"commit": m["meta"].get("commit"), "edge_source": "import_edges"},
        "primary_management_metric": _count(edges, legacy, lambda a, b: _num(a) < _num(b)),
        "secondary_registry_allowed_deps": _count(edges, registry, lambda a, b: b not in allowed.get(a, [])),
    }


def main() -> int:
    r = measure()
    (OUT_DIR / "layer_baseline.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    p, s = r["primary_management_metric"], r["secondary_registry_allowed_deps"]
    print(f"PRIMARY files={p['files']} edges={p['edges']} | SECONDARY(registry) files={s['files']} edges={s['edges']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
