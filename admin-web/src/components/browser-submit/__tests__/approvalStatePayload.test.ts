import {
  createApprovalPayload,
  validateApprovalPayload,
  ApprovalDecisionPayload,
} from "../approvalStatePayload";

describe("approvalStatePayload", () => {
  describe("createApprovalPayload", () => {
    it("should create approved payload with all required fields", () => {
      const payload = createApprovalPayload(
        "val_123",
        "hash_xyz",
        "approved",
        "user_admin",
      );

      expect(payload).toEqual({
        approval_status: "approved",
        approved_by: "user_admin",
        approved_at: expect.any(String),
        submitted: false,
        preview_hash: "hash_xyz",
        validation_id: "val_123",
      });
    });

    it("should create cancelled payload with all required fields", () => {
      const payload = createApprovalPayload(
        "val_456",
        "hash_abc",
        "cancelled",
        "user_admin",
      );

      expect(payload).toEqual({
        approval_status: "cancelled",
        cancelled_by: "user_admin",
        cancelled_at: expect.any(String),
        submitted: false,
        preview_hash: "hash_abc",
        validation_id: "val_456",
      });
    });

    it("should create payload without decided_by", () => {
      const payload = createApprovalPayload(
        "val_789",
        "hash_def",
        "approved",
      );

      expect(payload.approval_status).toBe("approved");
      expect(payload.approved_by).toBeUndefined();
      expect(payload.submitted).toBe(false);
    });

    it("should set submitted=false for approved", () => {
      const payload = createApprovalPayload(
        "val_123",
        "hash_xyz",
        "approved",
      );

      expect(payload.submitted).toBe(false);
    });

    it("should set submitted=false for cancelled", () => {
      const payload = createApprovalPayload(
        "val_123",
        "hash_xyz",
        "cancelled",
      );

      expect(payload.submitted).toBe(false);
    });

    it("should include ISO 8601 timestamp for approved_at", () => {
      const payload = createApprovalPayload(
        "val_123",
        "hash_xyz",
        "approved",
      );

      expect(payload.approved_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
    });

    it("should include ISO 8601 timestamp for cancelled_at", () => {
      const payload = createApprovalPayload(
        "val_123",
        "hash_xyz",
        "cancelled",
      );

      expect(payload.cancelled_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
    });

    it("should throw error for invalid approval_status", () => {
      expect(() => {
        createApprovalPayload(
          "val_123",
          "hash_xyz",
          "invalid" as 'approved' | 'cancelled',
        );
      }).toThrow("Invalid approval_status");
    });
  });

  describe("validateApprovalPayload", () => {
    it("should validate correct approved payload", () => {
      const payload: ApprovalDecisionPayload = {
        approval_status: "approved",
        approved_by: "user_admin",
        approved_at: new Date().toISOString(),
        submitted: false,
        preview_hash: "hash_xyz",
        validation_id: "val_123",
      };

      expect(validateApprovalPayload(payload)).toBe(true);
    });

    it("should validate correct cancelled payload", () => {
      const payload: ApprovalDecisionPayload = {
        approval_status: "cancelled",
        cancelled_by: "user_admin",
        cancelled_at: new Date().toISOString(),
        submitted: false,
        preview_hash: "hash_xyz",
        validation_id: "val_123",
      };

      expect(validateApprovalPayload(payload)).toBe(true);
    });

    it("should reject non-object", () => {
      expect(validateApprovalPayload(null)).toBe(false);
      expect(validateApprovalPayload("string")).toBe(false);
      expect(validateApprovalPayload(123)).toBe(false);
    });

    it("should reject invalid approval_status", () => {
      const payload = {
        approval_status: "pending",
        submitted: false,
        preview_hash: "hash",
        validation_id: "val",
      };

      expect(validateApprovalPayload(payload)).toBe(false);
    });

    it("should reject missing approval_status", () => {
      const payload = {
        submitted: false,
        preview_hash: "hash",
        validation_id: "val",
      };

      expect(validateApprovalPayload(payload)).toBe(false);
    });

    it("should reject missing preview_hash", () => {
      const payload = {
        approval_status: "approved",
        submitted: false,
        validation_id: "val",
      };

      expect(validateApprovalPayload(payload)).toBe(false);
    });

    it("should reject missing validation_id", () => {
      const payload = {
        approval_status: "approved",
        submitted: false,
        preview_hash: "hash",
      };

      expect(validateApprovalPayload(payload)).toBe(false);
    });

    it("should reject submitted=true", () => {
      const payload = {
        approval_status: "approved",
        submitted: true,
        preview_hash: "hash",
        validation_id: "val",
      };

      expect(validateApprovalPayload(payload)).toBe(false);
    });

    it("should reject non-boolean submitted", () => {
      const payload = {
        approval_status: "approved",
        submitted: "false",
        preview_hash: "hash",
        validation_id: "val",
      };

      expect(validateApprovalPayload(payload)).toBe(false);
    });

    it("should reject invalid approved_at format", () => {
      const payload = {
        approval_status: "approved",
        approved_at: "invalid",
        submitted: false,
        preview_hash: "hash",
        validation_id: "val",
      };

      expect(validateApprovalPayload(payload)).toBe(false);
    });

    it("should accept optional approved_by", () => {
      const payload = {
        approval_status: "approved",
        approved_by: "user_1",
        submitted: false,
        preview_hash: "hash",
        validation_id: "val",
      };

      expect(validateApprovalPayload(payload)).toBe(true);
    });

    it("should accept payload created by createApprovalPayload", () => {
      const payload = createApprovalPayload(
        "val_123",
        "hash_xyz",
        "approved",
        "user_admin",
      );

      expect(validateApprovalPayload(payload)).toBe(true);
    });
  });
});
