const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8401";
const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

export async function POST(req: Request) {
  const body = await req.json();
  const r = await fetch(`${BACKEND}/api/v1/google/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: AUTH },
    body: JSON.stringify(body),
  }).catch(() => null);

  if (!r || !r.ok) {
    return Response.json({ reply: "서버에 연결할 수 없습니다." }, { status: 200 });
  }
  return Response.json(await r.json());
}
