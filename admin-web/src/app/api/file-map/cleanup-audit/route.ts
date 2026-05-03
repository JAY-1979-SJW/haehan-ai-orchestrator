/**파일 정리 감사로그 조회 API.*/

import { NextRequest, NextResponse } from 'next/server';
import { loadAuditRecords, AuditRecord } from '@/server/file-map/auditStore';

interface AuditResponse {
  ok: boolean;
  records?: AuditRecord[];
  error?: string;
}

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
