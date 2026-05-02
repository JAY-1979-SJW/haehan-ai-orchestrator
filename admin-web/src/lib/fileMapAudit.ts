/**파일 정리 감사로그: 조회 및 표시.*/

export interface AuditRecord {
  runId: string;
  timestamp: string;
  packageId: string;
  operationId: string;
  operationType: string;
  status: 'success' | 'failed' | 'skipped' | 'conflict';
  sourcePath: string;
  targetPath: string;
  category: string;
  risk: 'low' | 'medium' | 'high';
  error?: string;
}

export interface AuditLogResponse {
  ok: boolean;
  records?: AuditRecord[];
  error?: string;
}

/**
 * 감사로그 조회.
 *
 * @param runId 특정 실행 ID 조회 (undefined = 전체)
 * @returns 감사로그 리스트
 */
export async function loadAuditRecords(runId?: string): Promise<AuditRecord[]> {
  const params = new URLSearchParams();
  if (runId) {
    params.append('run_id', runId);
  }

  try {
    const response = await fetch(`/api/file-map/cleanup-audit?${params.toString()}`);
    const result: AuditLogResponse = await response.json();

    if (!result.ok) {
      console.error('Failed to load audit records:', result.error);
      return [];
    }

    return result.records || [];
  } catch (err) {
    console.error('Error loading audit records:', err);
    return [];
  }
}

/**
 * 감사로그 레코드를 테이블용 행으로 변환.
 */
export function formatAuditRecord(record: AuditRecord): {
  timestamp: string;
  status: string;
  category: string;
  operation: string;
  risk: string;
} {
  const statusLabel = {
    success: '✓ 성공',
    failed: '✗ 실패',
    skipped: '- 스킵',
    conflict: '⚠ 충돌',
  }[record.status] || record.status;

  const riskLabel = {
    low: '낮음',
    medium: '중간',
    high: '높음',
  }[record.risk] || record.risk;

  return {
    timestamp: new Date(record.timestamp).toLocaleString('ko-KR'),
    status: statusLabel,
    category: record.category || '-',
    operation: record.operationType,
    risk: riskLabel,
  };
}

/**
 * 감사로그 통계.
 */
export function calculateAuditStats(records: AuditRecord[]) {
  return {
    total: records.length,
    success: records.filter((r) => r.status === 'success').length,
    failed: records.filter((r) => r.status === 'failed').length,
    skipped: records.filter((r) => r.status === 'skipped').length,
    conflict: records.filter((r) => r.status === 'conflict').length,
  };
}
