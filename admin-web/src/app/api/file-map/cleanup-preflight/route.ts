/**파일 정리 사전검사 API.*/

import { NextRequest, NextResponse } from 'next/server';
import { callPythonExecutorPreflight } from '@/lib/file-map/pythonExecutor';

interface PreflightRequest {
  plans: Array<{
    operation_id: string;
    path: string;
    category: string;
    file_size_bytes: number;
    file_name: string;
  }>;
  base_target_dir: string;
  include_sensitive?: boolean;
}

interface ExecutorPlan {
  source: string;
  target: string;
  confirmed: boolean;
}

interface PreflightItem {
  operation_id: string;
  source_path: string;
  target_path: string;
  category: string;
  status: 'ok' | 'conflict' | 'source_missing' | 'system_path' | 'blocked';
  reason: string;
}

interface PreflightResponse {
  ok: boolean;
  preflight_id?: string;
  total?: number;
  ok_count?: number;
  conflict_count?: number;
  skipped_count?: number;
  blocked_count?: number;
  items?: PreflightItem[];
  error?: string;
}

/**
 * POST /api/file-map/cleanup-preflight
 *
 * 정리 계획에 대한 사전검사 실행.
 */
export async function POST(req: NextRequest): Promise<NextResponse<PreflightResponse>> {
  try {
    const body = (await req.json()) as PreflightRequest;

    const { plans, base_target_dir, include_sensitive } = body;

    if (!plans || !Array.isArray(plans)) {
      return NextResponse.json(
        { ok: false, error: '계획 목록이 필요합니다' },
        { status: 400 }
      );
    }

    if (!base_target_dir) {
      return NextResponse.json(
        { ok: false, error: '기본 대상 디렉토리가 필요합니다' },
        { status: 400 }
      );
    }

    // file-map-executor preflight 호출
    const executorPlans: ExecutorPlan[] = plans.map((plan) => ({
      source: plan.path,
      target: `${base_target_dir}/${plan.file_name}`,
      confirmed: true,
    }));

    const executorResult = (await callPythonExecutorPreflight({
      base_target_dir,
      plans: executorPlans,
      include_sensitive,
    })) as Record<string, any>;

    if (!executorResult.ok) {
      const errorMsg =
        typeof executorResult.error === 'string'
          ? executorResult.error
          : '알 수 없는 오류';
      return NextResponse.json(
        { ok: false, error: errorMsg },
        { status: 400 }
      );
    }

    // executor 응답을 admin-web 형식으로 변환
    const executorItems = (executorResult.items || []) as Array<{
      source: string;
      target: string;
      status: string;
      reason: string;
    }>;

    const items: PreflightItem[] = executorItems.map((item, idx) => {
      const originalPlan = plans[idx];
      return {
        operation_id: originalPlan?.operation_id || `op-${idx}`,
        source_path: item.source,
        target_path: item.target,
        category: originalPlan?.category || 'unknown',
        status: (item.status === 'source_missing' ? 'source_missing' : 'ok') as any,
        reason: item.reason,
      };
    });

    return NextResponse.json({
      ok: true,
      preflight_id: executorResult.preflight_id,
      total: executorResult.total,
      ok_count: executorResult.ok_count,
      conflict_count: executorResult.conflict_count,
      skipped_count: executorResult.skipped_count,
      blocked_count: executorResult.blocked_count || 0,
      items,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json(
      { ok: false, error: `사전검사 실행 실패: ${message}` },
      { status: 500 }
    );
  }
}
