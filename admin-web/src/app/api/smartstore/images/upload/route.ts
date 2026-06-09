/**
 * POST /api/smartstore/images/upload — 이미지 파일을 FastAPI 서버에 업로드 후 경로 반환
 * 웹 HTML <input type="file"> → FormData → FastAPI /api/v1/smartstore/images/upload
 */
const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8400";
const API_USER = process.env.API_USER ?? "owner";
const API_PASS = process.env.API_PASS ?? "";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

export async function POST(req: Request) {
  const formData = await req.formData();

  const upstream = await fetch(`${BACKEND}/api/v1/smartstore/images/upload`, {
    method: "POST",
    headers: { Authorization: AUTH },
    body: formData,
  });

  const json = await upstream.json().catch(() => ({ ok: false, paths: [] }));
  return Response.json(json, { status: upstream.ok ? 200 : 502 });
}
