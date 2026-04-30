/**
 * Browser Approval UI Contract (BROWSER-4H)
 *
 * Defines the data structures for admin UI to display and manage browser action approvals.
 *
 * Design principles:
 * 1. approval_token NEVER shown in UI
 * 2. final_approval_token NEVER shown in UI
 * 3. token_hash NEVER shown in UI
 * 4. typed_text NEVER shown (use text_length only)
 * 5. Only safe fields from result_data shown
 * 6. Risk level determines approval workflow
 * 7. Certain keywords (delete, submit, payment) require final approval
 */

/**
 * Allowed browser action types
 */
export type BrowserActionType =
  | "browser.inspect"
  | "browser.plan_click"
  | "browser.plan_type"
  | "browser.plan_submit"
  | "browser.execute_click"
  | "browser.execute_type";

/**
 * Risk levels for browser actions
 */
export type BrowserRiskLevel = "low" | "medium" | "high" | "critical";

/**
 * Approval status
 */
export type BrowserApprovalStatus =
  | "received"
  | "validation_failed"
  | "approval_denied"
  | "approval_invalid"
  | "blocked"
  | "executed"
  | "failed"
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "used";

/**
 * Result status for executed tasks
 */
export type BrowserTaskResultStatus =
  | "executed"
  | "blocked"
  | "failed"
  | "success"
  | "error";

/**
 * Browser approval request (safe version for Admin UI display)
 *
 * NEVER contains:
 * - approval_token
 * - final_approval_token
 * - token_hash
 * - typed_text (use text_length instead)
 * - password, OTP, cookie, session
 *
 * MAY contain (safe fields only):
 * - task_id, action_type, selector
 * - risk_level, final_approval_required
 * - target_url_domain
 * - requested_by, created_at, expires_at
 */
export interface BrowserApprovalRequestDisplay {
  // Approval metadata
  approval_id: string;
  task_id: string;
  status: BrowserApprovalStatus;

  // Action info
  action_type: BrowserActionType;
  selector: string;
  target_url_domain?: string;

  // Risk assessment
  risk_level: BrowserRiskLevel;
  final_approval_required: boolean;
  risky_keywords?: string[]; // e.g., ["delete", "submit", "payment"]

  // Request metadata
  requested_by?: string;
  created_at?: string; // ISO8601
  expires_at?: string; // ISO8601 (if approval expires)

  // Action-specific optional fields
  value?: string; // For execute_type (always "[REDACTED]" in UI)
  text_length?: number; // Length of text typed (NOT the text itself)

  // UI control flags
  can_approve: boolean;
  can_reject: boolean;
  can_execute: boolean;
  requires_final_approval_input: boolean;
  approval_expired: boolean;
  approval_used: boolean;
}

/**
 * Browser task execution result (safe version for Admin UI display)
 *
 * NEVER contains:
 * - approval_token, final_approval_token, token_hash
 * - typed_text, password, OTP, cookie, session
 * - Authorization header, localStorage, sessionStorage
 * - raw screenshot or base64
 * - full DOM
 *
 * MAY contain (safe fields only):
 * - task_id, status, action_type, selector
 * - executed, element_found, result
 * - error_code, error_message
 * - target_url_domain, text_length, text_preview="[REDACTED]"
 * - screenshot_ref (reference only, not content)
 */
export interface BrowserTaskResultDisplay {
  // Result metadata
  task_id: string;
  status: BrowserTaskResultStatus;

  // Execution details
  action_type: BrowserActionType;
  selector: string;
  executed: boolean;
  element_found: boolean;
  result: string; // "success", "error", etc.

  // Risk assessment (final)
  risk_level: BrowserRiskLevel;
  final_approval_required: boolean;

  // Location info
  target_url_domain?: string;

  // Text input info (safe)
  text_length: number; // Length of typed text
  text_preview: "[REDACTED]"; // Always redacted

  // Error info (if failed)
  error_code?: string;
  error_message?: string;

  // Screenshot reference (metadata only, no content)
  screenshot_taken: boolean;
  screenshot_ref?: string; // Reference/path, never content

  // Timestamps
  executed_at?: string;
}

/**
 * Admin approval decision action
 *
 * NEVER contains:
 * - approval_token
 * - final_approval_token
 * - token_hash
 *
 * Contains only:
 * - approval_id (for reference)
 * - decision (approve, reject)
 * - reason (optional, for reject)
 */
export interface BrowserApprovalDecision {
  approval_id: string;
  task_id: string;
  decision: "approve" | "reject";
  reason?: string; // Required if decision is "reject"
  approved_by?: string; // Admin user ID
  final_approval_requested?: boolean; // If true, requires additional final approval step
}

/**
 * Response after approval decision
 */
export interface BrowserApprovalDecisionResponse {
  approval_id: string;
  task_id: string;
  status: BrowserApprovalStatus;
  decision_made_at: string;
  decided_by: string;
  next_action: "execute" | "blocked" | "pending_final_approval" | "rejected";
}

/**
 * UI display rules based on approval context
 */
export interface BrowserApprovalUIRules {
  // Button visibility
  showApproveButton: boolean;
  showRejectButton: boolean;
  showFinalApprovalCheckbox: boolean;
  showExecuteButton: boolean;

  // Visual indicators
  riskBadgeColor: "green" | "yellow" | "orange" | "red";
  riskBadgeText: string;
  statusBadgeColor: string;
  statusBadgeText: string;

