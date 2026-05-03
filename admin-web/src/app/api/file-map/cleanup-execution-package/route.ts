import { NextRequest, NextResponse } from 'next/server';
import { isSessionValid } from '@/lib/auth-session';
import {
  FileMapMaskingMode,
  ApiResponse,
  RequestBody,
  loadLocalFileMap,
  buildExecutionOperations,
  getMaskingPolicy,
  errorResponse,
  successResponse,
} from '@/server/file-map/executionPackageBuilder';

export const dynamic = 'force-dynamic';

const VALID_MODES: FileMapMaskingMode[] = ['mask_always', 'reveal_after_auth', 'reveal_on_trusted_device', 'reveal_for_export_with_warning'];
const DEFAULT_MODE: FileMapMaskingMode = 'reveal_after_auth';
const ALLOWED_GROUPS = new Set(['documents', 'spreadsheets', 'cad', 'images', 'archive']);
const DEFAULT_SELECTED = Array.from(ALLOWED_GROUPS);

function parseMode(modeParam: string | null): FileMapMaskingMode {
  return (modeParam && VALID_MODES.includes(modeParam as FileMapMaskingMode)) ? (modeParam as FileMapMaskingMode) : DEFAULT_MODE;
}

export async function GET(request: NextRequest): Promise<NextResponse<ApiResponse>> {
  try {
    const { searchParams } = new URL(request.url);
    const mode = parseMode(searchParams.get('mode'));
    const authVerified = isSessionValid();
    const fileMap = loadLocalFileMap();

    if (!fileMap) {
      const { body, status } = errorResponse('file_map_not_found', 404);
      return NextResponse.json(body, { status });
    }

    const shouldMask = getMaskingPolicy(mode, authVerified);
    const { operations, excluded } = buildExecutionOperations(fileMap, DEFAULT_SELECTED, shouldMask);
    const { body, status } = successResponse(operations, excluded, mode, authVerified, DEFAULT_SELECTED);
    const response = NextResponse.json(body, { status });

    if (!shouldMask) {
      response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    }
    return response;
  } catch (error) {
    const { body, status } = errorResponse(`api_failed: ${error instanceof Error ? error.message : 'unknown'}`, 500);
    return NextResponse.json(body, { status });
  }
}

export async function POST(request: NextRequest): Promise<NextResponse<ApiResponse>> {
  try {
    const { searchParams } = new URL(request.url);
    const mode = parseMode(searchParams.get('mode'));
    const body: RequestBody = await request.json();
    const selectedGroupIds = body.selected_group_ids || [];

    const validSelectedGroups = selectedGroupIds.filter((id: string) => ALLOWED_GROUPS.has(id));
    const authVerified = isSessionValid();
    const fileMap = loadLocalFileMap();

    if (!fileMap) {
      const { body: errBody, status } = errorResponse('file_map_not_found', 404);
      return NextResponse.json(errBody, { status });
    }

    const shouldMask = getMaskingPolicy(mode, authVerified);
    const { operations, excluded } = buildExecutionOperations(fileMap, validSelectedGroups, shouldMask);
    const { body: respBody, status } = successResponse(operations, excluded, mode, authVerified, validSelectedGroups);
    const response = NextResponse.json(respBody, { status });

    if (!shouldMask) {
      response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    }
    return response;
  } catch (error) {
    const { body, status } = errorResponse(`api_failed: ${error instanceof Error ? error.message : 'unknown'}`, 500);
    return NextResponse.json(body, { status });
  }
}
