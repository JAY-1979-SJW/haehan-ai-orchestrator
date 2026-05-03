'use client';

interface ExecutionOperation {
  operation_id: string;
  operation_type: 'move_preview' | 'archive_preview';
  current_path: string;
  suggested_path: string;
  category: string;
  risk: 'low' | 'medium' | 'high';
  masked: boolean;
  requires_final_approval: boolean;
  rollback_hint: { from: string; to: string };
  file_size_bytes?: number;
  modified_time?: string;
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return '0B';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)}GB`;
}

interface ExecutionOperationsListProps {
  operations: ExecutionOperation[];
}

export function ExecutionOperationsList({ operations }: ExecutionOperationsListProps) {
  if (!operations || operations.length === 0) {
    return null;
  }

  return (
    <div className="p-4 bg-white border rounded-lg">
      <h3 className="font-semibold text-sm mb-3">예상 작업 목록 (상위 10개)</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b">
              <th className="text-left px-2 py-1">현재 경로</th>
              <th className="text-left px-2 py-1">제안 경로</th>
              <th className="text-right px-2 py-1">크기</th>
            </tr>
          </thead>
          <tbody>
            {operations.slice(0, 10).map((op) => (
              <tr key={op.operation_id} className="border-b hover:bg-gray-50">
                <td className="px-2 py-1 font-mono text-gray-700 truncate max-w-xs">
                  ...{op.current_path.slice(-30)}
                </td>
                <td className="px-2 py-1 text-blue-600 truncate max-w-xs">
                  {op.suggested_path}
                </td>
                <td className="px-2 py-1 text-right">{formatFileSize(op.file_size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {operations.length > 10 && (
        <p className="text-xs text-gray-600 mt-2">외 {operations.length - 10}개 작업...</p>
      )}
    </div>
  );
}
