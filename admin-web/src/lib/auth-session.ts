/**
 * 파일 지도 인증 세션 관리
 * 메모리 기반 (서버 재시작 시 초기화)
 */

interface AuthSession {
  verified_at: number;
  expires_at: number;
}

const authSessions = new Map<string, AuthSession>();
const SESSION_ID = 'local_file_map_auth';
const SESSION_DURATION_MS = 15 * 60 * 1000; // 15분

export function createSession(): { verified_at: number; expires_at: number } {
  const now = Date.now();
  const session: AuthSession = {
    verified_at: now,
    expires_at: now + SESSION_DURATION_MS,
  };
  authSessions.set(SESSION_ID, session);
  return session;
}

export function isSessionValid(): boolean {
  const session = authSessions.get(SESSION_ID);
  if (!session) return false;
  const now = Date.now();
  if (now > session.expires_at) {
    authSessions.delete(SESSION_ID);
    return false;
  }
  return true;
}

export function getSession(): AuthSession | null {
  const session = authSessions.get(SESSION_ID);
  if (!session) return null;
  const now = Date.now();
  if (now > session.expires_at) {
    authSessions.delete(SESSION_ID);
    return null;
  }
  return session;
}

export function clearSession(): void {
  authSessions.delete(SESSION_ID);
}

export function getTimeRemaining(): number {
  const session = getSession();
  if (!session) return 0;
  return Math.max(0, session.expires_at - Date.now());
}
