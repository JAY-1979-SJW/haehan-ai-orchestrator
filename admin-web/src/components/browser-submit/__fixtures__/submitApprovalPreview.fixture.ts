/**
 * Mock Submit Approval Preview Fixture
 *
 * Test data for browser submit approval UI
 * - No production domains
 * - No real credentials
 * - internal.mock for display only
 */

export interface UserPreviewSummary {
  site_id: string;
  form_title: string;
  target_description: string;
  field_summary: Record<string, string>;
  risk_level: "low" | "medium" | "high";
  risk_description: string;
  is_destructive: boolean;
  destructive_warning: string;
  requires_confirmation: boolean;
  confirmation_question: string;
}

export interface UserPreviewDetails {
  site_id: string;
  origin: string;
  form_id: string;
  submit_button_id: string;
  intent: string;
  policy_verdict: "ALLOW" | "DENY";
  prompt_injection_verdict: string;
  hidden_fields_verdict: string;
  denied_fields_verdict: string;
  validator_reasons: string[];
  preview_hash: string;
  validation_id: string;
}

export interface AuditPreviewRecord {
  event_id: string;
  preview_hash: string;
  validation_id: string;
  action_id: string;
  user_id?: string;
  tenant_id?: string;
  site_id: string;
  form_id: string;
  submit_button_id: string;
  policy_verdict: "ALLOW" | "DENY";
  user_confirmed: boolean;
  submitted: boolean;
  submit_result: "pending" | "success" | "blocked" | "error" | "not_submitted";
  redacted_payload: Record<string, unknown>;
  created_at: string;
}

export interface SubmitApprovalPreviewFixture {
  user_preview_summary: UserPreviewSummary;
  user_preview_details: UserPreviewDetails;
  audit_preview_record: AuditPreviewRecord;
  preview_hash: string;
  validation_id: string;
  risk_level: "HIGH";
  policy_verdict: "ALLOW";
  submitted: boolean;
  submit_result: "pending" | "not_submitted";
}

/**
 * Mock approval preview for contact form
 *
 * Scenario:
 * - User attempts to submit contact form to internal.mock
 * - Policy allows the submission
 * - High risk due to form submission
 * - Awaiting user approval
 */
export const mockSubmitApprovalPreview: SubmitApprovalPreviewFixture = {
  user_preview_summary: {
    site_id: "allowed_internal_mock_form",
    form_title: "Contact Form Submission",
    target_description: "Internal contact form at internal.mock",
    field_summary: {
      email: "user@internal.mock",
      message: "Contact request regarding product inquiry",
      "Hidden fields": "3 fields (CSRF token, timestamp, version)",
    },
    risk_level: "high",
    risk_description:
      "Form submission is irreversible. Once submitted, the action cannot be undone.",
    is_destructive: true,
    destructive_warning:
      "이 작업은 되돌릴 수 없습니다. 신중히 검토 후 승인해주세요.",
    requires_confirmation: true,
    confirmation_question: "정말 이 폼을 제출하시겠습니까?",
  },

  user_preview_details: {
    site_id: "allowed_internal_mock_form",
    origin: "internal.mock",
    form_id: "contact_form",
    submit_button_id: "submit_button_id",
    intent: "submit_contact_form",
    policy_verdict: "ALLOW",
    prompt_injection_verdict: "SAFE",
    hidden_fields_verdict: "SAFE",
    denied_fields_verdict: "NONE",
    validator_reasons: [
      "Site is in internal allowlist",
      "Form is approved for submission",
      "No injection attempts detected",
      "All fields pass validation",
    ],
    preview_hash:
      "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234",
    validation_id: "smoke_approval_001",
  },

  audit_preview_record: {
    event_id: "evt_20260506_001_test1234",
    preview_hash:
      "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234",
    validation_id: "smoke_approval_001",
    action_id: "browser.submit.controlled_click",
    user_id: "user_admin_001",
    tenant_id: "tenant_default",
    site_id: "allowed_internal_mock_form",
    form_id: "contact_form",
    submit_button_id: "submit_button_id",
    policy_verdict: "ALLOW",
    user_confirmed: false, // Awaiting approval
    submitted: false, // Not yet submitted
    submit_result: "pending",
    redacted_payload: {
      email: "user@internal.mock",
      message: "Contact request regarding product inquiry",
      csrf_token: { masked: true },
      timestamp: "2026-05-06T12:00:00Z",
      form_version: "1.0",
    },
    created_at: "2026-05-06T12:00:00Z",
  },

  preview_hash:
    "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234",
  validation_id: "smoke_approval_001",
  risk_level: "HIGH",
  policy_verdict: "ALLOW",
  submitted: false,
  submit_result: "pending",
};

