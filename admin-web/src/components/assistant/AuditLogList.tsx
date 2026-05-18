/** AuditLogList — redacted 감사 로그 목록 (token/cookie 원문 표시 금지) */
import type { AuditLogEntry } from "@/types/assistant";

const LEVEL_COLOR: Record<string, string> = {
  INFO:  "text-[#059669]",
  WARN:  "text-[#D97706]",
  ERROR: "text-[#B91C1C]",
};

export function AuditLogList({ logs }: { logs: AuditLogEntry[] }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-[#374151]">감사 로그</span>
        <span className="text-[10px] bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] px-1.5 py-0.5 rounded">
          secret/token/cookie 원문 표시 금지
        </span>
      </div>
      <div className="space-y-1">
        {logs.map((log) => (
          <div key={log.id} className="flex items-start gap-2 text-xs p-2 rounded bg-[#F9FAFB] border border-[#F3F4F6]">
            <span className={`font-mono font-bold w-10 ${LEVEL_COLOR[log.level] ?? ""}`}>
              {log.level}
            </span>
            <span className="font-mono text-[#6B7280] w-40 shrink-0">{log.timestamp.slice(0, 19)}</span>
            <span className="text-[#374151]">{log.message}</span>
            {log.redacted && (
              <span className="ml-auto text-[#9CA3AF] text-[10px] shrink-0">[redacted]</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
