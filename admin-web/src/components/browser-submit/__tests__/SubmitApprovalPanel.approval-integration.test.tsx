import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SubmitApprovalPanel from "../SubmitApprovalPanel";
import {
  createApprovalPayload,
  validateApprovalPayload,
  ApprovalDecisionPayload,
} from "../approvalStatePayload";
import { SubmitApprovalPreviewFixture } from "../__fixtures__/submitApprovalPreview.fixture";

describe("SubmitApprovalPanel - Approval State Integration", () => {
  const mockFixture: SubmitApprovalPreviewFixture = {
    validation_id: "val_integration_test_123",
    preview_hash: "hash_integration_test_xyz",
    user_preview_summary: {
      site_id: "site_1",
      form_title: "Test Form",
      risk_level: "low",
      field_count: 5,
    },
    user_preview_details: {
      form_id: "form_123",
      submit_button_id: "btn_submit",
      policy_verdict: {
        prompt_injection: "safe",
        hidden_fields: "none",
        denied_fields: [],
      },
    },
    audit_preview_record: {
      redacted_payload: {
        field1: "[redacted]",
        field2: "[redacted]",
      },
    },
  };

  describe("상태 변경 (State Changes)", () => {
    it("should change state from pending to approved on approve click", async () => {
      const { getByTestId } = render(
        <SubmitApprovalPanel preview={mockFixture} />,
      );

      expect(getByTestId("approval-status-badge")).toHaveTextContent("대기 중");

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        expect(getByTestId("approval-status-badge")).toHaveTextContent(
          "승인됨",
        );
      });
    });

    it("should change state from pending to cancelled on cancel click", async () => {
      const { getByTestId } = render(
        <SubmitApprovalPanel preview={mockFixture} />,
      );

      expect(getByTestId("approval-status-badge")).toHaveTextContent("대기 중");

      fireEvent.click(getByTestId("cancel-button"));

      await waitFor(() => {
        expect(getByTestId("approval-status-badge")).toHaveTextContent(
          "취소됨",
        );
      });
    });

    it("should show pending state with approve and cancel buttons", () => {
      const { getByTestId } = render(
        <SubmitApprovalPanel preview={mockFixture} />,
      );

      expect(getByTestId("approval-status-badge")).toHaveTextContent("대기 중");
      expect(getByTestId("approve-button")).toBeInTheDocument();
      expect(getByTestId("cancel-button")).toBeInTheDocument();
    });

    it("should show approved state with confirmation message", async () => {
      const { getByTestId } = render(
        <SubmitApprovalPanel preview={mockFixture} />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        expect(getByTestId("approved-message")).toBeInTheDocument();
        expect(getByTestId("approved-message")).toHaveTextContent("승인 완료");
      });
    });
  });

  describe("Payload 생성 (Payload Creation)", () => {
    it("should call onApprovalDecision with approved payload on approve", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledWith(
          expect.objectContaining({
            approval_status: "approved",
            validation_id: mockFixture.validation_id,
            preview_hash: mockFixture.preview_hash,
            submitted: false,
          }),
        );
      });
    });

    it("should call onApprovalDecision with cancelled payload on cancel", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("cancel-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledWith(
          expect.objectContaining({
            approval_status: "cancelled",
            validation_id: mockFixture.validation_id,
            preview_hash: mockFixture.preview_hash,
            submitted: false,
          }),
        );
      });
    });

    it("should include validation_id in payload", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledWith(
          expect.objectContaining({
            validation_id: "val_integration_test_123",
          }),
        );
      });
    });

    it("should include preview_hash in payload", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("cancel-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledWith(
          expect.objectContaining({
            preview_hash: "hash_integration_test_xyz",
          }),
        );
      });
    });
  });

  describe("콜백 호출 (Callback Invocation)", () => {
    it("should call onApprovalDecision on approve click", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledTimes(1);
      });
    });

    it("should call onApprovalDecision on cancel click", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("cancel-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledTimes(1);
      });
    });

    it("should pass valid payload to onApprovalDecision", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledWith(
          expect.any(Object),
        );

        const payload = mockCallback.mock.calls[0][0];
        expect(validateApprovalPayload(payload)).toBe(true);
      });
    });
  });

  describe("네트워크 및 제출 금지 (No Network/Submit)", () => {
    it("should not make fetch call on approve", async () => {
      const originalFetch = global.fetch;
      const fetchMock = jest.fn();
      global.fetch = fetchMock as any;

      try {
        const { getByTestId } = render(
          <SubmitApprovalPanel preview={mockFixture} />,
        );

        fireEvent.click(getByTestId("approve-button"));

        await waitFor(() => {
          expect(fetchMock).not.toHaveBeenCalled();
        });
      } finally {
        global.fetch = originalFetch;
      }
    });

    it("should not make fetch call on cancel", async () => {
      const originalFetch = global.fetch;
      const fetchMock = jest.fn();
      global.fetch = fetchMock as any;

      try {
        const { getByTestId } = render(
          <SubmitApprovalPanel preview={mockFixture} />,
        );

        fireEvent.click(getByTestId("cancel-button"));

        await waitFor(() => {
          expect(fetchMock).not.toHaveBeenCalled();
        });
      } finally {
        global.fetch = originalFetch;
      }
    });

    it("should not actually submit form", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalled();
        const payload = mockCallback.mock.calls[0][0];
        expect(payload.submitted).toBe(false);
      });
    });
  });

  describe("Payload 검증 (Payload Validation)", () => {
    it("should create valid approved payload", () => {
      const payload = createApprovalPayload(
        mockFixture.validation_id,
        mockFixture.preview_hash,
        "approved",
      );

      expect(validateApprovalPayload(payload)).toBe(true);
    });

    it("should create valid cancelled payload", () => {
      const payload = createApprovalPayload(
        mockFixture.validation_id,
        mockFixture.preview_hash,
        "cancelled",
      );

      expect(validateApprovalPayload(payload)).toBe(true);
    });

    it("should maintain submitted=false in payload", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        const payload = mockCallback.mock.calls[0][0];
        expect(payload.submitted).toBe(false);
      });
    });

    it("should include required fields in all payloads", async () => {
      const mockCallback = jest.fn();
      const { getByTestId } = render(
        <SubmitApprovalPanel
          preview={mockFixture}
          onApprovalDecision={mockCallback}
        />,
      );

      fireEvent.click(getByTestId("approve-button"));

      await waitFor(() => {
        const payload = mockCallback.mock.calls[0][0];
        expect(payload).toHaveProperty("approval_status");
        expect(payload).toHaveProperty("validation_id");
        expect(payload).toHaveProperty("preview_hash");
        expect(payload).toHaveProperty("submitted");
      });
    });
  });
});
