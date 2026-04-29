# Stage 13C-1 audit summary reporting channel design

**Date**: 2026-04-29  
**Context**: Stage 13B observe_summary (structured fields) has been integrated and deployed (commit 6347b6c).  
**Scope**: Design the safe audit summary reporting channel — PC local audit.jsonl must NOT be exposed to server/admin-web; only sanitized summary counts/categories should be reported.

---

## 1. Current State Summary

### 1-1. Local Audit Recording

- **Location**: `~/.haehan_agent/audit.jsonl` (Windows: `%USERPROFILE%\.haehan_agent\audit.jsonl`)
- **Events**: 7 event types from `browser_open_*` actions:
  - `browser_open_requested` (URL category, allow_about_blank, allow_private_network flags)
  - `browser_open_dry_run_checked` (validation ok/fail, error_code)
  - `browser_open_blocked` (error_code, reason text — raw)
  - `browser_open_started` (URL category baseline)
  - `browser_open_observed` (pages_observed_count, title_len, login_required_hint, modal_candidates_count, html_truncated, page_structure_counts)
  - `browser_open_completed` (ok flag, error_code — raw reason text if error)
  - `browser_open_failed` (error_code, reason text — raw)

### 1-2. Server & Admin-Web Exposure

- **Current Access**: Admin-web **cannot directly read** PC local audit.jsonl (no SSH/SCP connection, no REST API for raw audit).
- **Risk**: Raw audit.jsonl contains:
  - Raw error reason text (may leak internal paths, URLs, config hints)
  - Page titles (may contain sensitive user data if URL allowlist insufficient)
  - Modal candidate count & hints (may hint at security mechanisms)
  - HTML truncated flag (may hint at complexity/size of target page)
  - No direct exposure currently — but task detail might extend to audit data in future.

### 1-3. Stage 13B observe_summary Relationship

- **observe_summary**: Structured fields stored in `LocalAgentTask.observe_summary` (optional dict).
- **Purpose**: Task detail display safe summary for `open_url_readonly` (browse action).
- **Content**: url_category, final_url_sanitized, title, status_category, pages_observed_count, error_category, blocked_reason, login_required_hint, modal_candidates_count, html_truncated, page_structure_counts, observed_at.
- **NOT for audit**: observe_summary does not store audit event counts/categories; it stores the final observed page summary.

### 1-4. Stage 13C Goal

- **Define**: A safe audit summary reporting channel where local-agent reports task-associated audit counts/categories without exposing raw audit JSONL.
- **Mechanism**: WS result message includes optional `audit_summary` dict with allowed primitive/count fields only.
- **Storage**: `LocalAgentTask.audit_summary` (optional dict) stores server-side.
- **Display**: Admin-web can show audit event count, category breakdown, status distribution — no raw event payloads, no URLs, no paths, no text.
- **Non-blocking**: If audit_summary is missing/null, existing task flow must work unchanged.

---

## 2. Field Classification

Classify audit summary fields by storage & display intent.

### 2-1. STORE_AND_DISPLAY Candidates

| Field | Type | Purpose | Sanitize |
|-------|------|---------|----------|
| `audit_event_count` | int | Total # events in task window | intrinsic |
| `audit_window_started_at` | ISO str | Task request timestamp (local clock) | timestamp only |
| `audit_window_ended_at` | ISO str | Task completion timestamp | timestamp only |
| `audit_event_categories` | list[str] | `["browser_open_requested", "browser_open_observed", ...]` enum codes | enum only |
| `blocked_event_count` | int | # events with "blocked" status | intrinsic |
| `allowed_event_count` | int | # events with "ok" status | intrinsic |
| `denied_event_count` | int | # events with "denied" status | intrinsic |
| `error_event_count` | int | # events with error_code | intrinsic |
| `last_event_category` | str | Most recent event type (enum) | enum only |
| `last_event_status` | str | Most recent event status: "ok" / "blocked" / "denied" / "error" | enum only |
| `policy_decision_counts` | dict | `{"blocked": N, "denied": N, "allowed": N}` | count dict only |
| `target_kind_counts` | dict | `{"about_blank": N, "internal_test": N, "external": N}` | count dict only |
| `action_kind_counts` | dict | `{"dry_run_checked": N, "started": N, "completed": N, "failed": N}` | count dict only |

