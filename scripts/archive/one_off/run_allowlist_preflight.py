"""discovery candidate JSON에 대해 allowlist preflight를 실행하는 스크립트.

Usage:
    python scripts/run_allowlist_preflight.py \
        --site-id g2b \
        --candidates tmp/candidates_g2b.json \
        --output tmp/preflight_g2b.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_orchestrator.local_agent.browser_allowlist_expansion_preflight import (
    preflight_expansion, can_auto_approve,
    VERDICT_ALLOW, VERDICT_REVIEW, VERDICT_BLOCKED,
)
from ai_orchestrator.local_agent.browser_site_registry import (
    SitePolicy, register_site, clear_all,
)


def load_site_policy(config_dir: Path, site_id: str) -> SitePolicy | None:
    config_file = config_dir / f"{site_id}.json"
    if not config_file.exists():
        return None
    with open(config_file, encoding="utf-8") as f:
        data = json.load(f)
    policy = SitePolicy(
        site_id=data["site_id"],
        label=data["label"],
        allowed_hosts=tuple(data["allowed_hosts"]),
        allowed_paths=tuple(data.get("allowed_paths", [])),
        blocked_paths=tuple(data.get("blocked_paths", [])),
    )
    return policy


def run_preflight(site_id: str, candidates_path: Path) -> list[dict]:
    with open(candidates_path, encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for entry in data.get("candidates", []):
        candidate = entry.get("candidate")
        if candidate is None:
            results.append({
                "label": entry.get("visible_label", "?"),
                "candidate_type": entry.get("candidate_type", "?"),
                "verdict": VERDICT_BLOCKED,
                "reason": "candidate 없음 (build 단계 차단)",
                "auto_approve": False,
            })
            continue

        # preflight은 site_id 키를 기대 (candidate는 source_site_id로 저장)
        enriched = dict(candidate)
        if "site_id" not in enriched:
            enriched["site_id"] = enriched.get("source_site_id", site_id)
        # site_candidate + selector_candidate 양쪽으로 전달해야 auto-register 판정 가능
        result = preflight_expansion(
            site_candidate=enriched,
            selector_candidate=enriched,
        )
        auto = can_auto_approve(result)

        results.append({
            "label": candidate.get("visible_label", "?"),
            "candidate_type": candidate.get("candidate_type", "?"),
            "selector_fingerprint": candidate.get("selector_fingerprint", "?"),
            "verdict": result.get("verdict", VERDICT_BLOCKED),
            "reason": result.get("reason", ""),
            "risk_level": result.get("risk_level", "?"),
            "auto_approve": auto,
        })
    return results


def summarize(results: list[dict]) -> dict:
    by_verdict: dict[str, int] = {VERDICT_ALLOW: 0, VERDICT_REVIEW: 0, VERDICT_BLOCKED: 0}
    auto_count = 0
    for r in results:
        v = r["verdict"]
        by_verdict[v] = by_verdict.get(v, 0) + 1
        if r["auto_approve"]:
            auto_count += 1
    return {
        "total": len(results),
        "allow": by_verdict[VERDICT_ALLOW],
        "review": by_verdict[VERDICT_REVIEW],
        "blocked": by_verdict[VERDICT_BLOCKED],
        "auto_approve": auto_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="allowlist preflight 실행")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--config-dir", type=Path, default=Path("configs/site_policies"))
    args = parser.parse_args()

    clear_all()
    policy = load_site_policy(args.config_dir, args.site_id)
    if policy:
        register_site(policy)
    else:
        print(f"[WARN] site_id={args.site_id}의 config 없음 — site registry 없이 실행")

    results = run_preflight(args.site_id, args.candidates)
    summary = summarize(results)

    print(f"\n[Preflight 결과] site_id={args.site_id}")
    print(f"  총={summary['total']}  ALLOW={summary['allow']}  REVIEW={summary['review']}  BLOCKED={summary['blocked']}  auto_approve={summary['auto_approve']}")
    print()

    for i, r in enumerate(results):
        verdict = r["verdict"]
        icon = "✅" if verdict == VERDICT_ALLOW else ("⚠️ " if verdict == VERDICT_REVIEW else "❌")
        auto = " [AUTO]" if r["auto_approve"] else ""
        print(f"  [{i+1:02d}] {icon} {verdict:<20} {r['candidate_type']:<25} {r['label']!r}{auto}")

    output_data = {
        "site_id": args.site_id,
        "summary": summary,
        "results": results,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 저장 완료: {args.output}")

    clear_all()


if __name__ == "__main__":
    main()
