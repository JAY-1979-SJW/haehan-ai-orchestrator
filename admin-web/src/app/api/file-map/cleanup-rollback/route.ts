/**파일 정리 롤백 매니페스트 조회 API.*/

import { NextRequest, NextResponse } from 'next/server';
import { loadManifest, isValidUuid, RollbackManifest } from '@/server/file-map/rollbackStore';

interface RollbackResponse {
  ok: boolean;
  manifest?: RollbackManifest;
  error?: string;
}

export async function GET(req: NextRequest): Promise<NextResponse<RollbackResponse>> {
  try {
    const runId = req.nextUrl.searchParams.get('run_id');

    if (!runId) {
      return NextResponse.json(
        { ok: false, error: '실행 ID가 필요합니다' },
        { status: 400 }
      );
    }

    if (!isValidUuid(runId)) {
      return NextResponse.json(
        { ok: false, error: '유효하지 않은 실행 ID 형식입니다' },
        { status: 400 }
      );
    }

    const manifest = loadManifest(runId);

    if (!manifest) {
      return NextResponse.json(
        { ok: false, error: '롤백 매니페스트를 찾을 수 없습니다' },
        { status: 404 }
      );
    }

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
