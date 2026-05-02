'use client';

import { useState } from 'react';

interface PreflightItem {
  operation_id: string;
  source_path: string;
  target_path: string;
  category: string;
  status: string;
  reason: string;
}

interface PreflightReport {
  preflight_id: string;
  total: number;
  ok_count: number;
  conflict_count: number;
  skipped_count: number;
  blocked_count: number;
  items: PreflightItem[];
}

interface FileMapPreflightProps {
  onPreflightComplete?: (report: PreflightReport) => void;
  plans?: Array<{
    operation_id: string;
    path: string;
    category: string;
    file_size_bytes: number;
    file_name: string;
  }>;
}

export function FileMapPreflight({ onPreflightComplete, plans = [] }: FileMapPreflightProps) {
  const [report, setReport] = useState<PreflightReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRunPreflight = async () => {
    setLoading(true);
    setError(null);

    try {
      const baseTargetDir = `${process.env.HOME || 'C:\\Users\\default'}\\클린업`;

      const response = await fetch('/api/file-map/cleanup-preflight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plans,
          base_target_dir: baseTargetDir,
          include_sensitive: false,
        }),
      });

      const result = await response.json();

      if (!result.ok) {
        setError(result.error || '사전검사 실패');
        return;
      }

      setReport(result);
      onPreflightComplete?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '오류 발생');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ok':
        return 'bg-green-50 text-green-800';
      case 'conflict':
        return 'bg-yellow-50 text-yellow-800';
      case 'source_missing':
        return 'bg-gray-50 text-gray-800';
      case 'blocked':
        return 'bg-red-50 text-red-800';
      default:
        return 'bg-gray-50 text-gray-800';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'ok':
        return '✓ 준비됨';
      case 'conflict':
        return '⚠ 충돌';
      case 'source_missing':
        return '✗ 누락';
      case 'blocked':
        return '🚫 제외';
      default:
        return status;
    }
  };

  return (
    <div className="space-y-6">
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <p className="text-sm text-blue-800">
          📋 사전검사는 파일 이동 전 충돌, 누락, 제외 항목을 검증합니다.
        </p>
      </div>

      {!report ? (
        <button
          onClick={handleRunPreflight}
          disabled={loading || plans.length === 0}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
        >
          {loading ? '사전검사 중...' : '사전검사 실행'}
        </button>
      ) : null}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
          {error}
        </div>
      )}

      {report && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-green-50 rounded-lg border border-green-200">
              <div className="text-2xl font-bold text-green-600">{report.ok_count}</div>
              <div className="text-sm text-green-800">준비됨</div>
            </div>
            <div className="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
              <div className="text-2xl font-bold text-yellow-600">{report.conflict_count}</div>
              <div className="text-sm text-yellow-800">충돌</div>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
              <div className="text-2xl font-bold text-gray-600">{report.skipped_count}</div>
              <div className="text-sm text-gray-800">누락</div>
            </div>
            <div className="p-4 bg-red-50 rounded-lg border border-red-200">
              <div className="text-2xl font-bold text-red-600">{report.blocked_count}</div>
              <div className="text-sm text-red-800">제외</div>
            </div>
          </div>

          {report.items.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-semibold text-sm">항목별 상태</h4>
              <div className="max-h-64 overflow-y-auto border border-gray-200 rounded-lg">
                <div className="divide-y">
                  {report.items.slice(0, 20).map((item) => (
                    <div
                      key={item.operation_id}
                      className={`p-3 text-sm ${getStatusColor(item.status)}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="font-mono text-xs truncate">{item.source_path}</div>
                          {item.reason && (
                            <div className="text-xs opacity-75 mt-1">{item.reason}</div>
                          )}
                        </div>
                        <span className="flex-shrink-0 whitespace-nowrap">
                          {getStatusLabel(item.status)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {report.items.length > 20 && (
                <p className="text-xs text-gray-500 text-center">
                  외 {report.items.length - 20}개 항목...
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
