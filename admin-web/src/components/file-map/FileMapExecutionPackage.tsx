'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';

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

interface PackageData {
  ok: boolean;
  package_id: string;
  package_only: boolean;
  execution_enabled: boolean;
  approval_required_for_execution: boolean;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  selected_groups: string[];
  excluded_groups: string[];
  summary?: {
    total_candidate_items: number;
    included_items: number;
    excluded_items: number;
    estimated_total_size_bytes: number;
  };
  operations: ExecutionOperation[];
  preflight_checks: Array<{ message: string; status?: 'pass' | 'warning' | 'fail' }>;
  blocked_operations: Array<{ reason: string; count: number; group_id?: string }>;
  error?: string;
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return '0B';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)}GB`;
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

export function FileMapExecutionPackage() {
  const [data, setData] = useState<PackageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<any>(null);
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [creatingPackage, setCreatingPackage] = useState(false);

  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
  }, []);

  useEffect(() => {
    const fetchPackage = async () => {
      if (!settings) return;

      try {
        setLoading(true);
        const response = await fetch(
          `/api/file-map/cleanup-execution-package?mode=${settings.maskingMode}`
        );
        const json: PackageData = await response.json();

        if (json.ok) {
          setData(json);
          const defaultSelected = new Set(json.selected_groups);
          setSelectedGroups(defaultSelected);
        } else {
          setError(json.error || 'Unknown error');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load execution package');
      } finally {
        setLoading(false);
      }
    };

    fetchPackage();
  }, [settings]);

  const handleCreatePackage = async () => {
    if (!settings || !data) return;

    try {
      setCreatingPackage(true);
      const response = await fetch(
        `/api/file-map/cleanup-execution-package?mode=${settings.maskingMode}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            selected_group_ids: Array.from(selectedGroups),
            confirm_exclusions: true,
            package_only: true,
          }),
        }
      );
      const json: PackageData = await response.json();

      if (json.ok) {
        setData(json);
      } else {
        setError(json.error || 'Failed to create package');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create package');
    } finally {
      setCreatingPackage(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-gray-600">
        <div className="animate-spin inline-block w-5 h-5 border-2 border-gray-300 border-t-blue-500 rounded-full mr-2" />
        실행 패키지를 로드 중입니다...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
        <p className="font-semibold mb-1">⚠️ 실행 패키지 로드 실패</p>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
        <p>실행 패키지 데이터가 없습니다.</p>
      </div>
    );
  }

  const summary = data.summary || {
    total_candidate_items: 0,
    included_items: 0,
    excluded_items: 0,
    estimated_total_size_bytes: 0,
  };

  const selectableGroupsByIds = ['documents', 'spreadsheets', 'cad', 'images', 'archive'];

  return (
    <div className="execution-package space-y-4">
      {/* 안내 문구 */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900">
        <p className="font-semibold mb-2">📦 실행 패키지 생성</p>
        <p className="mb-2">
          이 화면은 <strong>실행 패키지 생성 단계</strong>입니다. 아직 실제 파일 이동, 삭제, 이름변경, 폴더 생성은 수행하지 않습니다.
        </p>
        <p>민감문서, 중복 검토 후보, 고위험 파일은 기본 실행 패키지에서 제외됩니다.</p>
      </div>

      {/* 패키지 정보 */}
      <div className="p-4 bg-white border rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-medium text-sm">패키지 ID</div>
            <code className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">
              {data.package_id}
            </code>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 bg-purple-100 text-purple-800 text-sm rounded-full font-medium">
              📦 패키지 준비
            </span>
            <span className="px-3 py-1 bg-gray-100 text-gray-800 text-sm rounded-full font-medium">
              🔒 실행 비활성화
            </span>
          </div>
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-blue-600">{summary.total_candidate_items}</div>
          <div className="text-xs text-gray-600 mt-1">총 대상 파일</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-green-600">{summary.included_items}</div>
          <div className="text-xs text-gray-600 mt-1">포함 예정</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-orange-600">{summary.excluded_items}</div>
          <div className="text-xs text-gray-600 mt-1">제외됨</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-lg font-bold text-purple-600">{formatFileSize(summary.estimated_total_size_bytes)}</div>
          <div className="text-xs text-gray-600 mt-1">예상 크기</div>
        </div>
      </div>

      {/* 선택 가능 그룹 */}
      <div className="space-y-3">
        <h3 className="font-semibold text-sm text-gray-900">선택 가능 그룹</h3>
        <div className="space-y-2">
          {selectableGroupsByIds.map((groupId) => (
            <label key={groupId} className="flex items-center p-3 bg-white border rounded-lg cursor-pointer hover:bg-gray-50">
              <input
                type="checkbox"
                checked={selectedGroups.has(groupId)}
                onChange={(e) => {
                  const newSelected = new Set(selectedGroups);
                  if (e.target.checked) {
                    newSelected.add(groupId);
                  } else {
                    newSelected.delete(groupId);
                  }
                  setSelectedGroups(newSelected);
                }}
                className="w-4 h-4 rounded border-gray-300"
              />
              <div className="ml-3 flex-1">
                <div className="font-medium text-sm">{getGroupLabel(groupId)}</div>
                <div className="text-xs text-gray-600 mt-1">
                  {data.operations.filter((op) => op.category === groupId).length}개 파일
                </div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* 예상 작업 목록 */}
      {data.operations.length > 0 && (
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
                {data.operations.slice(0, 10).map((op) => (
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
          {data.operations.length > 10 && (
            <p className="text-xs text-gray-600 mt-2">외 {data.operations.length - 10}개 작업...</p>
          )}
        </div>
      )}

      {/* 사전 점검 체크리스트 */}
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <h3 className="font-semibold text-sm text-yellow-900 mb-2">⚠️ 실행 전 사전 점검</h3>
        <ul className="space-y-2 text-xs text-yellow-900">
          {data.preflight_checks.map((check, idx) => (
            <li key={idx} className="flex items-start gap-2">
              <span className="mt-0.5">
                {check.status === 'pass' ? '✓' : check.status === 'warning' ? '⚠️' : '✗'}
              </span>
              <span>{check.message}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* 기본 제외 항목 */}
      {data.blocked_operations.length > 0 && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <h3 className="font-semibold text-sm text-red-900 mb-2">🚫 기본 제외 항목</h3>
          <div className="space-y-2 text-xs text-red-900">
            {data.blocked_operations.map((blocked, idx) => (
              <div key={idx} className="flex items-center justify-between">
                <span>{blocked.reason}</span>
                <span className="font-medium">{blocked.count}개</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 롤백 참고정보 */}
      <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
        <h3 className="font-semibold text-sm mb-2">💾 롤백 참고정보</h3>
        <ul className="list-disc list-inside space-y-1 text-xs text-gray-700">
          <li>모든 파일 이동 작업은 기록되며, 원본 경로 정보가 보존됩니다</li>
          <li>실행 후 문제가 발생한 경우 원본 경로로 복원 가능합니다</li>
          <li>이동된 파일의 메타데이터(수정 시간 등)는 유지됩니다</li>
          <li>중복/삭제 작업은 포함되지 않습니다</li>
        </ul>
      </div>

      {/* 보안 정책 안내 */}
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-900">
        <p className="font-semibold mb-2">🔐 보안 및 정책</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>민감문서, 중복 검토 후보, 고위험 파일은 기본 실행 패키지에서 제외됩니다</li>
          <li>이 화면은 패키지 생성 단계만 제공합니다</li>
          <li>삭제 작업은 패키지에 포함되지 않습니다</li>
          <li>실제 파일 이동은 별도 최종 승인 단계에서만 가능합니다</li>
        </ul>
      </div>

      {/* 패키지 생성 버튼 */}
      <div className="flex gap-2">
        <button
          onClick={handleCreatePackage}
          disabled={selectedGroups.size === 0 || creatingPackage}
          className={`flex-1 px-4 py-2 rounded font-medium transition-colors ${
            selectedGroups.size === 0 || creatingPackage
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : 'bg-blue-500 hover:bg-blue-600 text-white cursor-pointer'
          }`}
        >
          {creatingPackage ? '생성 중...' : '패키지 생성'}
        </button>
      </div>
    </div>
  );
}
