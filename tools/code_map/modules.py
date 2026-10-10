# module_category: audit
# primary_trade: common
"""코드맵 × 선언된 골격 교차 검증 + 모듈 단위 세부 지도.

입력: data/code_map/map.json(전체 노드·엣지), data/code_map/run_ledger.json(실행 점검),
      선언 골격 = codebase_layer_audit.classify_path(레이어) · _FORBIDDEN_IMPORT_PAIRS(금지 import)
      · configs/module_boundaries.json(모듈 경계) · CLAUDE.md 규칙(상위→하위 의존만 허용)
출력: data/code_map/modules.json, data/code_map/modules.md
사용: python tools/code_map/modules.py   (build.py·runcheck.py 이후)
읽기 전용.
"""

from __future__ import annotations

import contextlib
import json
import sys
from collections import Counter, defaultdict
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map.layer_rules import _FORBIDDEN_IMPORT_PAIRS, classify_path  # noqa: E402

OUT_DIR = ROOT / "data" / "code_map"
CYCLE_EXCEPTIONS_FILE = ROOT / "configs" / "cycle_exceptions.json"
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


# 2026-09-29 STD-08(복잡도) 리팩터: 원래 main() 하나(C901=38)에 있던 각 단계(원본 주석의
# "1.~5." + 모듈 지도 집계 + 결과 조립 + 마크다운 렌더)를 아래 함수들로 분리했다. 로직·순서·
# 자료구조·문자열은 그대로이고, main() 은 이 함수들을 순서대로 호출·조립만 한다.


def _load_map_data() -> tuple[dict, dict, dict]:
    m = json.loads((OUT_DIR / "map.json").read_text(encoding="utf-8"))
    ledger_p = OUT_DIR / "run_ledger.json"
    ledger = json.loads(ledger_p.read_text(encoding="utf-8"))["nodes"] if ledger_p.exists() else {}
    bounds = json.loads((ROOT / "configs" / "module_boundaries.json").read_text(encoding="utf-8"))
    return m, ledger, bounds


def _load_layer_and_module_maps(files: list[str]) -> tuple[dict, dict | None, dict[str, tuple], dict[str, tuple]]:
    reg_p = ROOT / "configs" / "module_registry.json"
    reg_doc = json.loads(reg_p.read_text(encoding="utf-8")) if reg_p.exists() else {}
    registry = reg_doc.get("files", {})
    allowed = reg_doc.get("allowed_deps")
    legacy_layer = {f: classify_path(f) for f in files}  # 옛 경로 추측 판정 — 비교용
    layer = {f: ((registry[f]["layer"], registry[f]["reason"]) if f in registry else legacy_layer[f]) for f in files}
    return registry, allowed, legacy_layer, layer


def _layer_inversion_target(t: str, layer: dict[str, tuple], ls: str, allowed: dict | None) -> str | None:
    """대상 t 가 ls 기준 금지된 하위 레이어 의존이면 그 레이어(lt)를, 아니면 None을 반환.

    _find_layer_inversions 의 안쪽 for 문 본문을 분리(2026-09-29 STD-08: C901=11>10, 바깥 for
    문의 판정도 함께 세어져 있었다). 판정 로직·순서는 그대로.
    """
    if t not in layer:
        return None
    lt = layer[t][0]
    if PurePosixPath(t).suffix not in CODE_SUFFIX:
        return None
    if PurePosixPath(t).name == "__init__.py":  # 패키지 초기화는 구조적 연결 — 방향 검사 제외
        return None
    bad = (lt not in allowed.get(ls, [])) if allowed else (_layer_num(ls) < _layer_num(lt))
    return lt if lt in CODE_LAYERS and bad else None


def _is_shim_file(s: str) -> bool:
    """`# haehan-shim:` 로 시작하는 1줄 경로-포워딩 호환 파일인가(scripts/ops/make_shim.py 가
    만듦). shim 은 메커니즘상 항상 "낮은 층 shim → 실제(보통 더 높은 층) 모듈"을 가리켜 층
    역전으로 잡힌다(PR #165 분석, 2026-10-09 — verify_change.py·tool_home_gate.py 의 같은
    종류 판정에서 이미 제외함)."""
    try:
        with (ROOT / s).open(encoding="utf-8", errors="replace") as f:
            return f.readline().startswith("# haehan-shim:")
    except OSError:
        return False


