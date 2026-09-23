"""NAVER-MAIL-DYNAMIC-FOLDER-DISCOVERY-CLOSEOUT-01 audit.

판정:
  PASS_NAVER_MAIL_DYNAMIC_FOLDER_DISCOVERY_CLOSEOUT
  WARN_FOLDER_POLICY_EXCLUDED
  WARN_LNB_COUNT_RECONCILIATION_REMAINS
  FAIL_SIDE_EFFECT_OCCURRED
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import folder_profile as fpr


@dataclass
class CloseoutVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_FORBIDDEN = (
    "popup/read",
    "captureScreenshot",
    "send",
    "delete",
    "trash_action",
    "spam_action",
    "download",
    "submit",
    "label_change",
)


def judge_closeout(snap: fpr.FolderProfileSnapshot, *, side_effect_log: list[str] | None = None) -> CloseoutVerdict:
    side_effect_log = side_effect_log or []
    hits = [e for e in side_effect_log if any(b in e for b in _FORBIDDEN)]
    if hits:
        return CloseoutVerdict(False, "FAIL_SIDE_EFFECT_OCCURRED", reasons=[f"side_effect:{hits[:3]}"])

    metrics = {
        "folder_count": len(snap.folders),
        "collectable_n": len(snap.collectable_folders),
        "excluded_n": len(snap.policy_excluded_folders),
        "unknown_n": len(snap.unknown_folders),
        "non_folder_menus_n": len(snap.non_folder_menus),
        "smart_group_headers_n": len(snap.smart_group_headers),
        "reconciliation_explained": (snap.reconciliation or {}).get("explained", False),
        "raw_lnb_sum": (snap.reconciliation or {}).get("raw_lnb_sum"),
        "reconciled_real_sum": (snap.reconciliation or {}).get("reconciled_real_sum"),
    }

    # 1) unknown_folders 0 인지
    if snap.unknown_folders:
        return CloseoutVerdict(
            False,
            "WARN_LNB_COUNT_RECONCILIATION_REMAINS"
            if (snap.reconciliation and not snap.reconciliation.get("explained"))
            else "WARN_FOLDER_POLICY_EXCLUDED",
            reasons=[f"unknown_present:{snap.unknown_folders}"],
            metrics=metrics,
        )

    # 2) reconciliation 미설명 시
    if snap.reconciliation and not snap.reconciliation.get("explained"):
        return CloseoutVerdict(
            False,
            "WARN_LNB_COUNT_RECONCILIATION_REMAINS",
            reasons=[f"formula:{snap.reconciliation.get('formula')}"],
            metrics=metrics,
        )

    # 3) 정책 제외된 실제 폴더가 있더라도 안전한 처리이면 PASS 가능
    # 단, 단순 excluded 갯수만으로 WARN 처리하지는 않음 (정상)
    return CloseoutVerdict(
        True,
        "PASS_NAVER_MAIL_DYNAMIC_FOLDER_DISCOVERY_CLOSEOUT",
        reasons=[],
        metrics=metrics,
    )


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot_json", type=Path)
    args = ap.parse_args(argv)
    d = json.loads(args.snapshot_json.read_text(encoding="utf-8"))
    snap = fpr.FolderProfileSnapshot(
        schema_version=d.get("schema_version", ""),
        run_id=d.get("run_id", ""),
        account_hint_masked=d.get("account_hint_masked", ""),
        discovered_at_iso=d.get("discovered_at_iso", ""),
        lnb_total_unread=d.get("lnb_total_unread", -1),
        folders=d.get("folders", []),
        groups=d.get("groups", {}),
        unknown_folders=d.get("unknown_folders", []),
        policy_excluded_folders=d.get("policy_excluded_folders", []),
        collectable_folders=d.get("collectable_folders", []),
        warnings=d.get("warnings", []),
        verdict=d.get("verdict", ""),
        non_folder_menus=d.get("non_folder_menus", []),
        smart_group_headers=d.get("smart_group_headers", []),
        reconciliation=d.get("reconciliation", {}),
    )
    v = judge_closeout(snap)
    print(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
