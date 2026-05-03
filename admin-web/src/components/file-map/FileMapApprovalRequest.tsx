'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';
import { ApprovalHeader } from './approval/ApprovalHeader';
import { ApprovalSummaryCards } from './approval/ApprovalSummaryCards';
import { ApprovalGroupsList } from './approval/ApprovalGroupsList';
import { ExcludedGroupsList } from './approval/ExcludedGroupsList';
import { ApprovalChecklist } from './approval/ApprovalChecklist';
import { ApprovalPolicyNotice } from './approval/ApprovalPolicyNotice';

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

  const selectedItemCount = data.approval_groups
    .filter((g) => selectedGroups.has(g.group_id))
    .reduce((sum, g) => sum + g.item_count, 0);

  return (
    <div className="approval-request space-y-4">
      <ApprovalHeader requestId={data.approval_request_id} />

      <ApprovalSummaryCards
        summary={data.summary}
        selectedItemCount={selectedItemCount}
      />

      <ApprovalGroupsList
        groups={data.approval_groups}
        selectedGroups={selectedGroups}
        expandedGroup={expandedGroup}
        onToggleGroup={toggleGroupSelection}
        onToggleExpanded={(id) => setExpandedGroup(expandedGroup === id ? null : id)}
      />

      <ExcludedGroupsList
        groups={data.excluded_groups}
        expandedGroup={expandedGroup}
        onToggleExpanded={(id) => setExpandedGroup(expandedGroup === id ? null : id)}
      />

      <ApprovalChecklist checklist={data.checklist} />

      <ApprovalPolicyNotice />
    </div>
  );
}
