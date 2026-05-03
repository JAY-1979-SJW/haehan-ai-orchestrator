/**파일 정리 승인 토큰 검증 (서버 측).*/

const APPROVAL_TOKEN_PREFIX = 'user-approved-cleanup-';

/**
 * 승인 토큰 검증 (UUID suffix 포함).
 *
 * 클라이언트가 발급한 토큰의 형식 검증:
 * prefix: 'user-approved-cleanup-'
 * suffix: UUID v4 형식
 *
 * @param token 검증할 토큰
 * @returns 토큰이 유효한 형식인 경우 true
 */
export function validateApprovalToken(token: string): boolean {
  if (!token || !token.startsWith(APPROVAL_TOKEN_PREFIX)) {
    return false;
  }

  const suffix = token.slice(APPROVAL_TOKEN_PREFIX.length);
  const uuidRegex =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  return uuidRegex.test(suffix);
}
