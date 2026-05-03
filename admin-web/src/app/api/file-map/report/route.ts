import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import { isSessionValid } from '@/lib/auth-session';
import {
  FileMapMaskingMode,
  ApiResponse,
  getStoragePath,
  loadReport,
  maskReport,
} from '@/server/file-map/reportBuilder';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest): Promise<NextResponse<ApiResponse>> {
  try {
    const storagePath = getStoragePath();
    const { searchParams } = new URL(request.url);

    // mode 파라미터 읽기 (기본값: reveal_after_auth)
    const modeParam = searchParams.get('mode');
    const validModes: FileMapMaskingMode[] = ['mask_always', 'reveal_after_auth', 'reveal_on_trusted_device', 'reveal_for_export_with_warning'];
    const mode: FileMapMaskingMode = (modeParam && validModes.includes(modeParam as FileMapMaskingMode)) ? (modeParam as FileMapMaskingMode) : 'reveal_after_auth';

    // 인증 상태 확인
    const authVerified = isSessionValid();

    // 저장소 정보
    const storageInfo = {
      storage_dir: storagePath,
      exists: fs.existsSync(storagePath),
    };

    // 보고서 로드
    const report = loadReport(storagePath);

    if (!report) {
      return NextResponse.json(
        {
          ok: false,
          generated_at: new Date().toISOString(),
          source: 'local_file_map',
          masked: true,
          mode,
          error: 'file_map_not_found',
          storage_info: storageInfo,
        },
        { status: 404 }
      );
    }

    // mode별 마스킹 정책 결정
    let shouldMask = true;
    let authRequired = false;
    let exportWarning = false;

    switch (mode) {
      case 'mask_always':
        shouldMask = true;
        break;

      case 'reveal_after_auth':
        // 인증 필요: auth_verified=true일 때만 원본
        if (!authVerified) {
          shouldMask = true;
          authRequired = true;
        } else {
          shouldMask = false;
        }
        break;

      case 'reveal_on_trusted_device':
        // 로컬 화면: 항상 원본 허용
        shouldMask = false;
        break;

      case 'reveal_for_export_with_warning':
        // 외부전송: 경고만 반환, 원본은 차단
        shouldMask = true;
        exportWarning = true;
        break;
    }

    // 인증 필요한데 미인증이면 401
    if (authRequired && !authVerified) {
      return NextResponse.json(
        {
          ok: false,
          generated_at: new Date().toISOString(),
          source: 'local_file_map',
          masked: true,
          mode,
          auth_verified: false,
          error: 'auth_required',
        },
        { status: 401 }
      );
    }

    const responseReport = shouldMask ? maskReport(report) : report;

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        source: 'local_file_map',
        masked: shouldMask,
        mode,
        auth_verified: authVerified,
        ...(exportWarning && { export_warning: true }),
        report: responseReport,
      },
      { status: 200 }
    );

    // 원본 데이터 응답은 항상 캐시 금지
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
        source: 'local_file_map',
        masked: true,
        error: `api_failed: ${error instanceof Error ? error.message : 'unknown'}`,
      },
      { status: 500 }
    );
  }
}
