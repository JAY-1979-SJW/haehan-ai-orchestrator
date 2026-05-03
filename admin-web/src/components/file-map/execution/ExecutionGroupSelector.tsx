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

function getGroupLabel(groupId: string): string {
  const labels: Record<string, string> = {
    documents: '업무문서',
    spreadsheets: '엑셀/정산',
    cad: 'CAD/도면',
    images: '이미지/스캔',
    archive: '설치파일 보관',
    sensitive: '민감문서',
    duplicates: '중복검토',
    hold: '분류보류',
    huge_files: '대용량 파일',
  };
  return labels[groupId] || groupId;
}

interface ExecutionGroupSelectorProps {
  operations: ExecutionOperation[];
  selectedGroups: Set<string>;
  onToggleGroup: (groupId: string, checked: boolean) => void;
}

export function ExecutionGroupSelector({
  operations,
  selectedGroups,
  onToggleGroup,
}: ExecutionGroupSelectorProps) {
  const selectableGroupsByIds = ['documents', 'spreadsheets', 'cad', 'images', 'archive'];

  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-sm text-gray-900">선택 가능 그룹</h3>
      <div className="space-y-2">
        {selectableGroupsByIds.map((groupId) => (
          <label key={groupId} className="flex items-center p-3 bg-white border rounded-lg cursor-pointer hover:bg-gray-50">
            <input
              type="checkbox"
              checked={selectedGroups.has(groupId)}
              onChange={(e) => onToggleGroup(groupId, e.target.checked)}
              className="w-4 h-4 rounded border-gray-300"
            />
            <div className="ml-3 flex-1">
              <div className="font-medium text-sm">{getGroupLabel(groupId)}</div>
              <div className="text-xs text-gray-600 mt-1">
                {operations.filter((op) => op.category === groupId).length}개 파일
              </div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}
