/**cleanup-audit 감사로그 조회 (읽기 전용).*/

import fs from 'fs';
import path from 'path';
import os from 'os';

export interface AuditRecord {
  run_id: string;
  timestamp: string;
  package_id: string;
  operation_id: string;
  operation_type: string;
  status: string;
  source_path: string;
  target_path: string;
  category: string;
  risk: string;
  error?: string;
}

/**
 * 감사로그 파일 경로 계산.
 *
 * @returns cleanup_audit.jsonl 파일 경로
 */
export function getAuditFilePath(): string {
  const home = os.homedir();
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory', 'cleanup_audit.jsonl');
}

/**
 * 감사로그 records 로드.
 *
 * @param runId 특정 실행 ID 필터 (undefined/null = 모두)
 * @returns 감사로그 배열 (파일 없으면 빈 배열)
 */
export function loadAuditRecords(runId?: string | null): AuditRecord[] {
  const auditFilePath = getAuditFilePath();

  if (!fs.existsSync(auditFilePath)) {
    return [];
  }

  const records: AuditRecord[] = [];
  try {
    const content = fs.readFileSync(auditFilePath, 'utf-8');
    const lines = content.split('\n').filter((line) => line.trim());

    for (const line of lines) {
      try {
        const record = JSON.parse(line) as AuditRecord;
        if (runId === null || runId === undefined || record.run_id === runId) {
          records.push(record);
        }
      } catch {
        // 잘못된 라인 무시
      }
    }
  } catch (error) {
    console.error('Failed to load audit records:', error);
  }

  return records;
}