/**
 * Minimal fixture for snapshot testing
 */
export const mockMinimalApprovalPreview: SubmitApprovalPreviewFixture = {
  user_preview_summary: {
    site_id: "test_form",
    form_title: "Test Form",
    target_description: "Test form submission",
    field_summary: {
      field1: "value1",
    },
    risk_level: "high",
    risk_description: "Irreversible action",
    is_destructive: true,
    destructive_warning: "Cannot be undone",
    requires_confirmation: true,
    confirmation_question: "Confirm?",
  },

  user_preview_details: {
    site_id: "test_form",
    origin: "internal.mock",
    form_id: "test_form_id",
    submit_button_id: "submit_btn",
    intent: "test_intent",
    policy_verdict: "ALLOW",
    prompt_injection_verdict: "SAFE",
    hidden_fields_verdict: "SAFE",
    denied_fields_verdict: "NONE",
    validator_reasons: ["Allowed"],
    preview_hash: "a" + "b".repeat(63),
    validation_id: "test_001",
  },

  audit_preview_record: {
    event_id: "evt_test_001",
    preview_hash: "a" + "b".repeat(63),
    validation_id: "test_001",
    action_id: "browser.submit.controlled_click",
    site_id: "test_form",
    form_id: "test_form_id",
    submit_button_id: "submit_btn",
    policy_verdict: "ALLOW",
    user_confirmed: false,
    submitted: false,
    submit_result: "pending",
    redacted_payload: { field1: "value1" },
    created_at: "2026-05-06T12:00:00Z",
  },

  preview_hash: "a" + "b".repeat(63),
  validation_id: "test_001",
  risk_level: "HIGH",
  policy_verdict: "ALLOW",
  submitted: false,
  submit_result: "pending",
};

/**
 * Already approved fixture
 */
export const mockApprovedApprovalPreview: SubmitApprovalPreviewFixture = {
  ...mockSubmitApprovalPreview,
  audit_preview_record: {
    ...mockSubmitApprovalPreview.audit_preview_record,
    user_confirmed: true,
    submitted: false,
    submit_result: "pending", // Approved but not yet executed
  },
};

/**
 * Cancelled fixture
 */
export const mockCancelledApprovalPreview: SubmitApprovalPreviewFixture = {
  ...mockSubmitApprovalPreview,
  audit_preview_record: {
    ...mockSubmitApprovalPreview.audit_preview_record,
    user_confirmed: false,
    submitted: false,
    submit_result: "blocked", // User cancelled
  },
};

/**
 * Fixture with sensitive field masking (should never show raw values)
 */
export const mockRedactedApprovalPreview: SubmitApprovalPreviewFixture = {
  ...mockSubmitApprovalPreview,
  audit_preview_record: {
    ...mockSubmitApprovalPreview.audit_preview_record,
    redacted_payload: {
      email: "test@internal.mock",
      password: { masked: true }, // Never show raw password
      api_token: { masked: true }, // Never show raw token
      csrf_token: { masked: true }, // Safe hidden field masked for extra safety
      timestamp: "2026-05-06T12:00:00Z",
      form_version: "1.0",
    },
  },
};
