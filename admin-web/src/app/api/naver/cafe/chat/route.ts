/** POST /api/naver/cafe/chat — FastAPI 카페 채팅 SSE 프록시 */
const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8401";
const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

export async function POST(req: Request) {
  const body = await req.json();

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/v1/naver-cafe/chat`, {
      method:  "POST",
      headers: { "Content-Type": "application/json", Authorization: AUTH },
      body:    JSON.stringify(body),
    });
  } catch {
    return new Response(
      `event: error\ndata: ${JSON.stringify({ message: "백엔드 서버에 연결할 수 없습니다." })}\n\n`,
      { headers: { "Content-Type": "text/event-stream" } },
    );
  }

  if (!upstream.ok) {
    const text = await upstream.text();
    return new Response(
      `event: error\ndata: ${JSON.stringify({ message: `backend ${upstream.status}: ${text}` })}\n\n`,
      { headers: { "Content-Type": "text/event-stream" } },
    );
  }

  return new Response(upstream.body, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" },
  });
}
