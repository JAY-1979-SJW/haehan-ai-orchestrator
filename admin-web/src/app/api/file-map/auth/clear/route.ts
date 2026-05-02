import { NextResponse } from 'next/server';
import { clearSession } from '@/lib/auth-session';

export async function POST() {
  try {
    clearSession();

    return NextResponse.json(
      {
        ok: true,
        message: 'Session cleared',
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
