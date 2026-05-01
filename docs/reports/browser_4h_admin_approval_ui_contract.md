# BROWSER-4H: Admin Approval UI Contract Design

**Status**: Design & Mock Validation (BROWSER-4G + BROWSER-4H)  
**Date**: 2026-05-01  
**Model**: Claude Sonnet 4.6  
**Scope**: UI contract design + mock data validation (no real WebSocket/API)

---

## 1. Executive Summary

BROWSER-4H defines the Admin UI contract for browser action approval workflow. It specifies:

- **Data structures** for displaying browser action approval requests
- **Security rules** for token/secret non-disclosure in UI
- **Approval decision flow** (approve, reject, final approval)
- **Result display policy** (safe fields only)
- **Status vocabulary** and button state management
- **Risk assessment visualization** (badges, warnings, restrictions)

**Key principle**: Admin UI NEVER shows `approval_token`, `final_approval_token`, `token_hash`, typed text, or any sensitive data. Result display is limited to safe, whitelisted fields.

---

## 2. Data Structure Overview

### 2.1 BrowserApprovalRequestDisplay

**Purpose**: Display browser action pending approval to admin

**Safe fields** (always shown):
- `approval_id`: Unique approval record ID
- `task_id`: Browser task ID
- `action_type`: browser.execute_click, browser.execute_type, etc.
- `selector`: CSS selector of target element
- `risk_level`: low, medium, high, critical
- `final_approval_required`: Boolean flag
- `target_url_domain`: Safe domain name (no query/fragment)
- `requested_by`: Admin user ID who requested
- `created_at`: ISO8601 timestamp
- `expires_at`: Approval expiration (ISO8601)

**Safe optional fields**:
- `text_length`: For execute_type, length of input (NOT the text)
- `risky_keywords`: Detected keywords (delete, submit, payment)

**NEVER shown** (forbidden fields):
- ❌ `approval_token` (for verification only)
- ❌ `final_approval_token` (for verification only)
- ❌ `token_hash` (internal only)
- ❌ `value` (actual typed text) → use `[REDACTED]` + `text_length`
- ❌ `password`, `OTP`, `cookie`, `session`, `Authorization`
- ❌ `localStorage`, `sessionStorage`
- ❌ Full DOM, raw screenshot

**Status field**:
```
"received" | "validation_failed" | "approval_denied" | "approval_invalid"
| "blocked" | "expired" | "pending" | "approved" | "rejected" | "used"
```

**Control flags** (computed):
```typescript
can_approve: boolean;          // Approval allowed
can_reject: boolean;           // Rejection allowed
can_execute: boolean;          // Execute button shown
requires_final_approval_input: boolean; // Checkbox needed
approval_expired: boolean;     // Expiration flag
approval_used: boolean;        // Already executed
```

---

### 2.2 BrowserTaskResultDisplay

**Purpose**: Display execution result to admin

**Safe fields** (always shown):
- `task_id`: Reference to original task
- `status`: executed, blocked, failed, success, error
- `action_type`: Action that was performed
- `selector`: Target element selector
- `executed`: Boolean (did action run?)
- `element_found`: Boolean (was element found?)
- `result`: Result code (success, error, etc.)
- `risk_level`: Final risk assessment
- `target_url_domain`: Safe domain
- `text_length`: Length of text (NOT text itself)
- `text_preview`: Always `[REDACTED]`
- `executed_at`: ISO8601 timestamp

**Optional safe fields**:
- `error_code`: Error type code
- `error_message`: Human-readable error
- `screenshot_taken`: Boolean
- `screenshot_ref`: Reference/path only (never content)

**NEVER shown**:
- ❌ Approval tokens
- ❌ Raw typed text (use `text_length` only)
- ❌ Passwords, OTP, cookies, sessions
- ❌ Screenshot content (reference only)
- ❌ Base64, full DOM, localStorage

---

### 2.3 BrowserApprovalDecision

