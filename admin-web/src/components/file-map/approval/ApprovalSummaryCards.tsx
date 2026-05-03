'use client';

interface ApprovalSummaryCardsProps {
  summary?: {
    total_preview_items: number;
    auto_selectable_items: number;
    excluded_sensitive_items: number;
    excluded_high_risk_items: number;
    duplicate_review_items: number;
  };
  selectedItemCount: number;
}

export function ApprovalSummaryCards({
  summary,
  selectedItemCount,
}: ApprovalSummaryCardsProps) {
  const data = summary || {
    total_preview_items: 0,
    auto_selectable_items: 0,
    excluded_sensitive_items: 0,
    excluded_high_risk_items: 0,
    duplicate_review_items: 0,
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-blue-600">{data.total_preview_items}</div>
        <div className="text-xs text-gray-600 mt-1">총 파일</div>
      </div>
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-green-600">{data.auto_selectable_items}</div>
        <div className="text-xs text-gray-600 mt-1">선택 가능</div>
      </div>
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-yellow-600">{data.duplicate_review_items}</div>
        <div className="text-xs text-gray-600 mt-1">중복 검토</div>
      </div>
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-red-600">{data.excluded_sensitive_items}</div>
        <div className="text-xs text-gray-600 mt-1">민감문서</div>
      </div>
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-blue-600">{selectedItemCount}</div>
        <div className="text-xs text-gray-600 mt-1">선택됨</div>
      </div>
    </div>
  );
}
