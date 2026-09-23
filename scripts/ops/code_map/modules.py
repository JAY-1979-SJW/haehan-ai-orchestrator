# module_category: audit
# primary_trade: common
"""코드맵 × 선언된 골격 교차 검증 + 모듈 단위 세부 지도.

입력: data/code_map/map.json(전체 노드·엣지), data/code_map/run_ledger.json(실행 점검),
      선언 골격 = codebase_layer_audit.classify_path(레이어) · _FORBIDDEN_IMPORT_PAIRS(금지 import)
      · configs/module_boundaries.json(모듈 경계) · CLAUDE.md 규칙(상위→하위 의존만 허용)
출력: data/code_map/modules.json, data/code_map/modules.md
사용: python scripts/ops/code_map/modules.py   (build.py·runcheck.py 이후)
읽기 전용.
"""

from __future__ import annotations

import contextlib
import json
import sys
from collections import Counter, defaultdict
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.codebase_layer_audit import _FORBIDDEN_IMPORT_PAIRS, classify_path  # noqa: E402

OUT_DIR = ROOT / "data" / "code_map"
CODE_SUFFIX = (".py", ".ts", ".tsx", ".js")
CODE_LAYERS = {f"L{i}" for i in range(1, 11)}  # L0 런타임·L11 테스트·L12 문서는 방향 규칙 밖
RUN_LEVELS = ("R0", "R1")


def module_of(path: str) -> str:
    """폴더 기준 모듈 id (최대 3단계). connectors 평면 파일은 파일명 첫 토큰(도메인)으로 묶는다."""
    p = PurePosixPath(path)
    parts = p.parts
    if len(parts) == 1:
        return "(root)"
    if parts[:2] == ("ai_orchestrator", "connectors") and len(parts) == 3:
        return f"ai_orchestrator/connectors/{p.stem.split('_')[0]}*"
    if parts[0] == "admin-web" and len(parts) > 3 and parts[1] == "src":
        return "/".join(parts[: min(len(parts) - 1, 4)])
    return "/".join(parts[: min(len(parts) - 1, 3)])


def _layer_num(layer: str) -> int:
    return int(layer[1:]) if layer.startswith("L") and layer[1:].isdigit() else -1


