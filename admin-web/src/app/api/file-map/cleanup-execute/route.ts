/**파일 정리 실행 API.*/

import { NextRequest, NextResponse } from 'next/server';
import { validateApprovalToken } from '@/lib/file-map/approvalToken';
import { ExecuteRequest, ExecuteResponse, normalizePlans } from '@/lib/file-map/executePayload';
import { callPythonExecutor } from '@/lib/file-map/pythonExecutor';

export async function POST(req: NextRequest): Promise<NextResponse<ExecuteResponse>> {
  try {
    const body = (await req.json()) as ExecuteRequest;

    const {
      preflight_id,
      package_id,
      approval_token,
      user_confirmed_execution,
      dry_run,
      plans = [],
      base_target_dir,
      include_sensitive = false,
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

    // plans 정규화
    const normalizedPlans = normalizePlans(plans as unknown[]);

    // Python 실행
    const pythonResult = (await callPythonExecutor({
      preflight_id,
      package_id,
      approval_token,
      user_confirmed_execution,
      dry_run: dry_run === false ? false : true,
      plans: normalizedPlans,
      base_target_dir,
      include_sensitive,
    })) as Record<string, any>;

    if (!pythonResult.ok) {
      const errorMsg = typeof pythonResult.error === 'string'
        ? pythonResult.error
        : '알 수 없는 오류';
      return NextResponse.json(
        { ok: false, error: errorMsg },
        { status: 400 }
      );
    }

    const result = pythonResult.result as Record<string, any>;

    return NextResponse.json({
      ok: true,
      run_id: result.run_id as string,
      package_id: result.package_id as string,
      timestamp: result.timestamp as string,
      success_count: result.success_count as number,
      failed_count: result.failed_count as number,
      skipped_count: result.skipped_count as number,
      conflict_count: result.conflict_count as number,
      succeeded: result.succeeded as Array<any>,
      failed: result.failed as Array<any>,
      skipped: result.skipped as Array<any>,
      conflicts: result.conflicts as Array<any>,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json(
      { ok: false, error: `실행 실패: ${message}` },
      { status: 500 }
    );
  }
}
