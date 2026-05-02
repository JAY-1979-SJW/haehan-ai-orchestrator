import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { isSessionValid } from '@/lib/auth-session';

export const dynamic = 'force-dynamic';

type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';

interface CleanupPlanCategory {
  name: string;
  count: number;
  reason: string;
  suggested_path: string;
  samples: Array<{
    masked_name: string;
    file_path: string;
    size_bytes: number;
    modified_time: string;
  }>;
}

interface CleanupPlanSummary {
  total_files: number;
  archive_candidates: number;
  document_candidates: number;
  spreadsheet_candidates: number;
  cad_candidates: number;
  image_candidates: number;
  sensitive_candidates: number;
  duplicate_review_candidates: number;
  hold_candidates: number;
}

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

function getStoragePath(): string {
  const home = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

function loadLocalFileMap(): any {
  const storagePath = getStoragePath();
  const reportPath = path.join(storagePath, 'local_file_map.json');

  try {
    if (!fs.existsSync(reportPath)) {
      return null;
    }

    const content = fs.readFileSync(reportPath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    console.error('Failed to load local_file_map:', error);
    return null;
  }
}

function maskFilename(filename: string): string {
  // 강한 민감 패턴
  const strongPatterns: Record<string, string> = {
    '신분증': '[신분증]',
    '주민등록증': '[주민등록증]',
    '운전면허': '[운전면허]',
    '여권': '[여권]',
    '통장.*사본': '[통장사본]',
    '계좌': '[계좌]',
    '금통': '[금융]',
    '은행': '[은행]',
    '형사.*사건': '[형사사건]',
    '고소': '[고소]',
    '소송': '[소송]',
    '변호인.*의견': '[법률문서]',
    '개인정보': '[개인정보]',
    '급여': '[급여]',
    '노임': '[급여]',
    '증거': '[증거]',
    '기밀': '[기밀]',
  };

  let masked = filename;

  // 강한 패턴 마스킹
  for (const [pattern, replacement] of Object.entries(strongPatterns)) {
    masked = masked.replace(new RegExp(pattern, 'gi'), replacement);
  }

  // 약한 패턴 (강한 패턴 포함되면)
  const hasStrong = Object.keys(strongPatterns).some(
    (pattern) => new RegExp(pattern, 'i').test(filename)
  );

  if (hasStrong) {
    const weakPatterns: Record<string, string> = {
      '계약서': '[계약서]',
      '변호사': '[법률]',
      '합의금': '[계약]',
    };

    for (const [pattern, replacement] of Object.entries(weakPatterns)) {
      masked = masked.replace(new RegExp(pattern, 'gi'), replacement);
    }

    // 개인명 마스킹
    masked = masked.replace(/[가-힣]{2,4}(?=[\s_])/g, '****');
  }

  return masked;
}

function buildCleanupSummary(fileMap: any): CleanupPlanSummary {
  return {
    total_files: fileMap.total_files || 0,
    archive_candidates: fileMap.large_files?.length || 0,
    document_candidates: fileMap.files_by_category?.document || 0,
    spreadsheet_candidates: fileMap.files_by_category?.spreadsheet || 0,
    cad_candidates: fileMap.files_by_category?.cad || 0,
    image_candidates: fileMap.files_by_category?.image || 0,
    sensitive_candidates: Math.ceil((fileMap.old_files?.length || 0) * 0.02), // 대략 2%
    duplicate_review_candidates: fileMap.suspicious_duplicates?.length || 0,
    hold_candidates: fileMap.suspicious_temp?.length || 0,
  };
}

function buildCategories(fileMap: any, shouldMask: boolean): Record<string, CleanupPlanCategory> {
  const processFiles = (files: any[], categoryName: string, reason: string, suggestedPath: string): CleanupPlanCategory => {
    const samples = (files || []).slice(0, 30).map((file: any) => ({
      masked_name: shouldMask ? maskFilename(file.name || '') : file.name || '',
      file_path: file.path || '',
      size_bytes: file.size_bytes || 0,
      modified_time: file.modified_time || '',
    }));

    return {
      name: categoryName,
      count: files?.length || 0,
      reason,
      suggested_path: suggestedPath,
      samples,
    };
  };

  return {
    archive: processFiles(fileMap.large_files, '보관', '오래된 설치파일', '01_업무문서/06_설치파일_보관'),
    documents: processFiles(
      (fileMap.files_by_category?.document_files || []).slice(0, 100),
      '업무문서',
      '분류 가능한 업무 문서',
      '01_업무문서'
    ),
    spreadsheets: processFiles(
      (fileMap.files_by_category?.spreadsheet_files || []).slice(0, 100),
      '엑셀/정산',
      '스프레드시트 및 내역서',
      '02_엑셀_내역_정산'
    ),
    cad: processFiles(
      (fileMap.files_by_category?.cad_files || []).slice(0, 50),
      'CAD/도면',
      '도면 및 설계 파일',
      '03_CAD_도면'
    ),
    images: processFiles(
      (fileMap.files_by_category?.image_files || []).slice(0, 100),
      '이미지/스캔',
      '사진, 스캔, 이미지',
      '04_사진_스캔'
    ),
    sensitive: processFiles(
      (fileMap.old_files || []).filter((f: any) =>
        /신분증|통장|계좌|급여|형사|고소|소송|변호인/.test(f.name || '')
      ).slice(0, 50),
      '민감문서',
      '보안이 필요한 민감문서',
      '01_업무문서/05_계약_증빙_민감'
    ),
    duplicates: processFiles(fileMap.suspicious_duplicates, '중복검토', '검토 후 삭제 가능한 중복 파일', '01_업무문서/08_중복검토'),
    hold: processFiles(fileMap.suspicious_temp, '분류보류', '현재 분류 불가 또는 최근 파일', '99_분류보류'),
  };
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

    // mode 파라미터 읽기
    const modeParam = searchParams.get('mode');
    const validModes: FileMapMaskingMode[] = ['mask_always', 'reveal_after_auth', 'reveal_on_trusted_device', 'reveal_for_export_with_warning'];
    const mode: FileMapMaskingMode = (modeParam && validModes.includes(modeParam as FileMapMaskingMode)) ? (modeParam as FileMapMaskingMode) : 'reveal_after_auth';

    // 인증 상태
    const authVerified = isSessionValid();

    // 파일맵 로드
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

    // mode별 마스킹 결정
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

    // 원본 데이터 응답은 캐시 금지
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
