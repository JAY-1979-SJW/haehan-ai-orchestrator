/** /assistant — Dashboard */
import { BackendStatusCard } from "@/components/assistant/BackendStatusCard";
import { StorageStatusCard } from "@/components/assistant/StorageStatusCard";
import { DryRunNotice } from "@/components/assistant/DryRunNotice";
import {
  backendStatusMock, storageStatusMock, knownBacklogMock,
} from "@/lib/assistant/mock";

export default function AssistantDashboard() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-[#111827]">대시보드</h1>
      <DryRunNotice enabled={backendStatusMock.dry_run_gate_enabled} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BackendStatusCard status={backendStatusMock} />
        <StorageStatusCard mounts={storageStatusMock} />
      </div>
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <div className="text-sm font-semibold text-[#111827] mb-3">Known Backlog</div>
        <div className="space-y-1.5">
          {knownBacklogMock.map((item) => (
            <div key={item.id} className="flex items-start gap-2 text-xs">
              <span className="font-mono text-[#6B7280] w-10 shrink-0">{item.id}</span>
              <span className="text-[#374151]">{item.title}</span>
              <span className="ml-auto text-[#9CA3AF] shrink-0">{item.app_note}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
