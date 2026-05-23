import { NextRequest, NextResponse } from 'next/server';
import { isSessionValid } from '@/lib/auth-session';
import {
  FileMapMaskingMode,
  ApiResponse,
  loadLocalFileMap,
  buildApprovalData,
  buildApprovalSummary,
} from '@/server/file-map/approvalRequestBuilder';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest): Promise<NextResponse<ApiResponse>> {
  try {
    const { searchParams } = new URL(request.url);

    const modeParam = searchParams.get('mode');
    const validModes: FileMapMaskingMode[] = ['mask_always', 'reveal_after_auth', 'reveal_on_trusted_device', 'reveal_for_export_with_warning'];
    const mode: FileMapMaskingMode = (modeParam && validModes.includes(modeParam as FileMapMaskingMode)) ? (modeParam as FileMapMaskingMode) : 'reveal_after_auth';

    const authVerified = isSessionValid();

    const fileMap = loadLocalFileMap();

    if (!fileMap) {
      return NextResponse.json(
        {
          ok: false,
          generated_at: new Date().toISOString(),
          approval_request_id: '',
          approval_required: false,
          execution_enabled: false,
          request_only: true,
          summary: {
            total_preview_items: 0,
            auto_selectable_items: 0,
            excluded_sensitive_items: 0,
            excluded_high_risk_items: 0,
            duplicate_review_items: 0,
          },
          approval_groups: [],
          excluded_groups: [],
          checklist: [],
          error: 'file_map_not_found',
        },
        { status: 404 }
      );
    }

    let shouldMask = true;

    switch (mode) {
      case 'mask_always':
        shouldMask = true;
        break;
      case 'reveal_after_auth':
        shouldMask = !authVerified;
        break;
      case 'reveal_on_trusted_device':
        shouldMask = !authVerified;
        break;
      case 'reveal_for_export_with_warning':
        shouldMask = true;
        break;
    }

    const { approval, excluded } = buildApprovalData(fileMap, shouldMask);
    const summary = buildApprovalSummary(approval, excluded);

    const requestId = `preview-local-${Date.now()}`;

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        approval_request_id: requestId,
        approval_required: true,
        execution_enabled: false,
        request_only: true,
        mode,
        auth_verified: authVerified,
        summary,
        approval_groups: approval,
        excluded_groups: excluded,
        checklist: [
          '실제 파일 이동 전 최종 확인 필요',
          '민감문서는 기본 제외됨',
          '중복 파일은 수동 확인 후 삭제',
          '대용량 파일(1GB+)은 별도 검토 필요',
        ],
      },
      { status: 200 }
    );

    if (!shouldMask) {
      response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    }

    return response;
  } catch (error) {
    console.error('API error:', error);
    return NextResponse.json(
      {
        ok: false,
        generated_at: new Date().toISOString(),
        approval_request_id: '',
        approval_required: false,
        execution_enabled: false,
        request_only: true,
        summary: {
          total_preview_items: 0,
          auto_selectable_items: 0,
          excluded_sensitive_items: 0,
          excluded_high_risk_items: 0,
          duplicate_review_items: 0,
        },
        approval_groups: [],
        excluded_groups: [],
        checklist: [],
        error: `api_failed: ${error instanceof Error ? error.message : 'unknown'}`,
      },
      { status: 500 }
    );
  }
}
