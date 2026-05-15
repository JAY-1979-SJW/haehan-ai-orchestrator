# Business Workflow Full Development Policy - 2026-05-13

## Rule

All business workflows must be developed completely through the following
pipeline:

```text
discover -> plan -> prepare -> approval -> execute -> verify -> log
```

The system must not stop at read-only discovery when the user asks for a
business-capable implementation. The implementation must include the final
execution path, but state-changing execution stays blocked until the user
explicitly approves it.

## Meaning

For every site or work surface:

- Discover visible sections, inputs, buttons, menus, and navigation.
- Classify all read, prepare, and state-changing actions.
- Build a prepare step that can fill drafts, forms, uploads, messages, posts,
  releases, submissions, or configuration plans without final submission.
- Build an approval gate that clearly shows what will change.
- Build an execute step that runs only after the user decides to approve.
- Verify the result and save audit evidence.
- Save logs without exposing passwords, cookies, tokens, or unnecessary private
  content.

## Approval Boundary

The following actions must be implemented but never executed without approval:

- send mail or messages
- publish posts, videos, comments, listings, releases, or announcements
- upload files or media
- create, delete, rename, share, move, or export private files
- create API keys, credentials, service accounts, IAM changes, or billing
  changes
- deploy apps, cloud resources, storage buckets, functions, databases, or rules
- request indexing, removal, policy, monetization, or channel/app changes
- submit forms to public agencies, marketplaces, consoles, or customer systems

Approval must be explicit and tied to the prepared action artifact. A generic
live session or login is not approval to execute a state-changing action.

## Google-Specific Application

Google-related work includes, at minimum:

- Google Account, Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Meet,
  Chat, Keep, Tasks, Contacts, Photos, Maps, Business/Profile surfaces
- Google Cloud Console, API Console, IAM, Billing, Cloud Run, Compute Engine,
  Storage, BigQuery, SQL, Kubernetes, Pub/Sub, Secret Manager, Logging,
  Monitoring, Cloud Shell
- Firebase Console, Hosting, Firestore, Realtime Database, Auth, Storage,
  Functions, Rules, Analytics
- Google AI Studio, Gemini, Vertex AI, Gemini API, API keys, model playgrounds
- Android Developers, Play Console, app releases, testing, policy, store
  listing, users, monetization
- YouTube, YouTube Studio, channel dashboard, content, analytics, comments,
  subtitles, monetization, customization, upload, live, posts
- Search Console, Analytics, Tag Manager, Ads, Merchant Center, AdSense

Every surface should have a read/prepare/approval/execute classification even
when some execute paths remain blocked pending official API setup or user
approval.

## Operating Instruction

When a user says "develop all business work", "make it usable for work", or
"approval is my final decision", implement complete action paths and approval
gates. Do not treat approval gating as a reason to omit the execute path.

Before code changes:

1. Regenerate worktree index.
2. Record pre-change dry-run evidence.
3. Scope the change to the site owner or common policy owner.

Before execution:

1. Generate a prepare artifact.
2. Show the action summary and risk.
3. Require explicit user approval.
4. Execute only the approved artifact.
5. Verify and log.
