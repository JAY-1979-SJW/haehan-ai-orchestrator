import { NextRequest, NextResponse } from 'next/server';
import { isSessionValid } from '@/lib/auth-session';
import {
  FileMapMaskingMode,
  ApiResponse,
  loadLocalFileMap,
  buildPreviewItems,
} from '@/server/file-map/cleanupPreviewBuilder';

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
          execution_enabled: false,
          preview_only: true,
          total_items: 0,
          items: [],
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

    const items = buildPreviewItems(fileMap, shouldMask);

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        execution_enabled: false,
        preview_only: true,
        total_items: items.length,
        mode,
        auth_verified: authVerified,
        masked: shouldMask,
        items,
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
        execution_enabled: false,
        preview_only: true,
        total_items: 0,
        items: [],
        error: `api_failed: ${error instanceof Error ? error.message : 'unknown'}`,
      },
      { status: 500 }
    );
  }
}
