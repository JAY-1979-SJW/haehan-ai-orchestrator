import { NextRequest, NextResponse } from 'next/server';

export interface BackendAuthContext {
  authorization: string;
  actor: string;
  role: string;
}

export function getBackendApiBase(): string {
  return (
    process.env.ORCHESTRATOR_API_BASE ||
    process.env.FASTAPI_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE ||
    'http://localhost:8400/api/v1'
  ).replace(/\/$/, '');
}

function unauthorized(message = 'backend_basic_auth_required'): NextResponse {
  return NextResponse.json(
    { ok: false, error: message },
    {
      status: 401,
      headers: { 'WWW-Authenticate': 'Basic' },
    }
  );
}

export async function requireBackendRole(
  request: NextRequest,
  allowedRoles: readonly string[]
): Promise<BackendAuthContext | NextResponse> {
  const authorization = request.headers.get('authorization') || '';
  if (!authorization.toLowerCase().startsWith('basic ')) {
    return unauthorized();
  }

  let response: Response;
  try {
    response = await fetch(`${getBackendApiBase()}/auth/me`, {
      method: 'GET',
      headers: { Authorization: authorization },
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    return NextResponse.json(
      { ok: false, error: 'backend_auth_unavailable' },
      { status: 503 }
    );
  }

  if (response.status === 401) {
    return unauthorized('backend_auth_rejected');
  }
  if (!response.ok) {
    return NextResponse.json(
      { ok: false, error: 'backend_auth_check_failed' },
      { status: response.status }
    );
  }

  const user = (await response.json()) as { actor?: string; role?: string };
  const role = user.role || '';
  if (!allowedRoles.includes(role)) {
    return NextResponse.json(
      { ok: false, error: 'insufficient_role' },
      { status: 403 }
    );
  }

  return {
    authorization,
    actor: user.actor || '',
    role,
  };
}

export function backendJsonHeaders(auth: BackendAuthContext): HeadersInit {
  return {
    'Content-Type': 'application/json',
    Authorization: auth.authorization,
  };
}
