'use client';

interface ApprovalChecklistProps {
  checklist: string[];
}

export function ApprovalChecklist({ checklist }: ApprovalChecklistProps) {
  return (
    <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
      <h3 className="font-semibold text-sm text-yellow-900 mb-2">⚠️ 주의사항</h3>
      <ul className="space-y-1 text-xs text-yellow-900">
        {checklist.map((item, idx) => (
          <li key={idx} className="flex items-start gap-2">
            <span className="mt-0.5">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
