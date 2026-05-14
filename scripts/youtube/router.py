"""YouTube recording/upload router."""
from __future__ import annotations

from . import recording, uploader

__status__ = {
    "tasks": {
        "record prepare": "done",
        "record execute": "approval_gated",
        "upload prepare": "done",
        "upload execute": "approval_gated",
        "upload verify": "done",
    },
    "note": "Recording and upload are separated. Upload defaults to dry-run and requires explicit approval.",
}


def run_youtube(task: str, sub: str, args: list[str]) -> None:
    match task:
        case "record" | "recording":
            _cmd_record(sub or "prepare", args)
        case "upload":
            _cmd_upload(sub or "prepare", args)
        case "status":
            print(__status__)
        case _:
            print(f"  [error] unknown youtube task: {task}")


def _cmd_record(sub: str, args: list[str]) -> None:
    if sub == "prepare":
        values = uploader.parse_kv_args(args)
        plan, path = recording.prepare_recording_plan(values)
        print("=" * 60)
        print("YouTube recording prepare")
        print("=" * 60)
        print(f"ready_for_approval: {plan['ready_for_approval']}")
        print(f"output: {plan['recording']['output_path']}")
        print(f"ffmpeg_found: {plan['recording']['ffmpeg_found']}")
        print(f"saved: {path}")
        print(f"execute: python scripts\\cdp_client.py youtube record execute {path} --approved --confirm={recording.APPROVAL_PHRASE}")
        return
    if sub == "execute":
        if not args:
            print("  [error] usage: youtube record execute <plan_path> --approved --confirm=YOUTUBE_APPROVED_RECORD")
            return
        plan_path = args[0]
        approved = "--approved" in args
        confirm = _confirm_arg(args)
        result, path = recording.execute_recording_plan(plan_path, approved=approved, confirm=confirm)
        print("=" * 60)
        print("YouTube recording execute")
        print("=" * 60)
        print(f"status: {result['status']}")
        print(f"state_change: {result['state_change']}")
        print(f"output: {result['output_path']}")
        print(f"saved: {path}")
        return
    print(f"  [error] unknown youtube record task: {sub}")


def _cmd_upload(sub: str, args: list[str]) -> None:
    if sub == "prepare":
        if not args:
            print("  [error] usage: youtube upload prepare <local_video> title=... description=... privacy=private")
            return
        local_path = args[0]
        values = uploader.parse_kv_args(args[1:])
        plan, path = uploader.prepare_upload_plan(local_path, values)
        print("=" * 60)
        print("YouTube upload prepare")
        print("=" * 60)
        print(f"ready_for_approval: {plan['ready_for_approval']}")
        print(f"local_path: {plan['local_path']}")
        print(f"privacy: {plan['metadata']['privacy_status']}")
        print(f"missing: {', '.join(plan['missing_requirements']) or '-'}")
        print(f"saved: {path}")
        print(f"dry-run execute: python scripts\\cdp_client.py youtube upload execute {path} --approved --confirm={uploader.APPROVAL_PHRASE} --dry-run")
        return
    if sub == "execute":
        if not args:
            print("  [error] usage: youtube upload execute <plan_path> --approved --confirm=YOUTUBE_APPROVED_UPLOAD [--dry-run|--live]")
            return
        plan_path = args[0]
        approved = "--approved" in args
        confirm = _confirm_arg(args)
        dry_run = "--live" not in args
        result, path = uploader.execute_upload_plan(plan_path, approved=approved, confirm=confirm, dry_run=dry_run)
        print("=" * 60)
        print("YouTube upload execute")
        print("=" * 60)
        print(f"status: {result['status']}")
        print(f"state_change: {result['state_change']}")
        print(f"dry_run: {result['dry_run']}")
        print(f"video_id: {result.get('video_id') or '-'}")
        print(f"reason: {result.get('reason') or '-'}")
        print(f"saved: {path}")
        return
    if sub == "verify":
        if not args:
            print("  [error] usage: youtube upload verify <result_path>")
            return
        verification, path = uploader.verify_upload_result(args[0])
        print("=" * 60)
        print("YouTube upload verify")
        print("=" * 60)
        print(f"status: {verification['status']}")
        print(f"video_id: {verification.get('video_id') or '-'}")
        print(f"saved: {path}")
        return
    print(f"  [error] unknown youtube upload task: {sub}")


def _confirm_arg(args: list[str]) -> str:
    for arg in args:
        if arg.startswith("--confirm="):
            return arg.split("=", 1)[1]
    return ""
