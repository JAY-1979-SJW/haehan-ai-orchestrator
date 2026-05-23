import { NextRequest, NextResponse } from 'next/server';
import {
  backendJsonHeaders,
  getBackendApiBase,
  requireBackendRole,
} from '@/lib/backend-auth';

export const dynamic = 'force-dynamic';
const APPROVAL_ROLES = ['admin', 'owner'] as const;

export async function GET(request: NextRequest): Promise<NextResponse> {
  try {
    const auth = await requireBackendRole(request, APPROVAL_ROLES);
    if (auth instanceof NextResponse) return auth;

    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    const approval_id = searchParams.get('approval_id');

    let url = `${getBackendApiBase()}/browser-approvals/requests`;
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (approval_id) params.append('approval_id', approval_id);

    if (params.toString()) {
      url += `?${params.toString()}`;
    }

    const response = await fetch(url, {
      method: 'GET',
      headers: backendJsonHeaders(auth),
      cache: 'no-store',
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('GET /api/approval/requests error:', error);
    return NextResponse.json(
      {
        ok: false,
        approvals: [],
        count: 0,
        error: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const auth = await requireBackendRole(request, APPROVAL_ROLES);
    if (auth instanceof NextResponse) return auth;

    const body = await request.json();

    const response = await fetch(`${getBackendApiBase()}/browser-approvals/requests`, {
      method: 'POST',
      headers: backendJsonHeaders(auth),
      body: JSON.stringify(body),
      cache: 'no-store',
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('POST /api/approval/requests error:', error);
    return NextResponse.json(
      {
        ok: false,
        approval_event_id: '',
        approval_id: '',
        error: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
