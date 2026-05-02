import { NextResponse } from 'next/server';
import { createSession } from '@/lib/auth-session';

export async function POST() {
  try {
    const session = createSession();

    return NextResponse.json(
      {
        ok: true,
        authenticated: true,
        expires_in_ms: session.expires_at - session.verified_at,
        expires_at: new Date(session.expires_at).toISOString(),
      },
      { status: 200 }
    );
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : 'unknown',
      },
      { status: 500 }
    );
  }
}
