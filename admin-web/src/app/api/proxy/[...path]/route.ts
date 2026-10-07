/**
 * 서버사이드 FastAPI 프록시 — 클라이언트 번들에 자격증명 노출 없이 모든 API 호출 처리.
 *
 * 클라이언트: fetch('/api/proxy/api/v1/health')
 * 서버→FastAPI: fetch('http://localhost:8401/api/v1/health', { Authorization: Basic ... })
 *
 * SSE(text/event-stream), JSON, 바이너리 모두 스트리밍 패스스루.
 */
import { NextRequest, NextResponse } from "next/server";

import { APPROVAL_HEADER, isApprovalIssuePath, isSameOriginJson, signApproval } from "@/lib/approvalProxy";

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

function jsonError(status: number, detail: string): NextResponse {
  return NextResponse.json({ detail }, { status });
}

/**
 * 승인 발급 경로(approvals/<id>/approve|reject|revoke) 전용 헤더 — 사람이 화면에서 누른 요청임을 증명한다.
 * 클라이언트가 보낸 Authorization 은 무시하고 로그인 쿠키(JWT)만 쓰며, 서버 Basic 은 붙이지 않는다.
 */
function buildApprovalHeaders(req: NextRequest, upstreamPath: string, body: Uint8Array, secret: string): HeadersInit {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const cookieTok = req.cookies.get("haehan_ai_token")?.value;
  const bearer = cookieTok ? decodeURIComponent(cookieTok) : "";
  if (bearer) headers["Authorization"] = `Bearer ${bearer}`;
  headers[APPROVAL_HEADER] = signApproval({ secret, method: req.method, path: upstreamPath, body, bearer });
  return headers;
}

async function proxy(req: NextRequest, segments: string[]): Promise<NextResponse | Response> {
  const path = segments.join("/");
  const search = req.nextUrl.search;
  const upstreamUrl = `${BACKEND}/${path}${search}`;
  const issuing = isApprovalIssuePath(`/${path}`);

  let body: BodyInit | null = null;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.arrayBuffer();
  }

  let headers = buildUpstreamHeaders(req);
  if (issuing) {
    const secret = (process.env.APPROVAL_PROXY_SECRET ?? "").trim();
    if (!secret) return jsonError(503, "승인 발급이 구성되지 않았습니다");
    if (req.method !== "POST" || !isSameOriginJson(req.headers)) return jsonError(403, "관리 화면에서만 승인할 수 있습니다");
    headers = buildApprovalHeaders(req, `/${path}`, new Uint8Array(body ? (body as ArrayBuffer) : new ArrayBuffer(0)), secret);
  }

  const upstream = await fetch(upstreamUrl, {
    method: req.method,
    headers,
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
