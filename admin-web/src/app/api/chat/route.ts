const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8401";
const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

export async function POST(req: Request) {
  const { message, domain, session_id } = await req.json();

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/v1/agent-ai/chat`, {
      method: "POST",
      headers: {
        "Content-Type":  "application/json",
        Authorization:   AUTH,
        "X-Agent-Id":    "web-ui",
        "X-Device-Token": API_PASS,
      },
      body: JSON.stringify({ message, session_id, client_mode: "SERVER_PROXY", domain }),
    });
  } catch {
    const errMsg = JSON.stringify({ message: "백엔드 서버에 연결할 수 없습니다." });
    return new Response(
      `event: error\ndata: ${errMsg}\n\nevent: done\ndata: {}\n\n`,
      { headers: { "Content-Type": "text/event-stream" } },
    );
  }

  if (!upstream.ok) {
    const errMsg = JSON.stringify({ message: `서버 오류 (${upstream.status})` });
    return new Response(
      `event: error\ndata: ${errMsg}\n\nevent: done\ndata: {}\n\n`,
      { headers: { "Content-Type": "text/event-stream" } },
    );
  }

  const d = await upstream.json() as { ok: boolean; text?: string; error_code?: string; user_message_kr?: string };

  const text = d.ok
    ? (d.text || "처리 완료")
    : (d.user_message_kr || d.error_code || "처리 중 오류가 발생했습니다.");

  const sse =
    `event: text\ndata: ${JSON.stringify({ text })}\n\n` +
    `event: done\ndata: ${JSON.stringify({ domain })}\n\n`;

  return new Response(sse, {
    headers: {
      "Content-Type":  "text/event-stream",
      "Cache-Control": "no-cache",
      Connection:      "keep-alive",
    },
  });
}