def _find_layer_inversions(
    import_edges: dict, layer: dict[str, tuple], allowed: dict | None
) -> tuple[Counter, dict[str, list[str]]]:
    """1. 레이어 역전: 코드 파일 간 엣지에서 하위(번호 작음) → 상위(번호 큼)."""
    inv_pairs: Counter = Counter()
    inv_samples: dict[str, list[str]] = defaultdict(list)
    for s, ts in import_edges.items():
        if s not in layer or PurePosixPath(s).suffix not in (".py", ".ts", ".tsx", ".js"):
            continue
        if PurePosixPath(s).name == "__init__.py":  # 패키지 재수출은 방향 검사 제외
            continue
        if _is_shim_file(s):
            continue
        ls = layer[s][0]
        if ls not in CODE_LAYERS:
            continue
        for t in ts:
            lt = _layer_inversion_target(t, layer, ls, allowed)
            if lt is None:
                continue
            key = f"{ls}->{lt}"
            inv_pairs[key] += 1
            if len(inv_samples[key]) < 5:
                inv_samples[key].append(f"{s} -> {t}")
    return inv_pairs, inv_samples


def _count_legacy_inversions(edges: dict, legacy_layer: dict[str, tuple]) -> int:
    legacy_inv = 0
    for s_, ts_ in edges.items():
        if PurePosixPath(s_).suffix not in CODE_SUFFIX or legacy_layer.get(s_, ("",))[0] not in CODE_LAYERS:
            continue
        for t_ in ts_:
            if t_ in legacy_layer and PurePosixPath(t_).suffix in CODE_SUFFIX:
                a_, b_ = legacy_layer[s_][0], legacy_layer[t_][0]
                if b_ in CODE_LAYERS and _layer_num(a_) < _layer_num(b_):
                    legacy_inv += 1
    return legacy_inv


def _find_forbidden_import_hits(edges: dict) -> list[dict]:
    """2. 선언된 금지 import 쌍 위반."""
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
    return forbidden_hits


def _crosscheck_declared_modules(bounds: dict, files: list[str], layer: dict[str, tuple]) -> tuple[list[dict], set]:
    """4. 모듈 경계 선언 대조."""
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
    return declared, covered


