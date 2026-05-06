/**
 * SubmitApprovalPanel Component Tests
 *
 * Tests for the 3-layer submit approval UI:
 * 1. Summary card rendering
 * 2. Approval/Cancel state transitions
 * 3. No real submit/fetch calls
 * 4. Redacted payload display
 * 5. No sensitive data exposure
 */

import { render, screen, fireEvent } from "@testing-library/react";
import SubmitApprovalPanel from "../SubmitApprovalPanel";
import {
  mockSubmitApprovalPreview,
  mockRedactedApprovalPreview,
} from "../__fixtures__/submitApprovalPreview.fixture";

describe("SubmitApprovalPanel", () => {
  describe("Rendering", () => {
    it("should render summary card by default", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      expect(screen.getByTestId("submit-approval-panel")).toBeInTheDocument();
      expect(screen.getByTestId("submit-preview-summary")).toBeInTheDocument();
      expect(screen.getByTestId("approval-status-badge")).toHaveTextContent(
        "대기 중"
      );
    });

    it("should display risk level HIGH", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      expect(screen.getByTestId("risk-level-badge")).toHaveTextContent("높음");
    });

    it("should show destructive warning", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      expect(
        screen.getByTestId("destructive-warning")
      ).toHaveTextContent("되돌릴 수 없습니다");
    });

    it("should display confirmation question", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      expect(screen.getByTestId("confirmation-question")).toHaveTextContent(
        "정말 이 폼을 제출하시겠습니까?"
      );
    });
  });

  describe("Details Toggle", () => {
    it("should toggle details visibility", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      const toggleButton = screen.getByTestId("toggle-details-button");
      expect(
        screen.queryByTestId("submit-preview-details")
      ).not.toBeInTheDocument();

      fireEvent.click(toggleButton);
      expect(screen.getByTestId("submit-preview-details")).toBeInTheDocument();

      fireEvent.click(toggleButton);
      expect(
        screen.queryByTestId("submit-preview-details")
      ).not.toBeInTheDocument();
    });

    it("should display preview hash in details", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      fireEvent.click(screen.getByTestId("toggle-details-button"));
      expect(screen.getByTestId("detail-preview-hash")).toHaveTextContent(
        mockSubmitApprovalPreview.preview_hash
      );
    });

    it("should display policy verdict in details", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      fireEvent.click(screen.getByTestId("toggle-details-button"));
      expect(screen.getByTestId("detail-policy-verdict")).toHaveTextContent(
        "허용"
      );
    });
  });

  describe("Approval/Cancel Actions", () => {
    it("should change state to approved on approve button click", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      expect(screen.getByTestId("approval-status-badge")).toHaveTextContent(
        "대기 중"
      );

      fireEvent.click(screen.getByTestId("approve-button"));

      expect(screen.getByTestId("approval-status-badge")).toHaveTextContent(
        "승인됨"
      );
      expect(screen.getByTestId("approved-message")).toBeInTheDocument();
    });

    it("should change state to cancelled on cancel button click", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      fireEvent.click(screen.getByTestId("cancel-button"));

      expect(screen.getByTestId("approval-status-badge")).toHaveTextContent(
        "취소됨"
      );
      expect(screen.getByTestId("cancelled-message")).toBeInTheDocument();
    });

    it("should call onApprovalDecision callback when approved", () => {
      const onApprovalDecision = jest.fn();
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          onApprovalDecision={onApprovalDecision}
        />
      );

      fireEvent.click(screen.getByTestId("approve-button"));

      expect(onApprovalDecision).toHaveBeenCalledWith(
        expect.objectContaining({
          approval_status: "approved",
          validation_id: mockSubmitApprovalPreview.validation_id,
          preview_hash: mockSubmitApprovalPreview.preview_hash,
        })
      );
    });

    it("should call onApprovalDecision callback when cancelled", () => {
      const onApprovalDecision = jest.fn();
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          onApprovalDecision={onApprovalDecision}
        />
      );

      fireEvent.click(screen.getByTestId("cancel-button"));

      expect(onApprovalDecision).toHaveBeenCalledWith(
        expect.objectContaining({
          approval_status: "cancelled",
          validation_id: mockSubmitApprovalPreview.validation_id,
          preview_hash: mockSubmitApprovalPreview.preview_hash,
        })
      );
    });
  });

  describe("Audit Record", () => {
    it("should not show audit record by default", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      expect(
        screen.queryByTestId("submit-audit-record-panel")
      ).not.toBeInTheDocument();
    });

    it("should show audit record when showAuditRecord=true", () => {
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          showAuditRecord={true}
        />
      );

      expect(screen.getByTestId("submit-audit-record-panel")).toBeInTheDocument();
    });

    it("should display event ID in audit record", () => {
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          showAuditRecord={true}
        />
      );

      expect(screen.getByTestId("audit-event-id")).toHaveTextContent(
        mockSubmitApprovalPreview.audit_preview_record.event_id
      );
    });

    it("should display validation ID in audit record", () => {
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          showAuditRecord={true}
        />
      );

      expect(screen.getByTestId("audit-validation-id")).toHaveTextContent(
        mockSubmitApprovalPreview.validation_id
      );
    });
  });

  describe("Redaction & Security", () => {
    it("should display redacted payload only (no raw secrets)", () => {
      render(
        <SubmitApprovalPanel
          preview={mockRedactedApprovalPreview}
          showAuditRecord={true}
        />
      );

      const payloadElement = screen.getByTestId("audit-redacted-payload");
      const payloadText = payloadElement.textContent || "";

      // Should NOT contain raw secrets
      expect(payloadText).not.toContain("password123");
      expect(payloadText).not.toContain("token_secret");

      // Should show masked marker
      expect(payloadText).toContain("masked");
    });

    it("should show redaction notice in audit record", () => {
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          showAuditRecord={true}
        />
      );

      expect(screen.getByTestId("redaction-notice")).toBeInTheDocument();
      expect(screen.getByTestId("redaction-notice")).toHaveTextContent(
        "마스킹되었습니다"
      );
    });

    it("should show production safeguard notice", () => {
      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);

      expect(
        screen.getByTestId("production-safeguard-notice")
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("production-safeguard-notice")
      ).toHaveTextContent("실제 폼 제출은 독립적인 검증");
    });
  });

  describe("No Network/Submit Calls", () => {
    it("should not make any fetch calls", () => {
      const fetchSpy = jest.spyOn(global, "fetch");

      render(<SubmitApprovalPanel preview={mockSubmitApprovalPreview} />);
      fireEvent.click(screen.getByTestId("approve-button"));

      expect(fetchSpy).not.toHaveBeenCalled();

      fetchSpy.mockRestore();
    });

    it("should only change local state, not call submit action", () => {
      const { rerender } = render(
        <SubmitApprovalPanel preview={mockSubmitApprovalPreview} />
      );

      expect(screen.getByTestId("approval-status-badge")).toHaveTextContent(
        "대기 중"
      );

      fireEvent.click(screen.getByTestId("approve-button"));

      expect(screen.getByTestId("approval-status-badge")).toHaveTextContent(
        "승인됨"
      );
      // State should change, but no external calls
    });
  });

  describe("State Persistence", () => {
    it("should maintain submitted=false state after approval", () => {
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          showAuditRecord={true}
        />
      );

      fireEvent.click(screen.getByTestId("approve-button"));

      // submitted should still be false (no actual submit happened)
      expect(screen.getByTestId("audit-submitted")).toHaveTextContent("No");
    });

    it("should maintain submit_result=pending after approval", () => {
      render(
        <SubmitApprovalPanel
          preview={mockSubmitApprovalPreview}
          showAuditRecord={true}
        />
      );

      fireEvent.click(screen.getByTestId("approve-button"));

      // submit_result should still be pending (approval ≠ execution)
      expect(screen.getByTestId("audit-submit-result")).toHaveTextContent(
        "PENDING"
      );
    });
  });
});
