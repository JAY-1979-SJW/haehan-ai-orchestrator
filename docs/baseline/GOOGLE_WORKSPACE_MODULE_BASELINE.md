# HAEHAN Google Workspace Module Baseline

Status: LOCKED
Baseline ID: GOOGLE-WORKSPACE-MODULE-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 2117c7f13d499e3bd627738fd4ffd7429979ce7a
Last updated: 2026-05-24

## 1. Purpose

This baseline locks the first Google sub-module split target: `workspace`.
The next implementation stage must split Workspace behavior without changing
the existing Google catalog counts or approval boundaries.

This is a baseline-only stage. It does not move Gmail, Drive, Calendar, Docs,
Sheets, or other Workspace runtime code yet.

## 2. Locked Workspace Scope

Workspace owns exactly 12 surfaces:

- `gmail`
- `drive`
- `calendar`
- `docs`
- `sheets`
- `slides`
- `forms`
- `meet`
- `chat`
- `contacts`
- `keep`
- `tasks`

Locked counts:

- Workspace surfaces: 12
- Workspace actions: 24
- Workspace read actions: 12
- Workspace approval actions: 12
- Workspace live input supported actions: 12
- Workspace prepare/open-only approval actions: 0

## 3. Host Boundaries

Workspace host ownership:

- `mail.google.com`: Gmail
- `drive.google.com`: Drive
- `calendar.google.com`: Calendar
- `docs.google.com`: Docs, Sheets, Slides, Forms
- `meet.google.com`: Meet
- `chat.google.com`: Chat
- `contacts.google.com`: Contacts
- `keep.google.com`: Keep
- `tasks.google.com`: Tasks

Every Workspace action target host must match its registered surface host.

## 4. Required Workspace Actions

Read actions:

- `gmail_open`
- `drive_open`
- `calendar_open`
- `docs_open`
- `sheets_open`
- `slides_open`
- `forms_open`
- `meet_open`
- `chat_open`
- `contacts_open`
- `keep_open`
- `tasks_open`

Approval actions:

- `gmail_send_email`
- `drive_upload_share_file`
- `calendar_create_event`
- `docs_create_edit_document`
- `sheets_update_cells`
- `slides_create_presentation`
- `forms_create_publish`
- `meet_create_meeting`
- `chat_send_message`
- `contacts_create_update`
- `keep_create_note`
- `tasks_create_task`

All 12 Workspace approval actions support safe live input handoff. They must
remain `no_final_submit_only` unless a separate approved final implementation is
added.

## 5. Authentication And Data Rules

Workspace modules must follow the Google authentication baseline:

- no Google password replay
- no Google password credential storage
- existing session or user-present login only
- OAuth/API only after separate approval

Private data rules:

- no mail body, account name, file name, document body, attendee, contact,
  chat message, note, or task content may be logged raw
- redacted preview only where a report needs evidence
- private data read paths must prefer official API/OAuth when available

## 6. Intended Module Shape

The approved target structure is:

```text
scripts/google/workspace/
  __init__.py
  registry.py
  router.py
  gmail.py
  drive.py
  calendar.py
  docs.py
  sheets.py
  slides.py
  forms.py
  meet.py
  chat.py
  contacts.py
  keep.py
  tasks.py
```

The first implementation step must use wrappers or registries. It must not
delete the existing top-level Google modules until compatibility tests prove
the router, catalog, and action counts are unchanged.

## 7. Step Plan

Workspace split must proceed in this order:

1. Add `scripts/google/workspace/registry.py`.
2. Add wrappers for existing Gmail, Drive, Calendar, Docs, and Sheets modules.
3. Add placeholder wrappers for Slides, Forms, Meet, Chat, Contacts, Keep, and Tasks.
4. Route Workspace tasks through `scripts/google/workspace/router.py`.
5. Keep old imports working from `scripts/google/router.py`.
6. Verify 12 surfaces and 24 actions remain unchanged.
7. Verify approval actions remain 12 and host warnings remain 0.
8. Commit only after Google tests and repo guard pass.

## 8. Forbidden During Workspace Split

- no broad Google refactor outside Workspace
- no Cloud, YouTube, Marketing, AI, Developer, or Media file movement
- no password login restoration
- no live final send, upload, create, edit, publish, or delete without approval
- no secret, token, cookie, session, password, OTP, mail body, or private file content output
- no build, deploy, installer, Docker, or push

## 9. Required Verification

Minimum verification for Workspace changes:

```text
python tools/audits/google/audit_google_workspace_module_baseline_contract.py
python -m pytest tests/test_google_tab_registry.py tests/test_google_workflows.py tests/test_google_surfaces.py tests/test_google_user_present_session_auth.py -q
python tools/quality/module_quality_gate.py --module repo_guard
```

## 10. Known WARN

- Workspace module packages are not fully split yet.
- All Workspace approval actions are live-input-handoff supported with
  no-final-submit. Final send, upload, create, edit, publish, share, or save
  controls remain blocked until separately approved.
