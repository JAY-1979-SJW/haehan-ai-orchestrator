"""에이전트 사용량 기록·집계 (토큰 효율 설계서 2단계, 구조변경 #7).

작업(기준서 id)별 에이전트 토큰·도구 호출 수를 data/ops/agent_usage.jsonl 에 기록하고
단계별 합계를 보고한다. 기준서에 budget_tokens 를 주면 초과 시 경고.

  python tools/hooks/agent_usage.py record <spec-id> <role> <tokens> <tool_calls> [--stage S]
  python tools/hooks/agent_usage.py report [<spec-id>] [--budget N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
LOG = _ROOT / "data" / "ops" / "agent_usage.jsonl"


def record(spec_id, role, tokens, tool_calls, stage="", log=LOG):
    row = {
        "ts": int(time.time()),
        "spec": spec_id,
        "role": role,
        "stage": stage,
        "tokens": int(tokens),
        "tool_calls": int(tool_calls),
    }
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load(log=LOG):
    log = Path(log)
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


def summarize(rows, spec_id=None, budget=None):
    """(stage,role)별 합계 + 총합 + 예산 초과 경고."""
    rows = [r for r in rows if spec_id in (None, r["spec"])]
    by = {}
    for r in rows:
        k = (r.get("stage", ""), r["role"])
        t = by.setdefault(k, {"n": 0, "tokens": 0, "tool_calls": 0})
        t["n"] += 1
        t["tokens"] += r["tokens"]
        t["tool_calls"] += r["tool_calls"]
    total = sum(r["tokens"] for r in rows)
    return {
        "by": by,
        "total_tokens": total,
        "total_calls": sum(r["tool_calls"] for r in rows),
        "over_budget": bool(budget and total > budget),
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("spec")
    r.add_argument("role")
    r.add_argument("tokens", type=int)
    r.add_argument("tool_calls", type=int)
    r.add_argument("--stage", default="")
    q = sub.add_parser("report")
    q.add_argument("spec", nargs="?")
    q.add_argument("--budget", type=int)
    a = p.parse_args(argv)
    if a.cmd == "record":
        record(a.spec, a.role, a.tokens, a.tool_calls, a.stage)
        print("recorded")
        return 0
    s = summarize(load(), a.spec, a.budget)
    print("stage | role | n | tokens | tool_calls")
    for (st, ro), t in sorted(s["by"].items()):
        print(f"{st or '-'} | {ro} | {t['n']} | {t['tokens']} | {t['tool_calls']}")
    print(f"TOTAL tokens={s['total_tokens']} calls={s['total_calls']}")
    if s["over_budget"]:
        print(f"WARN: budget_tokens {a.budget} 초과")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
