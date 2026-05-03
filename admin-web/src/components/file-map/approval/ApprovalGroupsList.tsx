'use client';

interface ApprovalItem {
  current_path: string;
  suggested_path: string;
  category: string;
  risk: 'low' | 'medium' | 'high';
  file_size_bytes?: number;
  modified_time?: string;
}

interface ApprovalGroup {
  group_id: string;
  label: string;
  default_selected: boolean;
  risk: 'low' | 'medium' | 'high';
  item_count: number;
  items: ApprovalItem[];
}

function getRiskBadgeColor(risk: 'low' | 'medium' | 'high'): string {
  switch (risk) {
    case 'high':
      return 'bg-red-100 text-red-800';
    case 'medium':
      return 'bg-yellow-100 text-yellow-800';
    case 'low':
      return 'bg-green-100 text-green-800';
  }
}

function getRiskLabel(risk: 'low' | 'medium' | 'high'): string {
  switch (risk) {
    case 'high':
      return '위험(민감)';
    case 'medium':
      return '검토필요(중복)';
    case 'low':
      return '안전';
  }
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

interface ApprovalGroupsListProps {
  groups: ApprovalGroup[];
  selectedGroups: Set<string>;
  expandedGroup: string | null;
  onToggleGroup: (groupId: string) => void;
  onToggleExpanded: (groupId: string) => void;
}

export function ApprovalGroupsList({
  groups,
  selectedGroups,
  expandedGroup,
  onToggleGroup,
  onToggleExpanded,
}: ApprovalGroupsListProps) {
  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-sm text-gray-900">✓ 기본 선택 가능 그룹</h3>
      {groups.length === 0 ? (
        <p className="text-xs text-gray-600 p-3 bg-gray-50 rounded">선택 가능한 그룹이 없습니다.</p>
      ) : (
        groups.map((group) => (
          <div key={group.group_id} className="border rounded-lg overflow-hidden">
            <div className="p-3 bg-gray-50 hover:bg-gray-100 transition-colors">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedGroups.has(group.group_id)}
                  onChange={() => onToggleGroup(group.group_id)}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <div className="flex-1">
                  <div className="font-medium text-sm">{group.label}</div>
                  <div className="text-xs text-gray-600 mt-1">
                    {group.item_count}개 파일 · 위험도{' '}
                    <span className={`px-2 py-1 rounded text-xs font-medium ${getRiskBadgeColor(group.risk)}`}>
                      {getRiskLabel(group.risk)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    onToggleExpanded(group.group_id);
                  }}
                  className="px-2 py-1 text-xs text-gray-600 hover:text-gray-900"
                >
                  {expandedGroup === group.group_id ? '▼' : '▶'}
                </button>
              </label>
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
