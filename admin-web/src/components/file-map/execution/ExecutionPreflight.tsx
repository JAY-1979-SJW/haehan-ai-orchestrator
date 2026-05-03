'use client';

interface ExecutionPreflightProps {
  checks: Array<{ message: string; status?: 'pass' | 'warning' | 'fail' }>;
}

export function ExecutionPreflight({ checks }: ExecutionPreflightProps) {
  return (
    <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
      <h3 className="font-semibold text-sm text-yellow-900 mb-2">⚠️ 실행 전 사전 점검</h3>
      <ul className="space-y-2 text-xs text-yellow-900">
        {checks.map((check, idx) => (
          <li key={idx} className="flex items-start gap-2">
            <span className="mt-0.5">
              {check.status === 'pass' ? '✓' : check.status === 'warning' ? '⚠️' : '✗'}
            </span>
            <span>{check.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