def _dotted(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else ""


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    m = json.loads((OUT_DIR / "map.json").read_text(encoding="utf-8"))
    ledger_p = OUT_DIR / "run_ledger.json"
    ledger = json.loads(ledger_p.read_text(encoding="utf-8"))["nodes"] if ledger_p.exists() else {}
    bounds = json.loads((ROOT / "configs" / "module_boundaries.json").read_text(encoding="utf-8"))
    nodes = m["all_nodes"]
    edges = m["all_edges"]
    files = sorted(nodes)

    layer = {f: classify_path(f) for f in files}
    mod = {f: module_of(f) for f in files}

    # ── 1. 레이어 역전: 코드 파일 간 엣지에서 하위(번호 작음) → 상위(번호 큼) ──────────────
    inv_pairs: Counter = Counter()
    inv_samples: dict[str, list[str]] = defaultdict(list)
    for s, ts in edges.items():
        if s not in layer or PurePosixPath(s).suffix not in (".py", ".ts", ".tsx", ".js"):
            continue
        ls = layer[s][0]
        if ls not in CODE_LAYERS:
            continue
        for t in ts:
            if t not in layer:
                continue
            lt = layer[t][0]
            if PurePosixPath(t).suffix not in CODE_SUFFIX:
                continue
            if lt in CODE_LAYERS and _layer_num(ls) < _layer_num(lt):
                key = f"{ls}->{lt}"
                inv_pairs[key] += 1
                if len(inv_samples[key]) < 5:
                    inv_samples[key].append(f"{s} -> {t}")

    # ── 2. 선언된 금지 import 쌍 위반 ───────────────────────────────────────────────
    forbidden_hits = []
    for s, ts in edges.items():
        ds = _dotted(s)
        if not ds:
            continue
        for src_prefix, bad_prefix, reason in _FORBIDDEN_IMPORT_PAIRS:
            if not ds.startswith(src_prefix):
                continue
            for t in ts:
                if _dotted(t).startswith(bad_prefix):
                    forbidden_hits.append({"src": s, "dst": t, "rule": reason})

    # ── 3. 레이어 판정 불가 ───────────────────────────────────────────────────────
    unknown_layer = sorted(f for f, (lv, _) in layer.items() if not lv.startswith("L") or lv == "UNKNOWN")

    # ── 4. 모듈 경계 선언 대조 ──────────────────────────────────────────────────
    declared = []
    covered: set[str] = set()
    for b in bounds["modules"]:
        missing, members = [], set()
        for pat in b["paths"]:
            hit = {f for f in files if f == pat or (pat.endswith("/") and f.startswith(pat)) or fnmatch(f, pat)}
            if not hit:
                missing.append(pat)
            members |= hit
        covered |= members
        lay_mix = Counter(layer[f][0] for f in members)
        declared.append(
            {
                "name": b["name"],
                "declared_layer": b["layer"],
                "files": len(members),
                "missing_paths": missing,
                "actual_layers": dict(lay_mix),
                "layer_mismatch": sum(v for k, v in lay_mix.items() if k != b["layer"]),
            }
        )
    code_files = [f for f in files if PurePosixPath(f).suffix in (".py", ".ts", ".tsx", ".js")]
    unassigned = len([f for f in code_files if f not in covered])

    # ── 5. 실행 교차 ─────────────────────────────────────────────────────────────
    live_import_fail = sorted(
        f for f in files if nodes[f]["class"] == "LIVE" and ledger.get(f, {}).get("R0", {}).get("status") == "FAIL"
    )

    # ── 모듈 지도 ────────────────────────────────────────────────────────────────
    M: dict[str, dict] = defaultdict(
        lambda: {
            "files": 0,
            "lines": 0,
            "classes": Counter(),
            "layers": Counter(),
            "exts": Counter(),
            "run": {lv: Counter() for lv in RUN_LEVELS},
            "tests": set(),
            "out": Counter(),
            "in": Counter(),
            "intra": 0,
        }
    )
    for f in files:
        x = M[mod[f]]
        x["files"] += 1
        x["classes"][nodes[f]["class"]] += 1
        x["layers"][layer[f][0]] += 1
        x["exts"][nodes[f]["ext"]] += 1
        with contextlib.suppress(OSError, UnicodeDecodeError):
            if PurePosixPath(f).suffix in (".py", ".ts", ".tsx", ".js"):
                x["lines"] += sum(1 for _ in (ROOT / f).open(encoding="utf-8", errors="replace"))
        for lv in RUN_LEVELS:
            st = ledger.get(f, {}).get(lv, {}).get("status")
            if st:
                x["run"][lv][st] += 1
    for s, ts in edges.items():
        if s not in mod or PurePosixPath(s).suffix not in CODE_SUFFIX:  # 모듈 의존은 코드→코드만
            continue
        ms = mod[s]
        is_test = nodes[s]["class"] == "TEST_ONLY" or "/tests/" in s or s.startswith("tests/")
        for t in ts:
            if t not in mod or PurePosixPath(t).suffix not in CODE_SUFFIX:
                continue
            mt = mod[t]
            if is_test and mt != ms:
                M[mt]["tests"].add(s)
                continue
            if mt == ms:
                M[ms]["intra"] += 1
            else:
                M[ms]["out"][mt] += 1
                M[mt]["in"][ms] += 1
    modules = {}
    for k, x in M.items():
        out_n = sum(x["out"].values())
        modules[k] = {
            "files": x["files"],
            "lines": x["lines"],
            "classes": dict(x["classes"]),
            "layers": dict(x["layers"]),
            "dominant_layer": x["layers"].most_common(1)[0][0],
            "exts": dict(x["exts"].most_common(6)),
            "run": {lv: dict(c) for lv, c in x["run"].items() if c},
            "tests": len(x["tests"]),
            "fan_out": len(x["out"]),
            "fan_in": len(x["in"]),
            "cohesion": round(x["intra"] / (x["intra"] + out_n), 2) if (x["intra"] + out_n) else None,
            "top_out": x["out"].most_common(5),
            "top_in": x["in"].most_common(5),
        }
    mod_edges = Counter()
    for k, x in M.items():
        for t, n in x["out"].items():
            mod_edges[(k, t)] += n
    cycles = sorted({tuple(sorted((a, b))) for (a, b) in mod_edges if (b, a) in mod_edges})

    result = {
        "meta": {"map_generated_at": m["meta"]["generated_at"], "commit": m["meta"]["commit"]},
        "crosscheck": {
            "layer_inversions": {
                "total": sum(inv_pairs.values()),
                "by_pair": dict(inv_pairs.most_common()),
                "samples": dict(inv_samples),
            },
            "forbidden_import_hits": forbidden_hits,
            "unknown_layer_files": unknown_layer,
            "declared_modules": declared,
            "code_files": len(code_files),
            "code_files_unassigned_to_declared_module": unassigned,
            "live_but_import_fails": live_import_fail,
            "module_cycles": [list(c) for c in cycles],
        },
        "modules": dict(sorted(modules.items())),
        "module_edges": [{"from": a, "to": b, "n": n} for (a, b), n in mod_edges.most_common()],
    }
    (OUT_DIR / "modules.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    c = result["crosscheck"]
    lines = [
        f"# 골격 교차 검증·모듈 지도 — {m['meta']['generated_at']} @ {m['meta']['commit']}",
        "",
        "## 교차 검증",
        "",
        f"- 레이어 역전(하위→상위 의존): **{c['layer_inversions']['total']}** — {c['layer_inversions']['by_pair']}",
        f"- 선언된 금지 import 위반: **{len(forbidden_hits)}**",
        f"- 레이어 판정 불가 파일: {len(unknown_layer)}",
        f"- 선언 모듈에 속하지 않은 코드 파일: {unassigned} / {len(code_files)}",
        f"- LIVE 인데 import 실패: {len(live_import_fail)}",
        f"- 모듈 간 양방향(순환) 쌍: {len(cycles)}",
        "",
        "| 선언 모듈 | 선언 층 | 파일 | 실제 층 구성 | 층 불일치 | 없는 경로 |",
        "|---|---|---|---|---|---|",
        *[
            f"| {d['name']} | {d['declared_layer']} | {d['files']} | {d['actual_layers']} | {d['layer_mismatch']} | "
            f"{', '.join(d['missing_paths']) or '-'} |"
            for d in declared
        ],
        "",
        "## 모듈 (파일 많은 순)",
        "",
        "| 모듈 | 파일 | 줄 | 주 층 | 분류 | R0 | 테스트 | 의존 out/in | 응집도 |",
        "|---|---|---|---|---|---|---|---|---|",
        *[
            f"| {k} | {v['files']} | {v['lines']} | {v['dominant_layer']} | {v['classes']} | {v['run'].get('R0', {})} | "
            f"{v['tests']} | {v['fan_out']}/{v['fan_in']} | {v['cohesion']} |"
            for k, v in sorted(modules.items(), key=lambda kv: -kv[1]["files"])[:80]
        ],
    ]
    (OUT_DIR / "modules.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, (list, dict)) else len(v)) for k, v in c.items()}, ensure_ascii=False))
    print(f"inversions={c['layer_inversions']['total']} by_pair={c['layer_inversions']['by_pair']}")
    print(f"modules={len(modules)} module_edges={len(mod_edges)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
