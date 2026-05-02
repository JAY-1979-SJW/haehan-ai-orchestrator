'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';

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

interface ExcludedGroup {
  group_id: string;
  label: string;
  reason: string;
  item_count: number;
  items: ApprovalItem[];
}

interface ApprovalData {
  ok: boolean;
  approval_request_id: string;
  approval_required: boolean;
  execution_enabled: boolean;
  request_only: boolean;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  summary?: {
    total_preview_items: number;
    auto_selectable_items: number;
    excluded_sensitive_items: number;
    excluded_high_risk_items: number;
    duplicate_review_items: number;
  };
  approval_groups: ApprovalGroup[];
  excluded_groups: ExcludedGroup[];
  checklist: string[];
  error?: string;
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

export function FileMapApprovalRequest() {
  const [data, setData] = useState<ApprovalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<any>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());

  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
  }, []);

  useEffect(() => {
    const fetchApproval = async () => {
      if (!settings) return;

      try {
        setLoading(true);
        const response = await fetch(
          `/api/file-map/cleanup-approval-request?mode=${settings.maskingMode}`
        );
        const json: ApprovalData = await response.json();

        if (json.ok) {
          setData(json);
          // 기본 선택 그룹 초기화
          const defaultSelected = new Set<string>();
          json.approval_groups.forEach((group) => {
            if (group.default_selected) {
              defaultSelected.add(group.group_id);
            }
          });
          setSelectedGroups(defaultSelected);
        } else {
          setError(json.error || 'Unknown error');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load approval request');
      } finally {
        setLoading(false);
      }
    };

    fetchApproval();
  }, [settings]);

  const toggleGroupSelection = (groupId: string) => {
    const newSelected = new Set(selectedGroups);
    if (newSelected.has(groupId)) {
      newSelected.delete(groupId);
    } else {
      newSelected.add(groupId);
    }
    setSelectedGroups(newSelected);
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-gray-600">
        <div className="animate-spin inline-block w-5 h-5 border-2 border-gray-300 border-t-blue-500 rounded-full mr-2" />
        승인 요청서를 로드 중입니다...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
        <p className="font-semibold mb-1">⚠️ 승인 요청서 로드 실패</p>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
        <p>승인 요청서 데이터가 없습니다.</p>
      </div>
    );
  }

  const summary = data.summary || {
    total_preview_items: 0,
    auto_selectable_items: 0,
    excluded_sensitive_items: 0,
    excluded_high_risk_items: 0,
    duplicate_review_items: 0,
  };

  const selectedItemCount = data.approval_groups
    .filter((g) => selectedGroups.has(g.group_id))
    .reduce((sum, g) => sum + g.item_count, 0);

  return (
    <div className="approval-request space-y-4">
      {/* 안내 문구 */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900">
        <p className="font-semibold mb-2">📋 실행 승인 요청서</p>
        <p className="mb-2">
          이 화면은 <strong>실행 승인 요청서</strong>입니다. 실제 파일은 아직 변경되지 않았습니다.
        </p>
        <p>민감문서와 중복 검토 후보는 기본 실행 대상에서 제외됩니다.</p>
      </div>

      {/* 요청 ID 및 상태 */}
      <div className="p-4 bg-white border rounded-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-600">요청 ID</span>
          <code className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">
            {data.approval_request_id}
          </code>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full font-medium">
            📋 요청 검토 중
          </span>
          <span className="px-3 py-1 bg-gray-100 text-gray-800 text-sm rounded-full font-medium">
            🔒 실행 비활성화
          </span>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-blue-600">{summary.total_preview_items}</div>
          <div className="text-xs text-gray-600 mt-1">총 파일</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-green-600">{summary.auto_selectable_items}</div>
          <div className="text-xs text-gray-600 mt-1">선택 가능</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-yellow-600">{summary.duplicate_review_items}</div>
          <div className="text-xs text-gray-600 mt-1">중복 검토</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-red-600">{summary.excluded_sensitive_items}</div>
          <div className="text-xs text-gray-600 mt-1">민감문서</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-blue-600">{selectedItemCount}</div>
          <div className="text-xs text-gray-600 mt-1">선택됨</div>
        </div>
      </div>

      {/* 기본 선택 가능 그룹 */}
      <div className="space-y-3">
        <h3 className="font-semibold text-sm text-gray-900">✓ 기본 선택 가능 그룹</h3>
        {data.approval_groups.length === 0 ? (
          <p className="text-xs text-gray-600 p-3 bg-gray-50 rounded">선택 가능한 그룹이 없습니다.</p>
        ) : (
          data.approval_groups.map((group) => (
            <div key={group.group_id} className="border rounded-lg overflow-hidden">
              <div className="p-3 bg-gray-50 hover:bg-gray-100 transition-colors">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedGroups.has(group.group_id)}
                    onChange={() => toggleGroupSelection(group.group_id)}
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
                      setExpandedGroup(expandedGroup === group.group_id ? null : group.group_id);
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

      {/* 기본 제외 그룹 */}
      <div className="space-y-3">
        <h3 className="font-semibold text-sm text-gray-900">⚠️ 기본 제외 그룹</h3>
        {data.excluded_groups.length === 0 ? (
          <p className="text-xs text-gray-600 p-3 bg-gray-50 rounded">제외 그룹이 없습니다.</p>
        ) : (
          data.excluded_groups.map((group) => (
            <div key={group.group_id} className="border rounded-lg overflow-hidden bg-gray-50">
              <div className="p-3 hover:bg-gray-100 transition-colors cursor-pointer">
                <button
                  onClick={() => setExpandedGroup(expandedGroup === group.group_id ? null : group.group_id)}
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

      {/* 체크리스트 */}
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <h3 className="font-semibold text-sm text-yellow-900 mb-2">⚠️ 주의사항</h3>
        <ul className="space-y-1 text-xs text-yellow-900">
          {data.checklist.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2">
              <span className="mt-0.5">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* 제외 정책 안내 */}
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-900">
        <p className="font-semibold mb-2">🔐 보안 정책</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>민감문서는 기본 제외되며, 수동으로만 처리 가능</li>
          <li>중복 파일은 자동 삭제하지 않으며, 수동 확인 필요</li>
          <li>이 화면은 요청서만 표시합니다</li>
          <li>실제 파일 이동은 다음 단계에서 별도 승인 필요</li>
        </ul>
      </div>
    </div>
  );
}
