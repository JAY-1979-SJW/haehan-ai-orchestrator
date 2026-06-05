const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8401";
const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

// 비동기 브라우저 작업(job) 상태 폴링 프록시 — UniversalChat이 로그인 후 결과를 가져온다.
export async function GET(_req: Request, ctx: { params: { id: string } }) {
  const { id } = ctx.params;
  try {
    const r = await fetch(`${BACKEND}/api/v1/agent-ai/task/${encodeURIComponent(id)}`, {
      headers: {
        Authorization:    AUTH,
        "X-Agent-Id":     "web-ui",
        "X-Device-Token": API_PASS,
      },
      cache: "no-store",
    });
    if (!r.ok) return Response.json({ status: "unknown" });
    return Response.json(await r.json());
  } catch {
    return Response.json({ status: "pending" });
  }
}