**Rationale**: These fields expose audit activity _shape_ (counts, categories, timing window, decision breakdown) without exposing raw event payloads, URLs, reasons, or page content.

### 2-2. STORE_ONLY Candidates

| Field | Type | Purpose | Reason for Not Displaying |
|-------|------|---------|---------------------------|
| `audit_schema_version` | int | Schema version for backward compat | Internal tracking; not user-facing |
| `local_audit_source` | str | Source identifier (`"~/.haehan_agent/audit.jsonl"` path name or "local_audit_v1") | Reveals local path structure; hide in display |
| `agent_reported_event_count` | int | # events actually reported by agent (vs. unknown/dropped) | Useful for diagnostics; not needed in UI |
| `audit_summary_generated_at` | ISO str | When summary was generated (agent-side clock) | Internal timestamp; not user-facing |
| `audit_summary_hash` | str | SHA-256 or CRC of sanitized summary (for idempotency check) | Operational; not user-facing |
| `dropped_event_count` | int | # events unable to match to task_id | Diagnostic; not needed in UI |
| `redacted_field_count` | int | # fields dropped during sanitization | Diagnostic; not needed in UI |

**Rationale**: These fields support server-side validation, debugging, and idempotency without leaking operational details to users.

### 2-3. DISPLAY_DERIVED Candidates

| Field | Type | Compute From | Purpose |
|-------|------|-----|---------|
| `audit_health_status` | str | blocked_event_count, error_event_count | "healthy" / "warning" / "critical" label (UI-only, not stored) |
| `has_blocked_events` | bool | blocked_event_count > 0 | Boolean flag for UI conditional (not stored) |
| `has_denied_events` | bool | denied_event_count > 0 | Boolean flag for UI conditional (not stored) |
| `has_errors` | bool | error_event_count > 0 | Boolean flag for UI conditional (not stored) |
| `audit_coverage_label` | str | (task_id, audit_event_count) heuristic | "full" / "partial" / "none" label for coverage estimation (UI-only) |
| `event_count_label` | str | audit_event_count bucketing | "quiet" / "normal" / "high" / "very_high" for readability (UI-only) |

**Rationale**: Derived fields do not require server storage; they are computed client-side from STORE_AND_DISPLAY fields during rendering. This reduces payload size and keeps display logic centralized.

### 2-4. DO_NOT_STORE

Absolute blocklist — these MUST NOT be saved in LocalAgentTask.audit_summary:

- Raw audit JSONL line (entire event object)
- Raw event payload dict
- `current_url` original text
- URL query string (any part of `?key=value`)
- URL fragment (any part of `#anchor`)
- Raw HTML content
- Modal candidate text or reason
- Page text / innerHTML
- CSS selectors
- Screenshot file path
- Local file path (absolute or relative — `C:\Users\...`, `~/.haehan_agent/...`, etc.)
- Cookie values
- Session ID / session state
- Authorization token / Bearer token
- Password (plaintext or hashed)
- Authorization header
- Request/response headers (raw)
- Request/response body (raw)
- localStorage content
- sessionStorage content
- Clipboard content
- Typed/inputted text by user
- PC username / hostname (raw)
- Absolute local path of audit.jsonl source
- IP address or internal hostname (if sensitive in context)

**Enforcement**: Allowlist approach — only fields in 2-1 and 2-2 sections are copied into audit_summary; all others are dropped.

### 2-5. DO_NOT_DISPLAY

Fields that may be stored server-side but must NOT be rendered in admin-web:

- `audit_summary_hash` / digest
- `local_audit_source`
- Raw details of `dropped_event_count` (only show count, never reason per event)
- Raw details of `redacted_field_count` (only show count, never which fields)
- Raw policy reason text (if sensitivity unclear)
- Any raw local path appearing in error messages
- Any raw URL appearing in policy reason
- Direct JSON.stringify() of audit_summary dict
- Raw event list or table rows

