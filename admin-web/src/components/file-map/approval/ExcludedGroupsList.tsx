'use client';

interface ApprovalItem {
  current_path: string;
  suggested_path: string;
  category: string;
  risk: 'low' | 'medium' | 'high';
  file_size_bytes?: number;
  modified_time?: string;
}

interface ExcludedGroup {
  group_id: string;
  label: string;
  reason: string;
  item_count: number;
  items: ApprovalItem[];
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

interface ExcludedGroupsListProps {
  groups: ExcludedGroup[];
  expandedGroup: string | null;
  onToggleExpanded: (groupId: string | null) => void;
}

export function ExcludedGroupsList({
  groups,
  expandedGroup,
  onToggleExpanded,
}: ExcludedGroupsListProps) {
  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-sm text-gray-900">⚠️ 기본 제외 그룹</h3>
      {groups.length === 0 ? (
        <p className="text-xs text-gray-600 p-3 bg-gray-50 rounded">제외 그룹이 없습니다.</p>
      ) : (
        groups.map((group) => (
          <div key={group.group_id} className="border rounded-lg overflow-hidden bg-gray-50">
            <div className="p-3 hover:bg-gray-100 transition-colors cursor-pointer">
              <button
                onClick={() => onToggleExpanded(expandedGroup === group.group_id ? null : group.group_id)}
                className="w-full text-left flex items-center justify-between"
              >
                <div>
                  <div className="font-medium text-sm">{group.label}</div>
                  <div className="text-xs text-gray-600 mt-1">{group.reason}</div>
                  <div className="text-xs text-gray-600 mt-1">{group.item_count}개 파일</div>
                </div>
                <span className="text-gray-600">{expandedGroup === group.group_id ? '▼' : '▶'}</span>
              </button>
            </div>

            {expandedGroup === group.group_id && (
              <div className="p-3 bg-white border-t overflow-x-auto">
                {group.items.length === 0 ? (
                  <p className="text-xs text-gray-600">파일이 없습니다.</p>
                ) : (
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="bg-gray-50 border-b">
                        <th className="text-left px-2 py-1">파일 경로</th>
                        <th className="text-left px-2 py-1">제안 경로</th>
                        <th className="text-right px-2 py-1">크기</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.items.slice(0, 10).map((item, idx) => (
                        <tr key={idx} className="border-b hover:bg-gray-50">
                          <td className="px-2 py-1 font-mono text-gray-700 truncate max-w-xs">
                            ...{item.current_path.slice(-30)}
                          </td>
                          <td className="px-2 py-1 text-blue-600 truncate max-w-xs">
                            {item.suggested_path}
                          </td>
                          <td className="px-2 py-1 text-right">{formatFileSize(item.file_size_bytes)}</td>
                        </tr>
                      ))}
                      {group.items.length > 10 && (
                        <tr>
                          <td colSpan={3} className="px-2 py-1 text-xs text-gray-600 text-center">
                            외 {group.items.length - 10}개 파일...
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
