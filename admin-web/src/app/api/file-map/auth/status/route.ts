import { NextResponse } from 'next/server';
import { getSession, getTimeRemaining } from '@/lib/auth-session';

export async function GET() {
  try {
    const session = getSession();

    if (!session) {
      return NextResponse.json(
        {
          ok: true,
          authenticated: false,
          time_remaining_ms: 0,
        },
        { status: 200 }
      );
    }

    const timeRemaining = getTimeRemaining();

    return NextResponse.json(
      {
        ok: true,
        authenticated: true,
        verified_at: new Date(session.verified_at).toISOString(),
        expires_at: new Date(session.expires_at).toISOString(),
        time_remaining_ms: timeRemaining,
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
