/** StorageStatusCard — 스토리지 상태 카드 */
import type { StorageMount } from "@/types/assistant";

const PERSIST_COLOR: Record<string, string> = {
  PERSISTENT:  "text-[#059669]",
  EPHEMERAL:   "text-[#D97706]",
  DISPOSABLE:  "text-[#6B7280]",
  UNKNOWN:     "text-[#9CA3AF]",
};

export function StorageStatusCard({ mounts }: { mounts: StorageMount[] }) {
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm space-y-2">
      <span className="text-sm font-semibold text-[#111827]">스토리지 상태</span>
      <div className="space-y-2 mt-2">
        {mounts.map((m) => (
          <div key={m.path} className="flex items-start gap-2 text-xs">
            <span className={`font-bold mt-0.5 ${PERSIST_COLOR[m.persistence] ?? PERSIST_COLOR.UNKNOWN}`}>
              {m.persistence}
            </span>
            <div>
              <div className="font-medium text-[#374151]">{m.label}</div>
              <div className="font-mono text-[#6B7280]">{m.path}</div>
              <div className="text-[#9CA3AF]">{m.description}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
