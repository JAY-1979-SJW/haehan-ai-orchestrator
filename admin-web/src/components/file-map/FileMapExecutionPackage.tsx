'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';
import { ExecutionHeader } from './execution/ExecutionHeader';
import { ExecutionSummaryCards } from './execution/ExecutionSummaryCards';
import { ExecutionGroupSelector } from './execution/ExecutionGroupSelector';
import { ExecutionOperationsList } from './execution/ExecutionOperationsList';
import { ExecutionPreflight } from './execution/ExecutionPreflight';
import { ExecutionBlockedOperations } from './execution/ExecutionBlockedOperations';
import { ExecutionRollbackInfo } from './execution/ExecutionRollbackInfo';
import { ExecutionSecurityPolicy } from './execution/ExecutionSecurityPolicy';

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

export function FileMapExecutionPackage() {
  const [data, setData] = useState<PackageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<any>(null);
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
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

  const handleToggleGroup = (groupId: string, checked: boolean) => {
    const newSelected = new Set(selectedGroups);
    if (checked) {
      newSelected.add(groupId);
    } else {
      newSelected.delete(groupId);
    }
    setSelectedGroups(newSelected);
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

  return (
    <div className="execution-package space-y-4">
      <ExecutionHeader packageId={data.package_id} />

      <ExecutionSummaryCards summary={data.summary} />

      <ExecutionGroupSelector
        operations={data.operations}
        selectedGroups={selectedGroups}
        onToggleGroup={handleToggleGroup}
      />

      <ExecutionOperationsList operations={data.operations} />

      <ExecutionPreflight checks={data.preflight_checks} />

      <ExecutionBlockedOperations blockedOperations={data.blocked_operations} />

      <ExecutionRollbackInfo />

      <ExecutionSecurityPolicy />

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
