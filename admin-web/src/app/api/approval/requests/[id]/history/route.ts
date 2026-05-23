import { NextRequest, NextResponse } from 'next/server';
import {
  backendJsonHeaders,
  getBackendApiBase,
  requireBackendRole,
} from '@/lib/backend-auth';

export const dynamic = 'force-dynamic';
const APPROVAL_ROLES = ['admin', 'owner'] as const;

interface RouteParams {
  params: {
    id: string;
  };
}

export async function GET(
  request: NextRequest,
  { params }: RouteParams
): Promise<NextResponse> {
  try {
    const auth = await requireBackendRole(request, APPROVAL_ROLES);
    if (auth instanceof NextResponse) return auth;

    const { id } = params;

    const response = await fetch(`${getBackendApiBase()}/browser-approvals/requests/${id}/history`, {
      method: 'GET',
      headers: backendJsonHeaders(auth),
      cache: 'no-store',
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`GET /api/approval/requests/[id]/history error:`, error);
    return NextResponse.json(
      {
        ok: false,
        approval_id: '',
        events: [],
        count: 0,
        error: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
