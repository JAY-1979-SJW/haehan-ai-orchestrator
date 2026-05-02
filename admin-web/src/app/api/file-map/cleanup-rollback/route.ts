/**파일 정리 롤백 매니페스트 조회 API.*/

import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import os from 'os';

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

function getRollbackDirPath(): string {
  const home = os.homedir();
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

function loadManifest(runId: string): RollbackManifest | null {
  const rollbackDir = getRollbackDirPath();
  const manifestFile = path.join(rollbackDir, `rollback_${runId}.json`);

  if (!fs.existsSync(manifestFile)) {
    return null;
  }

  try {
    const content = fs.readFileSync(manifestFile, 'utf-8');
    return JSON.parse(content) as RollbackManifest;
  } catch (error) {
    console.error('Failed to load manifest:', error);
    return null;
  }
}

/**
 * UUID 형식 검증.
 */
function isValidUuid(id: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(id);
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
