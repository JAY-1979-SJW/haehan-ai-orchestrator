/**파일 정리 사전검사 API.*/

import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

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

    // 대상 디렉토리 존재 확인
    try {
      await fs.access(base_target_dir);
    } catch {
      return NextResponse.json(
        { ok: false, error: '대상 디렉토리가 존재하지 않습니다' },
        { status: 400 }
      );
    }

    // 모의 사전검사 실행 (실제 구현은 Python 모듈 호출)
    // TODO: Python cleanup_preflight 모듈 호출
    const preflightId = `preflight-${Date.now()}`;
    const items: PreflightItem[] = [];
    let okCount = 0;
    let conflictCount = 0;
    let skippedCount = 0;
    let blockedCount = 0;

    for (const plan of plans) {
      // 단순 검증: 파일 존재 확인
      try {
        await fs.access(plan.path);
        items.push({
          operation_id: plan.operation_id,
          source_path: plan.path,
          target_path: path.join(base_target_dir, path.basename(plan.path)),
          category: plan.category,
          status: 'ok',
          reason: '',
        });
        okCount++;
      } catch {
        items.push({
          operation_id: plan.operation_id,
          source_path: plan.path,
          target_path: '',
          category: plan.category,
          status: 'source_missing',
          reason: '소스 파일이 존재하지 않습니다',
        });
        skippedCount++;
      }
    }

    return NextResponse.json({
      ok: true,
      preflight_id: preflightId,
      total: plans.length,
      ok_count: okCount,
      conflict_count: conflictCount,
      skipped_count: skippedCount,
      blocked_count: blockedCount,
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