**Enforcement**: Admin-web template renders only STORE_AND_DISPLAY fields; STORE_ONLY and raw payload fields are never accessed/rendered.

---

## 3. Storage Location Alternatives

Three approaches to store audit_summary on the server side.

### 3-1. Option A: LocalAgentTask.audit_summary field

```python
@dataclass
class LocalAgentTask:
    ...
    observe_summary: dict | None = None  # (Stage 13B)
    audit_summary: dict | None = None     # (Stage 13C NEW)
```

**Pros**:
- Minimal schema change (one optional field per task).
- Audit summary lifetime-bound to task (no separate cleanup).
- Backward compat: existing tasks have `audit_summary=None`.
- Task detail API (`GET /api/v1/local-agents/{agent_id}/tasks/{task_id}`) naturally extends with optional `audit_summary`.

**Cons**:
- Couples audit and observe data in one model (semantic drift if audit scope expands beyond observe).
- No separate audit event versioning (if future audit events don't relate to observe, model becomes confusing).

### 3-2. Option B: Extend observe_summary to include audit_event_count only

Add `audit_event_count: int | None` to the existing observe_summary dict structure.

```python
@dataclass
class ObserveSummary:
    ...
    audit_event_count: int | None = None
    # other audit-related counts added to dict later
```

**Pros**:
- Leverage existing observe_summary structure (less schema surface).
- Observe and audit are semantically linked (both from same browse action).
- Single to_safe() serialization path.

**Cons**:
- Conflates observe page structure with audit event counts (schema bloat).
- If future tasks (non-observe) have audit_summary, model becomes inconsistent.
- API shape becomes harder to document (observe_summary does too much).

### 3-3. Option C: Separate LocalAgentAuditSummary model with dedicated store

```python
@dataclass
class LocalAgentAuditSummary:
    task_id: str
    audit_event_count: int
    audit_event_categories: list[str]
    policy_decision_counts: dict
    ...

@dataclass
class LocalAgentTask:
    ...
    audit_summary_id: str | None = None  # foreign key
```

**Pros**:
- Clean separation: audit summary is its own entity.
- Supports per-event-type versioning and schema evolution.
- Easier to add audit summary to other task types later.
- Audit summary can be queried/filtered independently.

**Cons**:
- Adds API endpoint complexity (`GET /api/v1/tasks/{task_id}/audit-summary`).
- Schema requires new table/collection in DB.
- Task detail API must join audit summary (extra query or embed).
- Overkill if only observe actions report audit.

---

## 4. Storage Location Recommendation

**Chosen: Option A (LocalAgentTask.audit_summary field)**

**Rationale**:

1. **Stage 13C scope**: Currently only `open_url_readonly` (browse action) has audit feedback. Audit and observe are tightly coupled to the same task.
2. **Minimal schema**: One optional dict field, backward compatible, no DB migration needed for optional columns.
3. **Task detail API extension**: Natural extension of task detail endpoint — no new endpoints, no joins.
4. **Admin-web impact**: Single task detail modal shows both observe_summary and audit_summary sections; no new page/component.
5. **Future flexibility**: If audit scope expands to other actions (Stage 14+), can still refactor to Option C without breaking task API contract (audit_summary remains optional).

**Constraints**:
- Raw audit JSONL MUST NOT be stored in audit_summary (allowlist-only approach).
- Task list API (`GET /api/v1/local-agents/{agent_id}/tasks`) does NOT include audit_summary (task detail only).
- audit_summary is optional; null/missing must not break existing clients.

---

## 5. Local-Agent Reporting Channel Design

### 5-1. WS Result Message Extension

Current flow (Stage 13B):
```
local_agent → WS result {
  task_id: "...",
  status: "completed",
  result_summary: "...",
  observe_summary: {...}  // Stage 13B
}
→ orchestrator apply_result() → LocalAgentTask.observe_summary = ...
```

New flow (Stage 13C):
```
local_agent → WS result {
  task_id: "...",
  status: "completed",
  result_summary: "...",
  observe_summary: {...},
  audit_summary: {...}  // NEW: optional
}
→ orchestrator apply_result() → LocalAgentTask.audit_summary = sanitize(audit_summary)
```

### 5-2. Agent-Side Reporting Logic

Local-agent must:

1. **Collect audit window**: Detect task_id from WS request; map all audit JSONL lines written during task lifetime to task_id.
   - Window: from task request → to task completion (timestamps match).
   - Unknown/unmapped events: dropped or categorized as `"unknown"`.

2. **Summarize without exposing raw data**:
   ```python
   def _build_audit_summary(task_id: str) -> dict | None:
       """
       Read ~/.haehan_agent/audit.jsonl.
       Filter events matching task window (estimated from result timestamps).
       Return allowlist dict with STORE_AND_DISPLAY fields only.
       """
       events = load_audit_events_for_task(task_id)
       if not events:
           return None  # No audit; report nothing
       
       return {
           "audit_event_count": len(events),
           "audit_window_started_at": events[0]["timestamp"],
           "audit_window_ended_at": events[-1]["timestamp"],
           "audit_event_categories": list(set(e["event_type"] for e in events)),
           "blocked_event_count": sum(1 for e in events if e.get("status") == "blocked"),
           "allowed_event_count": sum(1 for e in events if e.get("status") == "ok"),
           "policy_decision_counts": {...},
           "target_kind_counts": {...},
           "action_kind_counts": {...},
           # NO raw URLs, NO raw HTML, NO raw paths, NO raw text
       }
   ```

3. **Task matching strategy**:
   - Prefer exact task_id field in audit event (if 13B backfilled audit events with task_id).
   - Fallback: timestamp window (request → result).
   - Unmapped events: `"unknown"` category; dropped_event_count incremented.

### 5-3. Server-Side Validation & Storage

Orchestrator `apply_result()` handler:

```python
def apply_result(task_id: str, result_dict: dict) -> None:
    ...
    audit_summary = result_dict.get("audit_summary")
    if audit_summary:
        # Sanitize: allowlist only STORE_AND_DISPLAY + STORE_ONLY fields
        audit_summary = _sanitize_audit_summary(audit_summary)
        task.audit_summary = audit_summary
    ...
```

### 5-4. Failure Handling

- **Missing audit_summary**: Normal; task succeeds without audit data.
- **Invalid audit_summary**: Log warning; drop field; task succeeds.
- **Agent crash before audit report**: Task completion status is independent of audit success — audit data loss does NOT fail task.
- **audit_summary too large (>100KB)**: Truncate top-N categories; log warning.

---

## 6. Sanitization Rules

### 6-1. Allowlist Approach

Only fields explicitly listed in section 2-1 (STORE_AND_DISPLAY) and 2-2 (STORE_ONLY) are copied into server-stored `audit_summary`. All other keys are dropped.

### 6-2. Type Enforcement

Valid types in sanitized audit_summary:

- **Primitive**: `int`, `str`, `bool`
- **Collections**: `list[str]`, `list[int]`, `dict[str, int]`, `dict[str, str]` (key & value must be primitive)
- **NOT allowed**: `dict` with nested dict, list of dicts, arbitrary objects, None-padding

**Validation**:
```python
def _sanitize_audit_summary(raw: dict) -> dict:
    allowed_keys = {
        "audit_event_count", "audit_window_started_at", "audit_window_ended_at",
        "audit_event_categories", "blocked_event_count", "allowed_event_count",
        "denied_event_count", "error_event_count", "last_event_category",
        "last_event_status", "policy_decision_counts", "target_kind_counts",
        "action_kind_counts",  # STORE_AND_DISPLAY
        "audit_schema_version", "local_audit_source", "agent_reported_event_count",
        "audit_summary_generated_at", "audit_summary_hash", "dropped_event_count",
        "redacted_field_count",  # STORE_ONLY
    }
    result = {}
    for key, value in raw.items():
        if key not in allowed_keys:
            continue  # drop unknown
        if not _is_valid_primitive_or_count(value):
            continue  # drop invalid type
        result[key] = value
    return result
```

### 6-3. String Content Constraints

- **Enum-only fields** (`audit_event_categories`, `last_event_category`, `last_event_status`): Only allow whitelisted enum values (e.g., `["browser_open_requested", "browser_open_completed"]`, `["ok", "blocked", "denied", "error"]`).
  - Any value outside enum → drop field.
- **Timestamp fields** (`audit_window_started_at`, `audit_window_ended_at`, `audit_summary_generated_at`): ISO 8601 format only.
  - Invalid timestamp → drop field.
- **All other string values**: Drop (no free-form text).

### 6-4. Count & Dict Constraints

- **Integer counts** (`audit_event_count`, `blocked_event_count`, etc.): Non-negative integers only.
  - Negative → drop field or reset to 0.
- **Count dicts** (`policy_decision_counts`, `target_kind_counts`, `action_kind_counts`): Keys are whitelisted enum strings; values are non-negative integers.
  - Invalid key → drop; negative value → reset to 0.

### 6-5. Schema Versioning

Include `"audit_schema_version": 1` in audit_summary to support future schema changes.

---

## 7. API Impact

### 7-1. Task Detail Endpoint

**GET `/api/v1/local-agents/{agent_id}/tasks/{task_id}`**

Current response (Stage 13B):
```json
{
  "task_id": "...",
  "status": "completed",
  "result_summary": "...",
  "observe_summary": {...},
  ...
}
```

Stage 13C response:
```json
{
  "task_id": "...",
  "status": "completed",
  "result_summary": "...",
  "observe_summary": {...},
  "audit_summary": {...}  // NEW: optional, null if missing
  ...
}
```

**Backward compat**: Existing clients ignoring `audit_summary` field continue to work. Clients expecting the field check `if (task.audit_summary) { ... }`.

**to_safe() logic**: 
```python
def to_safe(self) -> dict:
    d = {
        "task_id": self.task_id,
        ...
        "observe_summary": self.observe_summary,
        "audit_summary": self.audit_summary,  # NEW
    }
    return d
```

### 7-2. Task List Endpoint

**GET `/api/v1/local-agents/{agent_id}/tasks`**

**NO CHANGE**. Task list remains `to_list_safe()` and does NOT include audit_summary (too detailed; list is summary only).

### 7-3. Raw Audit JSONL API

**DO NOT ADD**. Even if future use cases arise, raw audit.jsonl must not be exposed via HTTP endpoint — it's local-only and must be sanitized through summary reporting channel only.

---

## 8. Admin-Web Impact

### 8-1. Task Detail Modal

New "감사 요약" (Audit Summary) section in task detail modal (below observe_summary section):

```
┌─ Task Detail Modal ────────────────────────┐
│                                            │
│  Task ID: xyz                              │
│  Status: completed                         │
│  Result: ...                               │
│                                            │
│  ─ Observe Summary ─                       │
│    Final URL: https://...                  │
│    Title: Page Title                       │
│    Pages: 1                                │
│                                            │
│  ─ Audit Summary ─         [NEW]           │
│    Events: 5                               │
│    Blocked: 1                              │
│    Allowed: 4                              │
│    Categories: requested, started, ...     │
│    [View Details] (expands count breakdown) │
│                                            │
└────────────────────────────────────────────┘
```

### 8-2. Render Rules

- **If audit_summary is null**: Hide "감사 요약" section entirely.
- **Display fields** (from STORE_AND_DISPLAY):
  - `audit_event_count` → "전체 감사 이벤트: N"
  - `blocked_event_count` → "차단됨: N"
  - `allowed_event_count` → "허용됨: N"
  - `denied_event_count` → "거부됨: N" (if > 0)
  - `error_event_count` → "오류: N" (if > 0)
  - `audit_event_categories` → "이벤트 유형: [browser_open_requested, browser_open_observed, ...]"
  - `policy_decision_counts` → Pie/bar chart or text breakdown
  - `target_kind_counts` → Breakdown by target (about_blank, internal_test, external)
  - `action_kind_counts` → Breakdown by action phase (requested, started, completed, failed)
  - `audit_window_started_at`, `audit_window_ended_at` → Time window label (collapsible)

### 8-3. Anti-Patterns (Strict Prohibitions)

- **NO** `JSON.stringify(audit_summary)` raw display
- **NO** raw event list/table (each line is a JSON object)
- **NO** rendering of STORE_ONLY fields (hash, source, dropped_count details)
- **NO** external links/anchors in category text
- **NO** tooltip containing raw policy reasons or URLs
- **NO** copy-to-clipboard of raw JSON
- **NO** drill-down to event-level details (admin-web stays at summary level)

### 8-4. Derived Fields (Client-Side)

Compute in React component; do NOT send from server:

```typescript
function computeAuditStatus(auditSummary: AuditSummary | null): string {
  if (!auditSummary) return "no_audit";
  if (auditSummary.error_event_count > 0) return "critical";
  if (auditSummary.denied_event_count > 0) return "warning";
  return "healthy";
}
```

---

## 9. Test Plan

### 9-1. Mandatory Test Cases

**Server-side (pytest)**:

1. **Baseline**: Task without audit_summary = null.
   - `test_task_without_audit_summary_completes_normally`

2. **Allowlist enforcement**: Only STORE_AND_DISPLAY + STORE_ONLY fields survive sanitization.
   - `test_sanitize_drops_unknown_keys`
   - `test_sanitize_drops_raw_urls`
   - `test_sanitize_drops_raw_paths`
   - `test_sanitize_drops_raw_html`
   - `test_sanitize_drops_raw_text`

3. **Forbidden payload rejection**:
   - `test_audit_summary_rejects_raw_event_payload`
   - `test_audit_summary_rejects_audit_jsonl_line`
   - `test_audit_summary_rejects_cookie`
   - `test_audit_summary_rejects_session_token`
   - `test_audit_summary_rejects_password`
   - `test_audit_summary_rejects_url_query`
   - `test_audit_summary_rejects_url_fragment`
   - `test_audit_summary_rejects_selector`
   - `test_audit_summary_rejects_html_content`
   - `test_audit_summary_rejects_response_body`
   - `test_audit_summary_rejects_local_file_path`
   - `test_audit_summary_rejects_authorization_header`

4. **Type validation**:
   - `test_audit_summary_enforces_int_type_for_counts`
   - `test_audit_summary_enforces_string_type_for_categories`
   - `test_audit_summary_enforces_dict_type_for_policy_counts`
   - `test_audit_summary_rejects_nested_dict`
   - `test_audit_summary_rejects_list_of_dicts`
   - `test_audit_summary_rejects_negative_counts`

5. **Enum validation**:
   - `test_audit_event_categories_enum_only`
   - `test_last_event_status_enum_only`
   - `test_policy_decision_counts_keys_enum_only`

6. **Task detail API**:
   - `test_task_detail_includes_audit_summary`
   - `test_task_detail_audit_summary_is_optional`
   - `test_task_list_does_not_include_audit_summary`

7. **Idempotency** (if audit_summary_hash added):
   - `test_audit_summary_hash_matches_sorted_json`
   - `test_duplicate_audit_summary_detected`

**Admin-web (jest/React Testing Library)**:

8. **Rendering**:
   - `test_audit_summary_section_hidden_when_null`
   - `test_audit_summary_section_shows_event_count`
   - `test_audit_summary_section_shows_decision_breakdown`
   - `test_audit_summary_shows_no_raw_json`
   - `test_audit_summary_shows_no_raw_event_list`
   - `test_audit_summary_shows_no_forbidden_fields`

9. **XSS prevention**:
   - `test_audit_summary_category_text_escaped`
   - `test_audit_summary_no_dangerously_set_inner_html`
   - `test_audit_summary_no_javascript_in_links`

### 9-2. Smoke Test

```bash
# Python
python -m pytest tests/test_audit_summary_* -v

# Admin-web
npm run test -- audit_summary
npm run lint

# Noexec smoke
python scripts/check_local_agent_noexec_smoke.py --include audit_summary
```

---

## 10. Stage 13C-2 Minimal Implementation Proposal

### 10-1. Scope

Implement Option A (LocalAgentTask.audit_summary) with basic sanitization — no UI extension yet.

### 10-2. Changes Required

**Backend (ai_orchestrator)**:

1. **local_agent_registry.py**:
   - Add `audit_summary: dict | None = None` field to LocalAgentTask dataclass.
   - Add `_sanitize_audit_summary(raw: dict) -> dict` helper function.
   - Add ALLOWED_AUDIT_SUMMARY_KEYS constant.

2. **local_agent_router.py**:
   - Modify `apply_result()` to accept optional `audit_summary` from WS message.
   - Call `_sanitize_audit_summary()` before storing.
   - Log audit summary receipt (count, categories).

3. **local_agent_registry.py (to_safe)**:
   - Extend `to_safe()` to include `"audit_summary": self.audit_summary`.

4. **tests/test_audit_summary_fixture.py** (new):
   - 50+ test cases covering sections 9-1.

**Admin-web (admin-web/src)**:

5. **types/local-agent.ts**:
   - Add optional `audit_summary?: AuditSummary` to LocalAgentTask interface.
   - Add AuditSummary interface with STORE_AND_DISPLAY fields.

6. **API client** (no changes — audit_summary is optional in response, auto-deserialize).

**UI (defer to Stage 13C-3)**:

- Task detail modal audit section: DEFERRED.

### 10-3. Do NOT Implement in 13C-2

- Local-agent reporting logic (agent-side sanitization) — keep in 13C-3 or later.
- Admin-web audit summary display — defer to 13C-3.
- Audit event matching/windowing logic — defer to 13C-3.
- audit_summary_hash / dropped_event_count tracking — defer to 13C-3.

### 10-4. Validation Plan

- pytest: 50 tests, all passing.
- Admin-web typecheck: LocalAgentTask.audit_summary is optional (no type errors).
- Task detail API response includes audit_summary field (even if null).
- Existing clients unaffected (field is optional).

---

## 11. Stage 13C Halt Conditions

**STOP and escalate if any of the following occurs**:

1. **Raw audit JSONL transmission required**: If stakeholders ask for raw audit JSONL to be sent to server, STOP — this breaks the safety boundary and requires a separate approval/design cycle.

2. **Raw audit field storage required**: If requirements emerge to store raw event payloads, raw URLs, raw paths, raw HTML, raw text, STOP and redesign.

3. **Sensitive data storage**: If audit summary must include:
   - Local file path (absolute or relative)
   - URL query/fragment/credentials
   - Selector/CSS class/page element identifier
   - Input field content
   - Modal/popup text
   - Cookie/session/token
   - Password/authorization header
   - PC username/hostname
   
   → STOP immediately and escalate to security review.

4. **DB/Schema change**: If LocalAgentTask schema modification (e.g., new table for audit_summary, migration script) is blocked or requires coordination with DBA, STOP and notify.

5. **External URL execution**: If audit summary reporting requires fetching external URLs, calling external APIs, or network I/O beyond SSH-authenticated server communication, STOP.

6. **Local-agent execution**: If testing audit summary reporting requires actually running local-agent process or opening browser, STOP — defer to integration test environment.

7. **Scope creep**: If audit summary scope expands beyond `browser_open_*` events to system-wide auditing, DB access auditing, or compliance-driven compliance audit, STOP and request separate design for broader audit system.

---

## 12. Conclusion

**Stage 13C-1** defines the safe audit summary reporting channel:

- **Allowlist approach**: Only primitive/count fields stored; raw payloads dropped.
- **Task-bound storage**: audit_summary in LocalAgentTask (Option A).
- **Non-blocking**: Null/missing audit_summary does not break task flow.
- **API extension**: Task detail endpoint includes optional audit_summary.
- **Admin-web**: Display counts/categories only; no raw data, no XSS risk.
- **Testing**: 50+ mandatory test cases covering sanitization & forbidden payloads.
- **Next stage (13C-2)**: Implement backend schema + sanitization; defer agent reporting & UI to 13C-3.

**Safety boundary maintained**: Local audit.jsonl remains PC-local; only safe summary counts/categories cross the server boundary.

---

**Document prepared for review and implementation planning.**
