import { cookies } from 'next/headers';

interface AuthSession {
  verified_at: number;
  expires_at: number;
}

const authSessions = new Map<string, AuthSession>();
const SESSION_COOKIE = 'haehan_file_map_auth';
const SESSION_DURATION_MS = 15 * 60 * 1000;

function getSessionIdFromCookie(): string {
  return cookies().get(SESSION_COOKIE)?.value || '';
}

export function createSession(): {
  session_id: string;
  verified_at: number;
  expires_at: number;
} {
  const now = Date.now();
  const sessionId = crypto.randomUUID();
  const session: AuthSession = {
    verified_at: now,
    expires_at: now + SESSION_DURATION_MS,
  };
  authSessions.set(sessionId, session);
  cookies().set(SESSION_COOKIE, sessionId, {
    httpOnly: true,
    sameSite: 'strict',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    expires: new Date(session.expires_at),
  });
  return { session_id: sessionId, ...session };
}

export function isSessionValid(): boolean {
  const sessionId = getSessionIdFromCookie();
  if (!sessionId) return false;
  const session = authSessions.get(sessionId);
  if (!session) return false;
  const now = Date.now();
  if (now > session.expires_at) {
    authSessions.delete(sessionId);
    return false;
  }
  return true;
}

export function getSession(): AuthSession | null {
  const sessionId = getSessionIdFromCookie();
  if (!sessionId) return null;
  const session = authSessions.get(sessionId);
  if (!session) return null;
  const now = Date.now();
  if (now > session.expires_at) {
    authSessions.delete(sessionId);
    return null;
  }
  return session;
}

export function clearSession(): void {
  const sessionId = getSessionIdFromCookie();
  if (sessionId) authSessions.delete(sessionId);
  cookies().delete(SESSION_COOKIE);
}

export function getTimeRemaining(): number {
  const session = getSession();
  if (!session) return 0;
  return Math.max(0, session.expires_at - Date.now());
}
