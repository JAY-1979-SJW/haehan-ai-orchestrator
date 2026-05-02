/**파일 정리 감사로그 조회 API.*/

import { NextRequest, NextResponse } from 'next/server';

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

/**
 * GET /api/file-map/cleanup-audit?run_id=<run_id>
 *
 * 감사로그 조회 (기본 마스킹 적용).
 */
export async function GET(req: NextRequest): Promise<NextResponse<AuditResponse>> {
  try {
    const runId = req.nextUrl.searchParams.get('run_id');

    // TODO: Python cleanup_audit 모듈에서 감사로그 로드
    // load_records(run_id) 호출
    // 마스킹 정책 적용

    // 모의 응답
    const records: AuditRecord[] = [];

    if (runId) {
      // run_id로 필터링된 감사로그
      // records = await loadAuditRecords(runId);
    } else {
      // 모든 감사로그 (최근 100개)
      // records = await loadAllAuditRecords(100);
    }

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
