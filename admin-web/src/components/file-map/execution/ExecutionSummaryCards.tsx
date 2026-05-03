'use client';

function formatFileSize(bytes?: number): string {
  if (!bytes) return '0B';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)}GB`;
}

interface ExecutionSummaryCardsProps {
  summary?: {
    total_candidate_items: number;
    included_items: number;
    excluded_items: number;
    estimated_total_size_bytes: number;
  };
}

export function ExecutionSummaryCards({ summary }: ExecutionSummaryCardsProps) {
  const data = summary || {
    total_candidate_items: 0,
    included_items: 0,
    excluded_items: 0,
    estimated_total_size_bytes: 0,
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-blue-600">{data.total_candidate_items}</div>
        <div className="text-xs text-gray-600 mt-1">총 대상 파일</div>
      </div>
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-green-600">{data.included_items}</div>
        <div className="text-xs text-gray-600 mt-1">포함 예정</div>
      </div>
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-2xl font-bold text-orange-600">{data.excluded_items}</div>
        <div className="text-xs text-gray-600 mt-1">제외됨</div>
      </div>
      <div className="p-3 bg-white border rounded-lg">
        <div className="text-lg font-bold text-purple-600">{formatFileSize(data.estimated_total_size_bytes)}</div>
        <div className="text-xs text-gray-600 mt-1">예상 크기</div>
      </div>
    </div>
  );
}