def _make_module_accumulator() -> dict:
    return {
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


def _accumulate_module_file_stats(
    files: list[str], mod: dict[str, str], nodes: dict, layer: dict[str, tuple], ledger: dict, m_acc: dict
) -> None:
    for f in files:
        x = m_acc[mod[f]]
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


def _accumulate_module_edges(edges: dict, mod: dict[str, str], nodes: dict, m_acc: dict) -> None:
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
                m_acc[mt]["tests"].add(s)
                continue
            if mt == ms:
                m_acc[ms]["intra"] += 1
            else:
                m_acc[ms]["out"][mt] += 1
                m_acc[mt]["in"][ms] += 1


def _summarize_modules(m_acc: dict) -> dict[str, dict]:
    modules = {}
    for k, x in m_acc.items():
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
    return modules


def _module_edges_and_cycles(m_acc: dict) -> tuple[Counter, list[tuple[str, str]]]:
    mod_edges = Counter()
    for k, x in m_acc.items():
        for t, n in x["out"].items():
            mod_edges[(k, t)] += n
    cycles = sorted({tuple(sorted((a, b))) for (a, b) in mod_edges if (b, a) in mod_edges})
    return mod_edges, cycles


def _is_ancestor_init_edge(src: str, dst: str) -> bool:
    """dst 가 src 의 조상(또는 같은) 패키지의 __init__.py 인가 — a/b/c.py 를 import 하면 a/__init__.py 도 실행되는 암묵 간선."""
    d = PurePosixPath(dst)
    if d.name != "__init__.py":
        return False
    pkg = str(d.parent)
    sdir = str(PurePosixPath(src).parent)
    return pkg != "." and (sdir == pkg or sdir.startswith(pkg + "/"))


def _cycle_edges(import_edges: dict) -> dict:
    """폴더 순환 계산에 쓰는 간선 — 실제 import 만(경로 문자열 언급은 의존이 아니다), 조상 패키지 __init__ 로 가는 암묵 간선은 뺀다.

    층간 위반(_find_layer_inversions)과 같은 기준이다(2026-10-07 대표님 승인). 예전에는 all_edges(문자열 경로 언급 포함)로 재서
    '문자열로만 서로 언급하는' 쌍이 순환으로 잡혔고, 조상 __init__ 간선이 상위↔하위 폴더 순환을 만들었다.

    2026-10-09: shim 파일(`# haehan-shim:`)에서 나가는 간선도 뺀다 — shim 은 메커니즘상 항상
    "옛 폴더 shim → 실제 폴더"를 가리켜 가짜 순환을 만든다(_find_layer_inversions 와 같은 이유로
    제외, verify_change.py·tool_home_gate.py 에서도 이미 같은 판정에 적용함).
    """
    return {
        s: [t for t in ts if not _is_ancestor_init_edge(s, t)]
        for s, ts in import_edges.items()
        if not _is_shim_file(s)
    }


def _load_cycle_exceptions() -> set[tuple[str, str]]:
    """configs/cycle_exceptions.json(승인된 '의도적 설계' 순환 — 플러그인 레지스트리처럼 폴더
    분리가 비용 대비 과한 경우) — 늘리는 변경은 지휘창 승인 필요, 줄이는 방향(해소)은 자유."""
    if not CYCLE_EXCEPTIONS_FILE.exists():
        return set()
    try:
        data = json.loads(CYCLE_EXCEPTIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {tuple(sorted(e["pair"])) for e in data.get("exceptions", [])}


def _cycle_pairs(import_edges: dict, mod: dict[str, str], nodes: dict) -> list[tuple[str, str]]:
    """실제 import 기준 폴더 순환 쌍(정렬된 (a, b) 목록) — 승인된 예외(cycle_exceptions.json)는 뺀다."""
    acc: dict[str, dict] = defaultdict(_make_module_accumulator)
    _accumulate_module_edges(_cycle_edges(import_edges), mod, nodes, acc)
    cycles = _module_edges_and_cycles(acc)[1]
    exceptions = _load_cycle_exceptions()
    return [c for c in cycles if tuple(sorted(c)) not in exceptions]


def _build_result(m: dict, ctx: dict, modules: dict[str, dict], mod_edges: Counter) -> dict:
    """ctx 는 crosscheck 계산 단계들의 출력을 모은 딕셔너리(2026-09-29 STD-08: PLR0913=15>6,
    main() 에서 그대로 딕셔너리로 모아 넘긴다 — 각 키의 의미는 아래 crosscheck 필드명과 동일)."""
    registry, allowed = ctx["registry"], ctx["allowed"]
    inv_pairs, inv_samples = ctx["inv_pairs"], ctx["inv_samples"]
    return {
        "meta": {"map_generated_at": m["meta"]["generated_at"], "commit": m["meta"]["commit"]},
        "crosscheck": {
            "layer_source": "configs/module_registry.json" if registry else "classify_path(legacy)",
            "legacy_path_guess_inversions": ctx["legacy_inv"],
            "direction_model": "registry allowed_deps" if allowed else "numeric order",
            "layer_inversions": {
                "total": sum(inv_pairs.values()),
                "by_pair": dict(inv_pairs.most_common()),
                "samples": dict(inv_samples),
            },
            "forbidden_import_hits": ctx["forbidden_hits"],
            "unknown_layer_files": ctx["unknown_layer"],
            "declared_modules": ctx["declared"],
            "code_files": len(ctx["code_files"]),
            "code_files_unassigned_to_declared_module": ctx["unassigned"],
            "live_but_import_fails": ctx["live_import_fail"],
            "module_cycles": [list(c) for c in ctx["cycles"]],
        },
        "modules": dict(sorted(modules.items())),
        "module_edges": [{"from": a, "to": b, "n": n} for (a, b), n in mod_edges.most_common()],
    }


def _render_markdown_report(result: dict, m: dict, modules: dict[str, dict]) -> str:
    # result["crosscheck"] 가 이미 아래에 필요한 값을 전부 담고 있어(2026-09-29 STD-08:
    # PLR0913=9>6, _build_result 가 만든 값을 그대로 재사용) 원본처럼 개별 인자로 받지 않는다.
    c = result["crosscheck"]
    declared = c["declared_modules"]
    lines = [
        f"# 골격 교차 검증·모듈 지도 — {m['meta']['generated_at']} @ {m['meta']['commit']}",
        "",
        "## 교차 검증",
        "",
        f"- 레이어 역전(하위→상위 의존): **{c['layer_inversions']['total']}** — {c['layer_inversions']['by_pair']}",
        f"- 선언된 금지 import 위반: **{len(c['forbidden_import_hits'])}**",
        f"- 레이어 판정 불가 파일: {len(c['unknown_layer_files'])}",
        f"- 선언 모듈에 속하지 않은 코드 파일: {c['code_files_unassigned_to_declared_module']} / {c['code_files']}",
        f"- LIVE 인데 import 실패: {len(c['live_but_import_fails'])}",
        f"- 모듈 간 양방향(순환) 쌍: {len(c['module_cycles'])}",
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
    return "\n".join(lines)


def _crosscheck_summary(c: dict) -> dict:
    """crosscheck 요약 줄용 값: 목록은 길이, 'total' 이 있는 dict(layer_inversions 등)는 그 total, 그 밖의 dict 는 키 수.

    예전에는 dict 를 모두 len() 으로 세어 layer_inversions({total, by_pair, ...})가 키 개수 3 으로 찍혔다 —
    실제 위반이 30건이어도 '3' 으로 보이는 오보(2026-10-07 기준선 감사).
    """
    out: dict = {}
    for k, v in c.items():
        if isinstance(v, dict) and "total" in v:
            out[k] = v["total"]
        elif isinstance(v, (list, dict)):
            out[k] = len(v)
        else:
            out[k] = v
    return out


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    m, ledger, bounds = _load_map_data()
    nodes = m["all_nodes"]
    edges = m["all_edges"]
    # 층간 방향은 실제 import 로만 판정(문자열 경로 언급은 의존이 아님) — 옛 지도면 전체 엣지로 대체
    import_edges = m.get("import_edges", edges)
    files = sorted(nodes)

    registry, allowed, legacy_layer, layer = _load_layer_and_module_maps(files)
    mod = {f: module_of(f) for f in files}

    inv_pairs, inv_samples = _find_layer_inversions(import_edges, layer, allowed)
    legacy_inv = _count_legacy_inversions(edges, legacy_layer)
    forbidden_hits = _find_forbidden_import_hits(edges)
    # ── 3. 레이어 판정 불가 ───────────────────────────────────────────────────────
    unknown_layer = sorted(f for f, (lv, _) in layer.items() if not lv.startswith("L") or lv == "UNKNOWN")
    declared, covered = _crosscheck_declared_modules(bounds, files, layer)
    code_files = [f for f in files if PurePosixPath(f).suffix in (".py", ".ts", ".tsx", ".js")]
    unassigned = len([f for f in code_files if f not in covered])

    # ── 5. 실행 교차 ─────────────────────────────────────────────────────────────
    live_import_fail = sorted(
        f for f in files if nodes[f]["class"] == "LIVE" and ledger.get(f, {}).get("R0", {}).get("status") == "FAIL"
    )

    # ── 모듈 지도 ────────────────────────────────────────────────────────────────
    m_acc: dict[str, dict] = defaultdict(_make_module_accumulator)
    _accumulate_module_file_stats(files, mod, nodes, layer, ledger, m_acc)
    _accumulate_module_edges(edges, mod, nodes, m_acc)
    modules = _summarize_modules(m_acc)
    mod_edges, _all_edge_cycles = _module_edges_and_cycles(
        m_acc
    )  # 모듈 통계용(문자열 언급 포함) — 순환 판정에는 쓰지 않는다
    cycles = _cycle_pairs(import_edges, mod, nodes)

    ctx = {
        "registry": registry,
        "allowed": allowed,
        "legacy_inv": legacy_inv,
        "inv_pairs": inv_pairs,
        "inv_samples": inv_samples,
        "forbidden_hits": forbidden_hits,
        "unknown_layer": unknown_layer,
        "declared": declared,
        "code_files": code_files,
        "unassigned": unassigned,
        "live_import_fail": live_import_fail,
        "cycles": cycles,
    }
    result = _build_result(m, ctx, modules, mod_edges)
    (OUT_DIR / "modules.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    md = _render_markdown_report(result, m, modules)
    (OUT_DIR / "modules.md").write_text(md, encoding="utf-8")

    c = result["crosscheck"]
    print(json.dumps(_crosscheck_summary(c), ensure_ascii=False))
    print(f"inversions={c['layer_inversions']['total']} by_pair={c['layer_inversions']['by_pair']}")
    print(f"modules={len(modules)} module_edges={len(mod_edges)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
