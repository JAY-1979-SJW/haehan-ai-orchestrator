/** POST /api/naver/marketing-ops/neighbors/refresh — CDP로 이웃 목록 재조회 프록시 */
const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8401";
const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

export async function POST() {
  try {
    const upstream = await fetch(`${BACKEND}/api/v1/naver/marketing-ops/neighbors/refresh`, {
      method: "POST",
      headers: { Authorization: AUTH },
    });
    const data = await upstream.json();
    return Response.json(data, { status: upstream.status });
  } catch {
    return Response.json({ ok: false, error: "백엔드 서버에 연결할 수 없습니다." }, { status: 502 });
  }
}
