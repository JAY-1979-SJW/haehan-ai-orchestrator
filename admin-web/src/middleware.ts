import { NextRequest, NextResponse } from "next/server";

const TOKEN_COOKIE = "haehan_ai_token";

// 인증 없이 접근 가능한 공개 경로
const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/about",
  "/api/auth",
  "/api/v1/users/signup",
  "/api/v1/users/login",
];

// 관리자(admin/owner) 전용 경로
const ADMIN_PATHS = [
  "/ops",
  "/admin",
  "/naver/session",
  "/assistant/approval",
  "/assistant/logs",
  "/assistant/deployment",
  "/assistant/storage",
  "/browser-approvals",
];

function isPublic(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

function isNextInternal(pathname: string): boolean {
  return pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/icons") ||
    pathname.startsWith("/images") ||
    pathname === "/";  // 홈(대시보드)은 공개 — 세션 위젯은 클라이언트에서 처리
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Next.js 내부 경로, 정적 파일 — 통과
  if (isNextInternal(pathname)) return NextResponse.next();

  // OWNER_MODE=true 환경 (로컬 개발 / Electron owner 모드) — 미들웨어 비활성
  if (process.env.OWNER_MODE === "true") return NextResponse.next();

  // 공개 경로 — 통과
  if (isPublic(pathname)) return NextResponse.next();

  // JWT 쿠키 확인
  const token = req.cookies.get(TOKEN_COOKIE)?.value;

  if (!token) {
    // 미로그인 → /login?returnTo=<원래경로>
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("returnTo", pathname + req.nextUrl.search);
    return NextResponse.redirect(loginUrl);
  }

  // TODO: JWT 서명 검증 (JWT_SECRET을 Edge Runtime에서 읽을 수 있을 때)
  // 현재는 쿠키 존재 여부만 확인 — 실제 토큰 유효성은 FastAPI에서 검증
  // const payload = verifyJwt(token);
  // if (!payload) return NextResponse.redirect(new URL("/login", req.url));

  // 관리자 전용 경로 — 쿠키에서 role 확인 불가능 (httpOnly 아닌 경우 JS에서 설정하므로
  // role 정보가 없음). 클라이언트 측 role 체크는 PageShell authRequired="admin"으로 처리.

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * 아래를 제외한 모든 경로에 미들웨어 적용:
     * - _next/static (정적 파일)
     * - _next/image (이미지 최적화)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon\\.ico).*)",
  ],
};
