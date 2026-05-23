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

export async function POST(
  request: NextRequest,
  { params }: RouteParams
): Promise<NextResponse> {
  try {
    const auth = await requireBackendRole(request, APPROVAL_ROLES);
    if (auth instanceof NextResponse) return auth;

    const { id } = params;
    const body = await request.json();

    // Ensure approval_event_type is set to APPROVAL_REJECTED
    const decisionBody = {
      ...body,
      approval_event_type: 'APPROVAL_REJECTED',
    };

    const response = await fetch(`${getBackendApiBase()}/browser-approvals/requests/${id}/reject`, {
      method: 'POST',
      headers: backendJsonHeaders(auth),
      body: JSON.stringify(decisionBody),
      cache: 'no-store',
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`POST /api/approval/requests/[id]/reject error:`, error);
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
