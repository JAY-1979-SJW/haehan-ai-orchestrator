/**파일 정리 승인 토큰 관리.*/

const APPROVAL_TOKEN_PREFIX = 'user-approved-cleanup';
const APPROVAL_TOKEN_STORAGE_KEY = 'fileMapApprovalToken';
const APPROVAL_TIMESTAMP_KEY = 'fileMapApprovalTimestamp';
const APPROVAL_TOKEN_VALIDITY_MS = 15 * 60 * 1000; // 15분

/**
 * UUID v4 생성 (crypto.randomUUID 또는 fallback).
 */
function generateUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  // fallback: timestamp + random (acceptable for session ID)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * 새로운 승인 토큰 생성.
 */
export function generateApprovalToken(): string {
  const id = generateUUID();
  const token = `${APPROVAL_TOKEN_PREFIX}-${id}`;

  // localStorage에 저장 (세션용)
  localStorage.setItem(APPROVAL_TOKEN_STORAGE_KEY, token);
  localStorage.setItem(APPROVAL_TIMESTAMP_KEY, Date.now().toString());

  return token;
}

/**
 * 저장된 승인 토큰 검증 (15분 유효).
 */
export function validateApprovalToken(token: string): boolean {
  if (!token || !token.startsWith(APPROVAL_TOKEN_PREFIX)) {
    return false;
  }

  const stored = localStorage.getItem(APPROVAL_TOKEN_STORAGE_KEY);
  if (!stored || stored !== token) {
    return false;
  }

  const timestamp = localStorage.getItem(APPROVAL_TIMESTAMP_KEY);
  if (!timestamp) {
    return false;
  }

  const elapsed = Date.now() - parseInt(timestamp, 10);
  return elapsed < APPROVAL_TOKEN_VALIDITY_MS;
}

/**
 * 저장된 승인 토큰 가져오기.
 */
export function getStoredApprovalToken(): string | null {
  const token = localStorage.getItem(APPROVAL_TOKEN_STORAGE_KEY);
  if (!token) {
    return null;
  }

  // 유효성 재검증
  if (validateApprovalToken(token)) {
    return token;
  }

  // 만료된 토큰 삭제
  clearApprovalToken();
  return null;
}

/**
 * 승인 토큰 삭제.
 */
export function clearApprovalToken(): void {
  localStorage.removeItem(APPROVAL_TOKEN_STORAGE_KEY);
  localStorage.removeItem(APPROVAL_TIMESTAMP_KEY);
}

/**
 * 토큰 남은 유효 시간 (초 단위, 음수면 만료됨).
 */
export function getTokenRemainingTime(): number {
  const timestamp = localStorage.getItem(APPROVAL_TIMESTAMP_KEY);
  if (!timestamp) {
    return -1;
  }

  const elapsed = Date.now() - parseInt(timestamp, 10);
  const remaining = APPROVAL_TOKEN_VALIDITY_MS - elapsed;
  return Math.max(-1, Math.ceil(remaining / 1000));
}
