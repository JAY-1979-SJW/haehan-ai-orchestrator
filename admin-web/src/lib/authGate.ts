// 미들웨어의 "로그인 안 된 요청" 처리 방식을 정하는 순수 함수(의존성 없음 → node:test 로 시험).
//
// 배경(2026-10-08 실측): 세션 쿠키가 없는 상태에서 화면이 /api/proxy/... 를 fetch 하면
// 미들웨어가 /setup(또는 /login) HTML 로 307 리다이렉트했고, fetch 가 그걸 따라가 200 HTML 을 받아
// `res.json()` 이 "Unexpected token '<'" 로 터졌다(잡히지 않은 pageerror). API 요청은 HTML 이동이 아니라
// 401 JSON 으로 답해야 호출자가 정상적으로 "로그인 필요"를 처리한다.

/** 화면 이동이 아니라 데이터(JSON)를 기대하는 경로인가 */
export function isApiRequestPath(pathname: string): boolean {
  return pathname === "/api" || pathname.startsWith("/api/");
}

export type UnauthenticatedAction =
  | { kind: "json401"; body: { detail: string } }
  | { kind: "redirect"; to: "/setup" | "/login" };

/** 인증 실패(쿠키 없음·서명 불일치) 시 무엇을 돌려줄지 */
export function unauthenticatedAction(pathname: string, desktop: boolean): UnauthenticatedAction {
  if (isApiRequestPath(pathname)) {
    return { kind: "json401", body: { detail: "로그인이 필요합니다." } };
  }
  return { kind: "redirect", to: desktop ? "/setup" : "/login" };
}