**Purpose**: Admin approval/rejection action

**Contains**:
```typescript
{
  approval_id: string;     // Which approval to decide on
  task_id: string;         // Associated task
  decision: "approve" | "reject";
  reason?: string;         // Required if reject
  approved_by?: string;    // Admin user ID
  final_approval_requested?: boolean;
}
```

**NEVER contains**:
- ❌ `approval_token`
- ❌ `final_approval_token`
- ❌ `token_hash`

**Server side** (not in UI):
- Server validates `approval_id` exists
- Server generates new `approval_token` if approved
- Token sent to local agent separately
- Token NEVER returned to UI

---

## 3. Security Rules

### 3.1 Token Non-Disclosure Policy

| Field | Input Payload | UI Display | Result Data | Log |
|-------|---|---|---|---|
| `approval_token` | ✓ Allowed (verification) | ❌ Never | ❌ Never | ❌ Never |
| `final_approval_token` | ✓ Allowed (verification) | ❌ Never | ❌ Never | ❌ Never |
| `token_hash` | ✓ Internal only | ❌ Never | ❌ Never | ❌ Never |
| Typed text (raw) | ✓ Input | ❌ Never | ❌ Never | ❌ Never |
| `text_length` | N/A | ✓ OK | ✓ OK | ✓ OK |
| `text_preview` | N/A | ✓ "[REDACTED]" | ✓ "[REDACTED]" | ✓ "[REDACTED]" |

### 3.2 Forbidden Keywords Detection

If action selector contains risky keywords, mark `final_approval_required = true`:

```typescript
const RISKY_KEYWORDS = [
  "delete", "remove", "purge", "clear", "wipe",
  "submit", "post", "send", "confirm",
  "payment", "checkout", "charge", "bill", "pay",
  "register", "signup", "create_account",
  "comment", "reply", "post_message",
  "save", "update", "modify"
];
```

If detected:
- `final_approval_required` = true
- Admin must check checkbox before approve
- Two-step approval flow enforced

### 3.3 Blocked Actions

Some action types are blocked entirely:

```
❌ browser.execute_submit  (not registered, never shown)
```

Handling:
- UI never shows "Approve" button for `browser.execute_submit`
- Status shows "blocked" with reason
- No execution possible

---

## 4. UI Display Rules by Status

### 4.1 Status: "received" (Pending Approval)

**Show**:
- All safe fields
- Risk badge (color by risk_level)
- "Approve" button
- "Reject" button
- Rejection reason input
- If `final_approval_required`: checkbox + disable Approve until checked

**Hide**:
- Result data
- Error details
- All forbidden fields

**Control**:
```
can_approve = !approval_expired && !final_approval_required
           || (final_approval_required && final_approval_checked)
can_reject = !approval_expired
```

---

### 4.2 Status: "approved" (Approved, Pending Execution)

**Show**:
- All safe fields
- Approval timestamp
- Approved by (admin)
- Risk badge
- "Awaiting execution..." indicator

**Hide**:
- Approve/Reject buttons
- Result data
- Forbidden fields

**Control**:
```
can_approve = false
can_reject = false
can_execute = false (local agent decides)
```

---

### 4.3 Status: "executed" (Completed Successfully)

**Show**:
- Approval info
- Execution result (from `BrowserTaskResultDisplay`)
- Success badge
- All safe result fields
- Executed timestamp

**Hide**:
- Approve/Reject buttons
- Forbidden fields

---

### 4.4 Status: "failed" (Execution Failed)

**Show**:
- Approval info
- Error code and message (safe summary)
- Failed badge
- Result fields

**Hide**:
- Approve/Reject buttons
- Forbidden fields

---

### 4.5 Status: "rejected" (Admin Rejected)

**Show**:
- Approval info
- Rejection reason
- Rejected badge
- Rejection timestamp

**Hide**:
- Approve/Reject buttons
- Result data
- Forbidden fields

---

