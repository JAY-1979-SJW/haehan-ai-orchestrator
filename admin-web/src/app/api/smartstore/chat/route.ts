/**
 * POST /api/smartstore/chat  — FastAPI 채팅 엔드포인트 SSE 프록시
 * LLM 호출·도구 실행은 FastAPI에서 처리. API 키는 서버 .env 한 곳에서만 관리.
 */
const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8400";
const API_USER = process.env.NEXT_PUBLIC_API_USER ?? "owner";
const API_PASS = process.env.NEXT_PUBLIC_API_PASS ?? "haehan2024!";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

export async function POST(req: Request) {
  const body = await req.json();

  const upstream = await fetch(`${BACKEND}/api/v1/smartstore/chat`, {
    method:  "POST",
    headers: { "Content-Type": "application/json", Authorization: AUTH },
    body:    JSON.stringify(body),
  });

  if (!upstream.ok) {
    const text = await upstream.text();
    return new Response(
      `event: error\ndata: ${JSON.stringify({ message: `backend ${upstream.status}: ${text}` })}\n\n`,
      { headers: { "Content-Type": "text/event-stream" } },
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type":  "text/event-stream",
      "Cache-Control": "no-cache",
      Connection:      "keep-alive",
    },
  });
}
