/**파일 정리 실행 API.*/

import { NextRequest, NextResponse } from 'next/server';
import { v4 as uuidv4 } from 'uuid';

interface ExecuteRequest {
  preflight_id: string;
  package_id: string;
  approval_token: string;
  user_confirmed_execution: boolean;
  dry_run?: boolean;
}

interface ExecuteResponse {
  ok: boolean;
  run_id?: string;
  package_id?: string;
  timestamp?: string;
  success_count?: number;
  failed_count?: number;
  skipped_count?: number;
  conflict_count?: number;
  succeeded?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    category: string;
    file_size_bytes: number;
    dry_run: boolean;
  }>;
  failed?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    error: string;
  }>;
  skipped?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    reason: string;
  }>;
  conflicts?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    reason: string;
  }>;
  error?: string;
}

/**
 * 승인 토큰 검증.
 */
function validateApprovalToken(token: string): boolean {
  return token && token.startsWith('user-approved-cleanup-');
}

/**
 * POST /api/file-map/cleanup-execute
 *
 * 파일 이동 실행 (승인 토큰 필수).
 */
export async function POST(req: NextRequest): Promise<NextResponse<ExecuteResponse>> {
  try {
    const body = (await req.json()) as ExecuteRequest;

    const {
      preflight_id,
      package_id,
      approval_token,
      user_confirmed_execution,
      dry_run = true,
    } = body;

    // 승인 토큰 검증
    if (!validateApprovalToken(approval_token)) {
      return NextResponse.json(
        { ok: false, error: '유효하지 않은 승인 토큰입니다' },
        { status: 401 }
      );
    }

    // 사용자 확인 검증
    if (!user_confirmed_execution) {
      return NextResponse.json(
        { ok: false, error: '사용자 최종 확인이 필요합니다' },
        { status: 400 }
      );
    }

    // preflight_id 검증
    if (!preflight_id) {
      return NextResponse.json(
        { ok: false, error: '사전검사 ID가 필요합니다' },
        { status: 400 }
      );
    }

    const runId = uuidv4();
    const timestamp = new Date().toISOString();

    // 모의 실행 (실제 구현은 Python cleanup_executor 모듈 호출)
    // TODO: Python cleanup_executor 모듈 호출
    // shutil.move는 cleanup_executor.py에서만 수행

    return NextResponse.json({
      ok: true,
      run_id: runId,
      package_id,
      timestamp,
      success_count: 0,
      failed_count: 0,
      skipped_count: 0,
      conflict_count: 0,
      succeeded: [],
      failed: [],
      skipped: [],
      conflicts: [],
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json(
      { ok: false, error: `실행 실패: ${message}` },
      { status: 500 }
    );
  }
}
