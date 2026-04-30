export type RegistrationCodeStatus =
  | "active"
  | "used"
  | "expired"
  | "revoked"
  | (string & {});

export type RegistrationAction =
  | "open_url"
  | "capture_screenshot"
  | (string & {});

export interface RegistrationCodeSummary {
  code_id: string;
  label: string;
  allowed_actions: string[];
  expires_at: string;
  created_at: string;
  issued_by: string;
  issuer_role: string;
  note: string;
  status: RegistrationCodeStatus;
  used_at: string;
  used_by_agent_id: string;
  revoked_at: string;
  revoked_by: string;
}

export interface RegistrationCodeListResponse {
  codes: RegistrationCodeSummary[];
}

export interface IssueRegistrationCodeRequest {
  label: string;
  expires_in_minutes: number;
  allowed_actions: RegistrationAction[];
  note?: string;
}

/** Issue 응답: registration_code 평문은 이 응답에서만 1회 노출. 장기 보존 금지. */
export interface IssueRegistrationCodeResponse {
  code_id: string;
  registration_code: string;
  label: string;
  allowed_actions: string[];
  expires_at: string;
  created_at: string;
}

export interface RevokeRegistrationCodeResponse {
  code_id: string;
  status: RegistrationCodeStatus;
  revoked_at: string;
  revoked_by: string;
  label: string;
}
