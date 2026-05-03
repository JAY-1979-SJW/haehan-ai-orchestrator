'use client';

interface ExecutionBlockedOperationsProps {
  blockedOperations: Array<{ reason: string; count: number; group_id?: string }>;
}

export function ExecutionBlockedOperations({ blockedOperations }: ExecutionBlockedOperationsProps) {
  if (!blockedOperations || blockedOperations.length === 0) {
    return null;
  }

  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
      <h3 className="font-semibold text-sm text-red-900 mb-2">🚫 기본 제외 항목</h3>
      <div className="space-y-2 text-xs text-red-900">
        {blockedOperations.map((blocked, idx) => (
          <div key={idx} className="flex items-center justify-between">
            <span>{blocked.reason}</span>
            <span className="font-medium">{blocked.count}개</span>
          </div>
        ))}
      </div>
    </div>
  );
}
