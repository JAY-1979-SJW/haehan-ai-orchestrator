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
 * 승인 토큰 검증.
 */
function validateApprovalToken(token: string): boolean {
  return token && token.startsWith('user-approved-cleanup-');
}

/**
 * Python cleanup_executor_api.py 호출.
 */
function callPythonExecutor(inputData: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    try {
      // Python 스크립트 경로
      const pythonScriptPath = path.resolve(
        'agent/local_inventory/file_map/cleanup_executor_api.py'
      );

      if (!fs.existsSync(pythonScriptPath)) {
        throw new Error(
          `cleanup_executor_api.py를 찾을 수 없습니다: ${pythonScriptPath}`
        );
      }

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
    const pythonResult = await callPythonExecutor({
      preflight_id,
      package_id,
      approval_token,
      user_confirmed_execution,
      dry_run: dryRunValue,
      plans,
      base_target_dir,
      include_sensitive,
    });

    if (!pythonResult.ok) {
      return NextResponse.json(
        { ok: false, error: pythonResult.error || '알 수 없는 오류' },
        { status: 400 }
      );
    }

    const result = pythonResult.result;

    return NextResponse.json({
      ok: true,
      run_id: result.run_id,
      package_id: result.package_id,
      timestamp: result.timestamp,
      success_count: result.success_count,
      failed_count: result.failed_count,
      skipped_count: result.skipped_count,
      conflict_count: result.conflict_count,
      succeeded: result.succeeded,
      failed: result.failed,
      skipped: result.skipped,
      conflicts: result.conflicts,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json(
      { ok: false, error: `실행 실패: ${message}` },
      { status: 500 }
    );
  }
}
