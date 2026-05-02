/**파일 정리 롤백 매니페스트 조회 API.*/

import { NextRequest, NextResponse } from 'next/server';

interface RollbackEntry {
  operation_id: string;
  original_path: string;
  moved_to_path: string;
  rollback_possible: boolean;
  timestamp: string;
}

interface RollbackManifest {
  run_id: string;
  package_id: string;
  generated_at: string;
  total_moved: number;
  entries: RollbackEntry[];
  notes: string;
}

interface RollbackResponse {
  ok: boolean;
  manifest?: RollbackManifest;
  error?: string;
}

/**
 * GET /api/file-map/cleanup-rollback?run_id=<run_id>
 *
 * 롤백 매니페스트 조회 (자동 롤백 실행 금지).
 */
export async function GET(req: NextRequest): Promise<NextResponse<RollbackResponse>> {
  try {
    const runId = req.nextUrl.searchParams.get('run_id');

    if (!runId) {
      return NextResponse.json(
        { ok: false, error: '실행 ID가 필요합니다' },
        { status: 400 }
      );
    }

    // TODO: Python cleanup_rollback 모듈에서 매니페스트 로드
    // load_manifest(run_id) 호출

    // 모의 응답
    const manifest: RollbackManifest = {
      run_id: runId,
      package_id: '',
      generated_at: new Date().toISOString(),
      total_moved: 0,
      entries: [],
      notes: '롤백은 수동으로만 수행 가능합니다.',
    };

    return NextResponse.json({
      ok: true,
      manifest,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json(
      { ok: false, error: `롤백 매니페스트 조회 실패: ${message}` },
      { status: 500 }
    );
  }
}