### 4.6 Status: "expired" (Approval Expired)

**Show**:
- Approval info
- Expiration timestamp
- Expired badge
- "Approval expired" message

**Hide**:
- Approve/Reject buttons
- Result data

**Control**:
```
can_approve = false
can_reject = false
```

---

### 4.7 Status: "used" (Already Executed)

**Show**:
- Approval info
- Execution result
- Used badge
- Execution timestamp

**Hide**:
- Approve/Reject buttons
- Forbidden fields

---

## 5. Risk Assessment Visualization

### 5.1 Risk Badges

```typescript
risk_level | Badge Color | Badge Text | Warning |
-----------|-------------|------------|---------|
low        | 🟢 Green    | "Low Risk" | None    |
medium     | 🟡 Yellow   | "Medium"   | None    |
high       | 🟠 Orange   | "High"     | Warning |
critical   | 🔴 Red      | "Critical" | Alert   |
```

### 5.2 Final Approval Badge

If `final_approval_required = true`:
- Show "🔒 Final Approval Required" badge
- Display checkbox: "I understand the risk"
- Disable "Approve" button until checked
- Two-step confirmation flow

### 5.3 Risky Keywords

If `risky_keywords` contains ["delete", "payment", etc.]:
- Show warning banner: "⚠️ This action uses risky operations (delete, payment, etc.)"
- Enforce final approval

### 5.4 Action Type Indicators

```
browser.inspect          | ℹ️ "Inspect & Report"
browser.plan_click       | 📋 "Plan Click"
browser.plan_type        | 📋 "Plan Type Input"
browser.plan_submit      | 📋 "Plan Submit"
browser.execute_click    | ▶️ "Execute Click"
browser.execute_type     | ▶️ "Execute Type Input"
browser.execute_submit   | ❌ "Not Allowed (Blocked)"
```

---

## 6. Approval Decision Flow

### 6.1 Approval Happy Path

```
[Admin views pending approval]
    ↓
[Checks safe fields, risk badge]
    ↓
[If final_approval_required: checks checkbox]
    ↓
[Clicks "Approve" button]
    ↓
[UI sends decision: {approval_id, task_id, "approve"}]
    ↓
[Server validates approval_id]
    ↓
[Server generates approval_token]
    ↓
[Server sends token to local agent]
    ↓
[Local agent verifies token, executes action]
    ↓
[Result sent back to server]
    ↓
[Admin views executed result]
```

**Key**: approval_token NEVER returned to UI in any step.

---

### 6.2 Rejection Flow

```
[Admin clicks "Reject" button]
    ↓
[Input reason (optional)]
    ↓
[UI sends: {approval_id, task_id, "reject", reason}]
    ↓
[Server marks approval as rejected]
    ↓
[Local agent never receives token]
    ↓
[Admin sees "Rejected" badge]
```

---

### 6.3 Final Approval Flow (Two-Step)

```
[Admin sees critical action with "🔒 Final Approval Required"]
    ↓
[Checkbox unchecked, "Approve" button disabled]
    ↓
[Admin reads warning, understands risk]
    ↓
[Admin checks checkbox]
    ↓
[Approve button enabled]
    ↓
[Admin clicks "Approve"]
    ↓
[Proceeds as normal approval]
```

---

## 7. Mock Data Test Cases

### 7.1 Case 1: Pending Low-Risk Execute Click

```
approval_id: "appr-001"
task_id: "task-001"
action_type: "browser.execute_click"
selector: "#increment-btn"
risk_level: "low"
final_approval_required: false

UI Display:
- Risk badge: "🟢 Low Risk"
- Approve button: ✓ Enabled
- Reject button: ✓ Enabled
- Final approval checkbox: Hidden
- Warning banner: None
```

---

### 7.2 Case 2: Pending Medium-Risk Type Action

