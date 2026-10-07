# YouTube Recording And Upload Workflow

Updated: 2026-05-13

This workflow supports local work recording and YouTube upload preparation with
explicit approval gates.

## Pipeline

```text
record prepare -> record execute -> upload prepare -> upload execute dry-run -> upload execute live -> verify
```

## Commands

Prepare a local screen recording plan:

```powershell
python scripts\entry\cdp_cli.py youtube record prepare duration=60 output=data\youtube_recordings\work.mp4
```

Execute recording after approval:

```powershell
python scripts\entry\cdp_cli.py youtube record execute <plan_path> --approved --confirm=YOUTUBE_APPROVED_RECORD
```

Prepare upload manifest:

```powershell
python scripts\entry\cdp_cli.py youtube upload prepare data\youtube_recordings\work.mp4 title="업무 기록" privacy=private tags=work,local
```

Dry-run upload gate:

```powershell
python scripts\entry\cdp_cli.py youtube upload execute <plan_path> --approved --confirm=YOUTUBE_APPROVED_UPLOAD --dry-run
```

Live upload uses the official YouTube Data API path and must remain approved:

```powershell
python scripts\entry\cdp_cli.py youtube upload execute <plan_path> --approved --confirm=YOUTUBE_APPROVED_UPLOAD --live
```

## Approval Rules

- Recording requires `YOUTUBE_APPROVED_RECORD`.
- Upload requires `YOUTUBE_APPROVED_UPLOAD`.
- Upload defaults to dry-run unless `--live` is supplied.
- Public publishing must be treated as a separate final approval decision.
- Upload metadata defaults to `privacy=private`.

## Safety Checklist

- Close password, cookie, token, billing, account, and customer PII screens
  before recording.
- Review the saved video locally before upload preparation.
- Do not include raw secrets in title, description, tags, or file names.
- Use official YouTube API credentials for live upload.

## Artifacts

- `data/youtube_recording_plans/`
- `data/youtube_recording_results/`
- `data/youtube_upload_plans/`
- `data/youtube_upload_results/`
- `data/logs/realtime_audit.jsonl`

