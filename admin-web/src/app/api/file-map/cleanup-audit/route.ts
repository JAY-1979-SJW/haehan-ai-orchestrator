/**파일 정리 감사로그 조회 API.*/

import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import os from 'os';

interface AuditRecord {
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

interface AuditResponse {
  ok: boolean;
  records?: AuditRecord[];
  error?: string;
}

function getAuditFilePath(): string {
  const home = os.homedir();
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory', 'cleanup_audit.jsonl');
}

function loadAuditRecords(runId?: string | null): AuditRecord[] {
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

/**
 * GET /api/file-map/cleanup-audit?run_id=<run_id>
 *
 * 감사로그 조회 (기본 마스킹 적용).
 */
export async function GET(req: NextRequest): Promise<NextResponse<AuditResponse>> {
  try {
    const runId = req.nextUrl.searchParams.get('run_id');
    const records = loadAuditRecords(runId);

    return NextResponse.json({
      ok: true,
      records,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json(
      { ok: false, error: `감사로그 조회 실패: ${message}` },
      { status: 500 }
    );
  }
}
