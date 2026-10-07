/**
 * 서버사이드 FastAPI 프록시 — 클라이언트 번들에 자격증명 노출 없이 모든 API 호출 처리.
 *
 * 클라이언트: fetch('/api/proxy/api/v1/health')
 * 서버→FastAPI: fetch('http://localhost:8401/api/v1/health', { Authorization: Basic ... })
 *
 * SSE(text/event-stream), JSON, 바이너리 모두 스트리밍 패스스루.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = (
  process.env.API_BASE_URL ??
  process.env.BACKEND_URL ??
  "http://localhost:8401"
).replace(/\/$/, "");

const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";

const AUTH = API_PASS
  ? `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`
  : "";

// 클라이언트에서 그대로 전달할 요청 헤더 목록
const FORWARD_REQUEST_HEADERS = new Set([
  "content-type",
  "accept",
  "cache-control",
  "x-request-id",
  "x-device-token",
  "x-haehan-desktop", // 데스크톱 첫 실행 등록/자동 세션 요청 표지(백엔드가 요구)
  "authorization", // 사용자 JWT(Bearer) 전달 — user-auth(getMe/login 등). 미포함 시 서버 Basic 주입.
]);

// 클라이언트에 그대로 전달할 응답 헤더 목록
const FORWARD_RESPONSE_HEADERS = new Set([
  "content-type",
  "cache-control",
  "x-request-id",
  "transfer-encoding",
]);

function buildUpstreamHeaders(req: NextRequest): HeadersInit {
  const headers: Record<string, string> = {};
  req.headers.forEach((value, key) => {
    if (FORWARD_REQUEST_HEADERS.has(key.toLowerCase())) {
      headers[key] = value;
    }
  });
  // 인증 우선순위: ① 클라이언트 Authorization(Bearer) → ② haehan_ai_token 쿠키(사용자 JWT)
  // → ③ 서버 Basic. self-contained 앱은 ②(webview_preload 가 심는 쿠키)로 JWT 보호
  // 엔드포인트(inbox/logs/ops/tasks 등)를 인증한다. 미설정 시에만 서버 Basic 폴백.
  const hasClientAuth = "Authorization" in headers || "authorization" in headers;
  if (!hasClientAuth) {
    const cookieTok = req.cookies.get("haehan_ai_token")?.value;
    if (cookieTok) {
      headers["Authorization"] = `Bearer ${decodeURIComponent(cookieTok)}`;
    } else if (AUTH) {
      headers["Authorization"] = AUTH;
    }
  }
  return headers;
}

function buildResponseHeaders(upstream: Response): HeadersInit {
  const headers: Record<string, string> = {};
  upstream.headers.forEach((value, key) => {
    if (FORWARD_RESPONSE_HEADERS.has(key.toLowerCase())) {
      headers[key] = value;
    }
  });
  return headers;
}

async function proxy(req: NextRequest, segments: string[]): Promise<NextResponse | Response> {
  const path = segments.join("/");
  const search = req.nextUrl.search;
  const upstreamUrl = `${BACKEND}/${path}${search}`;

  let body: BodyInit | null = null;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.arrayBuffer();
  }

  const upstream = await fetch(upstreamUrl, {
    method: req.method,
    headers: buildUpstreamHeaders(req),
    body: body ?? undefined,
    // @ts-expect-error — Node.js fetch 확장
    duplex: "half",
  });

  const responseHeaders = buildResponseHeaders(upstream);
  const contentType = upstream.headers.get("content-type") ?? "";

  // SSE — body를 그대로 패스스루
  if (contentType.includes("text/event-stream")) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  }

  // 일반 응답 (204 No Content 등 body=null 포함)
  const data = await upstream.arrayBuffer();
  return new NextResponse(data, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxy(req, path);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxy(req, path);
}

export async function PUT(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxy(req, path);
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxy(req, path);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxy(req, path);
}
