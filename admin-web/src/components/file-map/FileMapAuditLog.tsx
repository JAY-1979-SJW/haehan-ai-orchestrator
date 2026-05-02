'use client';

import { useState, useEffect } from 'react';
import { loadAuditRecords, formatAuditRecord, calculateAuditStats, type AuditRecord } from '@/lib/fileMapAudit';

interface FileMapAuditLogProps {
  runId?: string;
}

export function FileMapAuditLog({ runId }: FileMapAuditLogProps) {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadLogs = async () => {
      setLoading(true);
      setError(null);

      try {
        const logs = await loadAuditRecords(runId);
        setRecords(logs);
      } catch (err) {
        setError(err instanceof Error ? err.message : '로드 실패');
      } finally {
        setLoading(false);
      }
    };

    loadLogs();
  }, [runId]);

  const stats = calculateAuditStats(records);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'bg-green-50 text-green-800';
      case 'failed':
        return 'bg-red-50 text-red-800';
      case 'conflict':
        return 'bg-yellow-50 text-yellow-800';
      case 'skipped':
        return 'bg-gray-50 text-gray-800';
      default:
        return 'bg-gray-50';
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'low':
        return 'bg-blue-100 text-blue-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      case 'high':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100';
    }
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-gray-600">
        <div className="animate-spin inline-block w-5 h-5 border-2 border-gray-300 border-t-blue-500 rounded-full mr-2" />
        감사로그를 로드 중입니다...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
        {error}
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="p-6 text-center text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
        감사로그가 없습니다.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
          <div className="text-lg font-bold text-blue-600">{stats.total}</div>
          <div className="text-xs text-blue-800">총 항목</div>
        </div>
        <div className="p-3 bg-green-50 rounded-lg border border-green-200">
          <div className="text-lg font-bold text-green-600">{stats.success}</div>
          <div className="text-xs text-green-800">성공</div>
        </div>
        <div className="p-3 bg-red-50 rounded-lg border border-red-200">
          <div className="text-lg font-bold text-red-600">{stats.failed}</div>
          <div className="text-xs text-red-800">실패</div>
        </div>
        <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
          <div className="text-lg font-bold text-yellow-600">{stats.conflict}</div>
          <div className="text-xs text-yellow-800">충돌</div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-4 py-2 text-left font-medium text-gray-700">시간</th>
              <th className="px-4 py-2 text-left font-medium text-gray-700">상태</th>
              <th className="px-4 py-2 text-left font-medium text-gray-700">카테고리</th>
              <th className="px-4 py-2 text-left font-medium text-gray-700">작업</th>
              <th className="px-4 py-2 text-left font-medium text-gray-700">위험도</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {records.map((record) => {
              const formatted = formatAuditRecord(record);
              return (
                <tr
                  key={`${record.runId}-${record.operationId}`}
                  className={getStatusColor(record.status)}
                >
                  <td className="px-4 py-2 text-xs font-mono">{formatted.timestamp}</td>
                  <td className="px-4 py-2 text-xs font-medium">{formatted.status}</td>
                  <td className="px-4 py-2 text-xs">{formatted.category}</td>
                  <td className="px-4 py-2 text-xs">{formatted.operation}</td>
                  <td>
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${getRiskColor(record.risk)}`}
                    >
                      {formatted.risk}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {records.length > 100 && (
        <p className="text-xs text-center text-gray-500">
          최근 100개 항목만 표시됩니다. ({records.length - 100}개 추가)
        </p>
      )}
    </div>
  );
}
