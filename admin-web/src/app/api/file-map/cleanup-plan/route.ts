import { NextRequest, NextResponse } from 'next/server';
import { isSessionValid } from '@/lib/auth-session';
import {
  loadLocalFileMap,
  buildCleanupSummary,
  buildCategories,
  CleanupPlanCategory,
  CleanupPlanSummary,
} from '@/server/file-map/planCache';

export const dynamic = 'force-dynamic';

type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';

interface ApiResponse {
  ok: boolean;
  generated_at: string;
  source: string;
  masked: boolean;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  execution_enabled: boolean;
  summary?: CleanupPlanSummary;
  suggested_structure?: string;
  categories?: Record<string, CleanupPlanCategory>;
  error?: string;
}

const SUGGESTED_STRUCTURE = `01_PROJECT_FILE_정리안/
├─ 01_업무문서/
│  ├─ 업무문서/           (보고서, 계획안, 공문 등)
│  ├─ 엑셀_내역_정산/     (재무, 정산, 내역 등)
│  ├─ CAD_도면/           (도면, 설계도 등)
│  ├─ 사진_스캔/          (스캔, 촬영 이미지)
│  ├─ 계약_증빙_민감/     (계약서, 통장, 신분증 등)
│  ├─ 설치파일_보관/      (1년 이상 미사용 설치파일)
│  ├─ 압축_백업/          (백업, 압축 아카이브)
│  └─ 중복검토/           (복사본, 사본, 검토 필요)
└─ 99_분류보류/
   └─                      (미분류, 최근파일, 확장자 없음 등)`;

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
          source: 'local_cleanup_plan',
          masked: true,
          execution_enabled: false,
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
        shouldMask = false;
        break;
      case 'reveal_for_export_with_warning':
        shouldMask = true;
        break;
    }

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        source: 'local_cleanup_plan',
        masked: shouldMask,
        mode,
        auth_verified: authVerified,
        execution_enabled: false,
        summary: buildCleanupSummary(fileMap),
        suggested_structure: SUGGESTED_STRUCTURE,
        categories: buildCategories(fileMap, shouldMask),
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
        source: 'local_cleanup_plan',
        masked: true,
        execution_enabled: false,
        error: `api_failed: ${error instanceof Error ? error.message : 'unknown'}`,
      },
      { status: 500 }
    );
  }
}
