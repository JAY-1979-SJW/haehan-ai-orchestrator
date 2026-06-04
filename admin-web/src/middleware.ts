import { NextRequest, NextResponse } from "next/server";
import { jwtVerify } from "jose";

const TOKEN_COOKIE = "haehan_ai_token";

// 인증 없이 접근 가능한 공개 경로
const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/about",
  "/api/auth",
  "/api/v1/users/signup",
  "/api/v1/users/login",
  // 공개 문의 접수(비로그인). GET/PATCH 는 백엔드 require_role 이 보호하므로 안전.
  "/api/proxy/api/v1/inquiries",
  "/api/v1/inquiries",
];

function isPublic(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

function isNextInternal(pathname: string): boolean {
  return (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/icons") ||
    pathname.startsWith("/images") ||
    pathname === "/"  // 홈(대시보드)은 공개 — 세션 위젯은 클라이언트에서 처리
  );
}

function redirectToLogin(req: NextRequest): NextResponse {
  const { pathname, search } = req.nextUrl;
  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("returnTo", pathname + search);
  return NextResponse.redirect(loginUrl);
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Next.js 내부 경로, 정적 파일 — 통과
  if (isNextInternal(pathname)) return NextResponse.next();

  // OWNER_MODE=true 환경 (로컬 개발 / Electron owner 모드) — 미들웨어 비활성
  if (process.env.OWNER_MODE === "true") return NextResponse.next();

  // 공개 경로 — 통과
  if (isPublic(pathname)) return NextResponse.next();

  // JWT 쿠키 확인
  const token = req.cookies.get(TOKEN_COOKIE)?.value;
  if (!token) return redirectToLogin(req);

  // JWT 서명 검증 (jose — Edge Runtime 호환)
  // JWT_SECRET 미설정 시 서명 검증을 건너뛰고 쿠키 존재만 확인 (개발 편의)
  const secret = process.env.JWT_SECRET;
  if (secret) {
    try {
      await jwtVerify(token, new TextEncoder().encode(secret));
    } catch {
      // 서명 불일치 또는 만료 → 재로그인
      return redirectToLogin(req);
    }
  }

  // 관리자 전용 경로 — JWT payload에 role 미포함(서버 DB 조회 필요)이므로
  // API 레벨에서 requireBackendRole()이 보호하며 클라이언트 PageShell이 UI를 제한함.
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
