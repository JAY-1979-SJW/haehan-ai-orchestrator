"""NAVER-MAIL-DYNAMIC-FOLDER-DISCOVERY-01 audit."""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import folder_policy as fp
from scripts.naver.mail import folder_profile as fpr


@dataclass
class DiscoveryVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_FORBIDDEN = ("popup/read", "captureScreenshot",
              "send", "delete", "trash_action", "spam_action", "download",
              "submit", "label_change")


def judge(snap: "fpr.FolderProfileSnapshot",
          *, side_effect_log: list[str] | None = None
          ) -> DiscoveryVerdict:
    side_effect_log = side_effect_log or []
    hits = [e for e in side_effect_log
            if any(b in e for b in _FORBIDDEN)]
    if hits:
        return DiscoveryVerdict(False, "FAIL_SIDE_EFFECT_OCCURRED",
                                reasons=[f"side_effect:{hits[:3]}"])

    metrics = {
        "folder_count": len(snap.folders),
        "collectable_n": len(snap.collectable_folders),
        "excluded_n": len(snap.policy_excluded_folders),
        "unknown_n": len(snap.unknown_folders),
        "lnb_total_unread": snap.lnb_total_unread,
    }

    # 1) schema
    from dataclasses import asdict
    missing = fpr.validate_schema(asdict(snap))
    if missing:
        return DiscoveryVerdict(False, "FAIL_SCHEMA_MISSING",
                                reasons=[f"schema_missing:{missing}"],
                                metrics=metrics)

    # 2) collectable 폴더 존재해야 함 (최소 inbox)
    has_inbox = any(f.get("kind") == fp.KIND_INBOX for f in snap.folders)
    if not has_inbox:
        return DiscoveryVerdict(False, "WARN_NO_INBOX_DETECTED",
                                reasons=["inbox_folder_not_detected"],
                                metrics=metrics)

    # 3) unknown 폴더 처리 — 정책으로 excluded 됐는지
    unknown_collectable = [
        f for f in snap.folders
        if f.get("kind") == fp.KIND_UNKNOWN and f.get("is_collectable")
    ]
    if unknown_collectable:
        return DiscoveryVerdict(False, "WARN_UNKNOWN_FOLDER_DETECTED",
                                reasons=[f"unknown_collectable:{[f['name'] for f in unknown_collectable]}"],
                                metrics=metrics)

    # 4) policy_excluded 가 많은데 unknown 도 있으면 WARN_FOLDER_POLICY_EXCLUDED
    if snap.unknown_folders:
        return DiscoveryVerdict(False, "WARN_FOLDER_POLICY_EXCLUDED",
                                reasons=[f"unknown_present_but_excluded:{snap.unknown_folders}"],
                                metrics=metrics)

    return DiscoveryVerdict(True, "PASS_NAVER_MAIL_DYNAMIC_FOLDER_DISCOVERY",
                            reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse, json
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
    )
    v = judge(snap)
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
