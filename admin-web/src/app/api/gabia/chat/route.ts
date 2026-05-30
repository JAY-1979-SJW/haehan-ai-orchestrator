const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8401";
const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

export async function POST(req: Request) {
  const body = await req.json();
  const upstream = await fetch(`${BACKEND}/api/v1/gabia/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: AUTH },
    body: JSON.stringify(body),
  });
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