```
approval_id: "appr-002"
task_id: "task-002"
action_type: "browser.execute_type"
selector: "#search-input"
risk_level: "medium"
text_length: 15
text_preview: "[REDACTED]"

UI Display:
- Risk badge: "🟡 Medium"
- Input preview: "Typed 15 characters [REDACTED]"
- Approve button: ✓ Enabled
- Reject button: ✓ Enabled
- NEVER show: actual text input
```

---

### 7.3 Case 3: Critical Risk with Final Approval

```
approval_id: "appr-003"
action_type: "browser.execute_click"
selector: "#delete-btn"
risk_level: "critical"
final_approval_required: true
risky_keywords: ["delete"]

UI Display:
- Risk badge: "🔴 Critical"
- Warning: "⚠️ This action uses risky operations (delete)"
- "🔒 Final Approval Required" badge
- Checkbox: "I understand the risk"
- Approve button: ✓ Disabled (until checkbox checked)
- Reject button: ✓ Enabled
```

---

### 7.4 Case 4: Blocked Action (Submit)

```
approval_id: "appr-004"
action_type: "browser.plan_submit"
selector: "#submit-form"
status: "blocked"

UI Display:
- Status: "❌ Blocked"
- Reason: "Action type plan_submit requires final approval"
- Approve button: ❌ Disabled
- Reject button: ❌ Disabled
- Message: "This action cannot be automatically executed"
```

---

### 7.5 Case 5: Executed Success

```
task_id: "task-001"
status: "executed"
action_type: "browser.execute_click"
selector: "#confirm-btn"
executed: true
element_found: true
result: "success"

UI Display:
- Status badge: "✓ Executed"
- Result: "Success"
- Element found: ✓ Yes
- Approve/Reject buttons: Hidden
- Timestamp: "Executed at 2026-05-01 10:30:45"
```

---

### 7.6 Case 6: Execution Failed

```
task_id: "task-999"
status: "failed"
action_type: "browser.execute_click"
selector: "#nonexistent"
executed: false
element_found: false
error_code: "element_not_found"
error_message: "CSS selector '#nonexistent' not found in DOM"

UI Display:
- Status badge: "✗ Failed"
- Error code: "element_not_found"
- Error message: "CSS selector '#nonexistent' not found in DOM"
- Result: "Failed"
- Approve/Reject buttons: Hidden
```

---

## 8. Implementation Checklist

- [x] TypeScript type definitions (`admin-web/src/types/browser-approval.ts`)
- [x] Mock data for all test cases
- [x] UI display rules by status
- [x] Risk assessment visualization
- [x] Final approval flow
- [x] Security rules (no token disclosure)
- [x] Approval decision contract
- [ ] React components (BROWSER-4I)
- [ ] Admin API client update (BROWSER-4I)
- [ ] Integration with real WebSocket (BROWSER-5)

---

## 9. Security Compliance Checklist

- [x] ❌ `approval_token` NEVER in UI
- [x] ❌ `final_approval_token` NEVER in UI
- [x] ❌ `token_hash` NEVER in UI
- [x] ❌ Typed text (raw) NEVER in UI
- [x] ❌ Password, OTP, cookie, session NEVER in UI
- [x] ❌ Full DOM, raw screenshot NEVER in UI
- [x] ✓ `text_length` OK (no content)
- [x] ✓ `text_preview = "[REDACTED]"` OK
- [x] ✓ `screenshot_ref` (reference only) OK
- [x] ✓ Error messages (safe summary) OK
- [x] ✓ Risk assessment visible
- [x] ✓ Status vocabulary clear

---

## 10. References

- **BROWSER-4G**: WebSocket payload schema formalization
- **BROWSER-4F**: Persistent approval store
- **BROWSER-4E**: WebSocket contract (Gaps #1-3)
- **BROWSER-3C**: Approval verification
- **BROWSER-3**: Approval policy

---

**Document Status**: FINAL (Design + Mock Validation)  
**Date Completed**: 2026-05-01  
**Next Stage**: BROWSER-4I (React UI Components)
