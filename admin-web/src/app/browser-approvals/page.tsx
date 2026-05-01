/**
 * Browser approvals mock page (BROWSER-4I)
 *
 * Demo page showing browser action approval workflow with mock data.
 * This page demonstrates the UI contract without real API/WebSocket connections.
 */

import { PageShell } from "@/components/ui/PageShell";
import { BrowserApprovalMockPanel } from "@/components/browser-approval";

export const metadata = {
  title: "Browser Approvals - Admin",
  description: "Browser action approval workflow (mock data)",
};

export default function BrowserApprovalsPage() {
  return (
    <PageShell
      title="Browser Approvals"
      description="Browser action approval workflow (mock data)"
    >
      <BrowserApprovalMockPanel />
    </PageShell>
  );
}
