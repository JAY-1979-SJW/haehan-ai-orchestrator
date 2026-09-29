import { PageShell } from "@/components/ui/PageShell";
import { GoogleToolsPanel } from "./components/GoogleToolsPanel";

/**
 * 구글 허브 — Calendar/Drive/Docs/Sheets/YouTube/GCP.
 * 2026-09-29 구조 재설계(docs/specs/2026-09-29_app_purpose_and_structure_redesign.md):
 * 예전 NAV_GROUPS_ALL에 있던 "구글 허브"(/google)를 실제로 되살림.
 */
export default function GooglePage() {
  return (
    <PageShell title="구글 허브" description="Calendar · Drive · Docs · Sheets · YouTube · GCP" chatDomain="google">
      <div className="space-y-8">
        <GoogleToolsPanel />
      </div>
    </PageShell>
  );
}
