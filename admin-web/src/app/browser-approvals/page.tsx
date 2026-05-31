/**
 * Browser approvals page (BROWSER-4I)
 *
 * Real approval workflow page using actual API integration.
 * Displays and manages browser action approval requests.
 */

import { PageShell } from "@/components/ui/PageShell";
import { BrowserApprovalPanel } from "@/components/browser-approval/BrowserApprovalPanel";

export const metadata = {
  title: "Browser Approvals - Admin",
  description: "Browser action approval workflow",
};

export default function BrowserApprovalsPage() {
  return (
    <PageShell
      title="브라우저 승인"
      description="Browser action approval workflow"
      chatDomain="ops"
    >
      <BrowserApprovalPanel />
    </PageShell>
  );
}
