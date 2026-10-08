"""live_inputs 실행 결과 요약 출력 (leaf). [docs/module_separation_standard.md]"""

from __future__ import annotations

from pathlib import Path

from scripts.google.common.live_inputs_config import LATEST_LIVE_INPUT, LATEST_LIVE_INPUT_MANIFEST


def print_live_input_summary(result: dict, path: Path) -> None:
    print("=" * 60)
    print("Google live input")
    print("=" * 60)
    print(f"action: {result['action_key']}")
    print(f"status: {result['status']}")
    print(f"no_final_submit: {result['no_final_submit']}")
    print(f"final_clicked: {result['state_change_final_button_clicked']}")
    print(f"filled_fields: {', '.join(result['filled_fields']) if result['filled_fields'] else '-'}")
    if result["skipped_fields"]:
        print(f"skipped_fields: {', '.join(result['skipped_fields'])}")
    if result["warnings"]:
        print("warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    print(f"url: {result.get('current_url', '')}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_LIVE_INPUT}")


def print_live_manifest_summary(summary: dict, path: Path) -> None:
    print("=" * 60)
    print("Google live input manifest")
    print("=" * 60)
    print(f"status: {summary['status']}")
    print(f"no_final_submit: {summary['no_final_submit']}")
    print(f"final_clicked: {summary['state_change_final_button_clicked']}")
    print(
        "counts: "
        f"total={summary['counts']['total']} "
        f"filled={summary['counts']['filled']} "
        f"blocked={summary['counts']['blocked']} "
        f"failed={summary['counts']['failed']}"
    )
    for item in summary["items"]:
        print(f"- {item['action_key']}: {item['status']} -> {item.get('result_path', '-')}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_LIVE_INPUT_MANIFEST}")
