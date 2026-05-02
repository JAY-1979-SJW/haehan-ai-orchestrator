import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { maskFileObject, maskPath } from '@/lib/privacy';
import { isSessionValid } from '@/lib/auth-session';

export const dynamic = 'force-dynamic';

interface FileMapReport {
  title?: string;
  scan_root?: string;
  scan_timestamp?: string;
  total_files?: number;
  categories?: Record<string, any>;
  large_files?: any[];
  old_files?: any[];
  suspicious_duplicates?: any[];
  suspicious_temp?: any[];
  recommendations?: string[];
  [key: string]: any;
}

interface ApiResponse {
  ok: boolean;
  generated_at: string;
  source: string;
  masked: boolean;
  report?: FileMapReport;
  error?: string;
  storage_info?: any;
}

function getStoragePath(): string {
  // Windows: AppData/Local/HaehanAI/inventory
  const home = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

function loadReport(storagePath: string): FileMapReport | null {
  const reportPath = path.join(storagePath, 'local_file_map.json');

  try {
    if (!fs.existsSync(reportPath)) {
      return null;
    }

    const content = fs.readFileSync(reportPath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    console.error('Failed to load report:', error);
    return null;
  }
}

function maskReport(report: FileMapReport): FileMapReport {
  if (!report) return report;

  const masked = { ...report };

  // 파일 목록 마스킹
  if (masked.large_files && Array.isArray(masked.large_files)) {
    masked.large_files = masked.large_files.map((file) =>
      maskFileObject(file, false)
    );
  }

  if (masked.old_files && Array.isArray(masked.old_files)) {
    masked.old_files = masked.old_files.map((file) =>
      maskFileObject(file, false)
    );
  }

  if (masked.suspicious_duplicates && Array.isArray(masked.suspicious_duplicates)) {
    masked.suspicious_duplicates = masked.suspicious_duplicates.map((file) =>
      maskFileObject(file, false)
    );
  }

  if (masked.suspicious_temp && Array.isArray(masked.suspicious_temp)) {
    masked.suspicious_temp = masked.suspicious_temp.map((file) =>
      maskFileObject(file, false)
    );
  }

  // 카테고리별 파일 마스킹
  if (masked.categories && typeof masked.categories === 'object') {
    const maskedCategories: Record<string, any> = {};
    for (const [key, value] of Object.entries(masked.categories)) {
      if (Array.isArray(value)) {
        maskedCategories[key] = value.map((file) =>
          maskFileObject(file, false)
        );
      } else {
        maskedCategories[key] = value;
      }
    }
    masked.categories = maskedCategories;
  }

  return masked;
}

export async function GET(request: NextRequest): Promise<NextResponse<ApiResponse>> {
  try {
    const storagePath = getStoragePath();
    const { searchParams } = new URL(request.url);
    const reveal = searchParams.get('reveal') === 'true';

    // reveal 요청은 인증 필요
    if (reveal && !isSessionValid()) {
      return NextResponse.json(
        {
          ok: false,
          generated_at: new Date().toISOString(),
          source: 'local_file_map',
          masked: true,
          error: 'auth_required',
        },
        { status: 401 }
      );
    }

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
          error: 'file_map_not_found',
          storage_info: storageInfo,
        },
        { status: 404 }
      );
    }

    // 마스킹 결정
    const shouldMask = !reveal; // reveal=true일 때만 원본, 아니면 항상 마스킹
    const responseReport = shouldMask ? maskReport(report) : report;

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        source: 'local_file_map',
        masked: shouldMask,
        report: responseReport,
      },
      { status: 200 }
    );

    // reveal 응답에는 캐시 금지
    if (reveal) {
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
