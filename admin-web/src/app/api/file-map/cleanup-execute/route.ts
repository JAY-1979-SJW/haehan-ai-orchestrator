/**파일 정리 실행 API.*/

import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

interface ExecuteRequest {
  preflight_id: string;
  package_id: string;
  approval_token: string;
  user_confirmed_execution: boolean;
  dry_run?: boolean;
  plans?: Array<any>;
  base_target_dir?: string;
  include_sensitive?: boolean;
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
 * cleanup_executor_api.py 경로 해석.
 * 고정 후보 경로에서 첫 번째 존재하는 파일 반환.
 */
function resolveCleanupExecutorPath(): string {
  const candidates = [
    path.resolve(process.cwd(), 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py'),
    path.resolve(process.cwd(), '..', 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py'),
  ];

  const found = candidates.find((candidate) => fs.existsSync(candidate));

  if (!found) {
    throw new Error('cleanup_executor_api.py를 찾을 수 없습니다');
  }

  return found;
}

/**
 * 승인 토큰 검증 (UUID suffix 포함).
 */
function validateApprovalToken(token: string): boolean {
  const prefix = 'user-approved-cleanup-';
  if (!token || !token.startsWith(prefix)) {
    return false;
  }

  const suffix = token.slice(prefix.length);
  const uuidRegex =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  return uuidRegex.test(suffix);
}

/**
 * Python cleanup_executor_api.py 호출.
 */
function callPythonExecutor(inputData: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    try {
      // Python 스크립트 경로
      const pythonScriptPath = resolveCleanupExecutorPath();

      const child = spawn('python', [pythonScriptPath], {
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';

      child.stdout?.on('data', (data) => {
        stdout += data.toString();
      });

      child.stderr?.on('data', (data) => {
        stderr += data.toString();
      });

      child.on('close', (code) => {
        if (stderr) {
          console.error('Python stderr:', stderr);
        }

        if (code !== 0) {
          reject(new Error(`Python 실행 실패 (exit code ${code}): ${stderr}`));
          return;
        }

        try {
          const result = JSON.parse(stdout);
          resolve(result);
        } catch (e) {
          reject(new Error(`Python 응답 파싱 실패: ${stdout}`));
        }
      });

      child.on('error', (err) => {
        reject(new Error(`Python 실행 오류: ${err.message}`));
      });

      child.stdin?.write(JSON.stringify(inputData));
      child.stdin?.end();
    } catch (error) {
      reject(error);
    }
  });
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
      dry_run,
      plans = [],
      base_target_dir,
      include_sensitive = false,
    } = body;

    const dryRunValue: boolean = dry_run === false ? false : true;

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

    // Python 실행
    const pythonResult = (await callPythonExecutor({
      preflight_id,
      package_id,
      approval_token,
      user_confirmed_execution,
      dry_run: dryRunValue,
      plans,
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
