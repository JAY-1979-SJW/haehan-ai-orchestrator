/**
 * Approval State Payload Helper Functions
 *
 * Generates and validates approval decision payloads for SubmitApprovalPanel.
 * Payload format:
 * - approval_status: "approved" or "cancelled"
 * - submitted: false (UI state only, no actual form submission)
 * - validation_id, preview_hash: link to approval state log
 * - approved_by/approved_at or cancelled_by/cancelled_at: metadata
 */

export interface ApprovalDecisionPayload {
  approval_status: 'approved' | 'cancelled';
  approved_by?: string;
  approved_at?: string;
  cancelled_by?: string;
  cancelled_at?: string;
  submitted: boolean;
  submit_result?: string;
  preview_hash: string;
  validation_id: string;
}

/**
 * Create an approval decision payload.
 *
 * @param validation_id - Validation ID from preview
 * @param preview_hash - Preview hash for linking to approval state log
 * @param approval_status - "approved" or "cancelled"
 * @param decided_by - User/system that made decision (optional)
 * @returns ApprovalDecisionPayload
 */
export function createApprovalPayload(
  validation_id: string,
  preview_hash: string,
  approval_status: 'approved' | 'cancelled',
  decided_by?: string,
): ApprovalDecisionPayload {
  const now = new Date().toISOString();

  if (approval_status === 'approved') {
    return {
      approval_status: 'approved',
      approved_by: decided_by,
      approved_at: now,
      submitted: false,
      preview_hash,
      validation_id,
    };
  } else if (approval_status === 'cancelled') {
    return {
      approval_status: 'cancelled',
      cancelled_by: decided_by,
      cancelled_at: now,
      submitted: false,
      preview_hash,
      validation_id,
    };
  } else {
    throw new Error(`Invalid approval_status: ${approval_status}`);
  }
}

/**
 * Validate an approval decision payload.
 *
 * @param payload - Object to validate
 * @returns true if payload is valid ApprovalDecisionPayload
 */
export function validateApprovalPayload(
  payload: unknown,
): payload is ApprovalDecisionPayload {
  if (!payload || typeof payload !== 'object') {
    return false;
  }

  const p = payload as Record<string, unknown>;

  // Required fields
  if (!p.approval_status || typeof p.approval_status !== 'string') {
    return false;
  }
  if (p.approval_status !== 'approved' && p.approval_status !== 'cancelled') {
    return false;
  }

  if (!p.preview_hash || typeof p.preview_hash !== 'string') {
    return false;
  }

  if (!p.validation_id || typeof p.validation_id !== 'string') {
    return false;
  }

  // submitted must be false (UI state only)
  if (typeof p.submitted !== 'boolean' || p.submitted !== false) {
    return false;
  }

  // Optional timestamp fields (if present, must be ISO 8601 string)
  if (p.approved_at && typeof p.approved_at !== 'string') {
    return false;
  }
  if (p.cancelled_at && typeof p.cancelled_at !== 'string') {
    return false;
  }

  // Optional user fields
  if (p.approved_by && typeof p.approved_by !== 'string') {
    return false;
  }
  if (p.cancelled_by && typeof p.cancelled_by !== 'string') {
    return false;
  }

  return true;
}