  // Warnings
  showWarningBanner: boolean;
  warningMessage?: string;

  // Content visibility
  showResultData: boolean;
  showErrorDetails: boolean;
  showScreenshotReference: boolean;

  // Action restrictions
  disableApproveReason?: string;
  disableRejectReason?: string;
  disableExecuteReason?: string;
}

/**
 * Approval card display with full context
 */
export interface BrowserApprovalCard {
  request: BrowserApprovalRequestDisplay;
  result?: BrowserTaskResultDisplay;
  uiRules: BrowserApprovalUIRules;
}

/**
 * Mock data for testing
 */
export const MOCK_BROWSER_APPROVAL_REQUESTS: BrowserApprovalRequestDisplay[] = [
  // Pending low-risk action
  {
    approval_id: "appr-001",
    task_id: "task-001",
    status: "received",
    action_type: "browser.execute_click",
    selector: "#increment-btn",
    risk_level: "low",
    final_approval_required: false,
    target_url_domain: "example.com",
    requested_by: "user-123",
    created_at: new Date(Date.now() - 5 * 60000).toISOString(),
    expires_at: new Date(Date.now() + 55 * 60000).toISOString(),
    can_approve: true,
    can_reject: true,
    can_execute: true,
    requires_final_approval_input: false,
    approval_expired: false,
    approval_used: false,
  },

  // Pending medium-risk type action
  {
    approval_id: "appr-002",
    task_id: "task-002",
    status: "received",
    action_type: "browser.execute_type",
    selector: "#search-input",
    risk_level: "medium",
    final_approval_required: false,
    target_url_domain: "search.example.com",
    requested_by: "user-456",
    created_at: new Date(Date.now() - 10 * 60000).toISOString(),
    expires_at: new Date(Date.now() + 50 * 60000).toISOString(),
    value: "[REDACTED]",
    text_length: 15,
    text_preview: "[REDACTED]",
    can_approve: true,
    can_reject: true,
    can_execute: true,
    requires_final_approval_input: false,
    approval_expired: false,
    approval_used: false,
  },

  // Risky action requiring final approval
  {
    approval_id: "appr-003",
    task_id: "task-003",
    status: "received",
    action_type: "browser.execute_click",
    selector: "#delete-btn",
    risk_level: "critical",
    final_approval_required: true,
    risky_keywords: ["delete"],
    target_url_domain: "admin.example.com",
    requested_by: "user-789",
    created_at: new Date(Date.now() - 2 * 60000).toISOString(),
    expires_at: new Date(Date.now() + 58 * 60000).toISOString(),
    can_approve: false, // Requires final approval checkbox first
    can_reject: true,
    can_execute: false,
    requires_final_approval_input: true,
    approval_expired: false,
    approval_used: false,
  },

  // Blocked action (submit)
  {
    approval_id: "appr-004",
    task_id: "task-004",
    status: "blocked",
    action_type: "browser.plan_submit",
    selector: "#submit-form",
    risk_level: "high",
    final_approval_required: true,
    risky_keywords: ["submit"],
    target_url_domain: "form.example.com",
    requested_by: "user-111",
    created_at: new Date(Date.now() - 15 * 60000).toISOString(),
    can_approve: false,
    can_reject: false,
    can_execute: false,
    requires_final_approval_input: false,
    approval_expired: false,
    approval_used: false,
  },

  // Already executed
  {
    approval_id: "appr-005",
    task_id: "task-005",
    status: "used",
    action_type: "browser.execute_click",
    selector: "#confirm-btn",
    risk_level: "low",
    final_approval_required: false,
    target_url_domain: "dialog.example.com",
    requested_by: "user-222",
    created_at: new Date(Date.now() - 30 * 60000).toISOString(),
    can_approve: false,
    can_reject: false,
    can_execute: false,
    requires_final_approval_input: false,
    approval_expired: false,
    approval_used: true,
  },
];

export const MOCK_BROWSER_TASK_RESULTS: BrowserTaskResultDisplay[] = [
  {
    task_id: "task-001",
    status: "executed",
    action_type: "browser.execute_click",
    selector: "#increment-btn",
    executed: true,
    element_found: true,
    result: "success",
    risk_level: "low",
    final_approval_required: false,
    target_url_domain: "example.com",
    text_length: 0,
    text_preview: "[REDACTED]",
    screenshot_taken: false,
    executed_at: new Date(Date.now() - 2 * 60000).toISOString(),
  },

  {
    task_id: "task-002",
    status: "executed",
    action_type: "browser.execute_type",
    selector: "#search-input",
    executed: true,
    element_found: true,
    result: "success",
    risk_level: "medium",
    final_approval_required: false,
    target_url_domain: "search.example.com",
    text_length: 15,
    text_preview: "[REDACTED]",
    screenshot_taken: false,
    executed_at: new Date(Date.now() - 5 * 60000).toISOString(),
  },

  {
    task_id: "task-999",
    status: "failed",
    action_type: "browser.execute_click",
    selector: "#nonexistent",
    executed: false,
    element_found: false,
    result: "error",
    risk_level: "low",
    final_approval_required: false,
    target_url_domain: "example.com",
    text_length: 0,
    text_preview: "[REDACTED]",
    error_code: "element_not_found",
    error_message: "CSS selector '#nonexistent' not found in DOM",
    screenshot_taken: false,
  },
];
