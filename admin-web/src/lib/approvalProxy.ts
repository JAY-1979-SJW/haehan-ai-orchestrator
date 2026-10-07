/**
 * 승인 발급 경로의 프록시 증명 (R2d-2 P0c, 설계서 §13).
 *
 * `approvals/<id>/(approve|reject|revoke)` 요청에만 HMAC-SHA256 증명 `X-Approval-Proxy: <ts>.<nonce>.<hex>` 를 붙인다.
 * 서명 문자열은 백엔드 `ai_orchestrator/gates/human_session.py` 의 canonical() 과 글자 하나까지 같아야 한다 —
 * 교차 언어 시험(tests/test_human_session_p0c.py)이 node 로 이 파일을 실행해 값을 대조한다.
 * Node 의 type stripping 으로 바로 실행할 수 있도록 enum·namespace 등 지우기 불가능한 문법은 쓰지 않는다.
 */
import { createHash, createHmac, randomBytes } from "node:crypto";

const PREFIX = "HAEHAN-APPROVAL-V1";
const ISSUE_PATH = /(^|\/)approvals\/[^/]+\/(approve|reject|revoke)$/;

export const APPROVAL_HEADER = "X-Approval-Proxy";

/** 백엔드로 보낼 경로(앞 슬래시 포함, 쿼리 제외)가 승인 발급 경로인가. */
export function isApprovalIssuePath(upstreamPath: string): boolean {
  return ISSUE_PATH.test(upstreamPath);
}

function sha256Hex(data: Uint8Array | string): string {
  return createHash("sha256").update(data).digest("hex");
}

export function canonical(method: string, path: string, ts: string, nonce: string, body: Uint8Array, bearer: string): string {
  return [PREFIX, method.toUpperCase(), path, ts, nonce, sha256Hex(body), sha256Hex(bearer)].join("\n");
}

export function signApproval(args: {
  secret: string;
  method: string;
  path: string;
  body: Uint8Array;
  bearer: string;
  nowSeconds?: number;
  nonce?: string;
}): string {
  const ts = String(Math.floor(args.nowSeconds ?? Date.now() / 1000));
  const nonce = args.nonce ?? randomBytes(16).toString("hex");
  const msg = canonical(args.method, args.path, ts, nonce, args.body, args.bearer);
  const hex = createHmac("sha256", args.secret).update(msg, "utf8").digest("hex");
  return `${ts}.${nonce}.${hex}`;
}

/** 브라우저 same-origin 요청인가(다른 사이트의 요청 차단). Origin 호스트 = 요청 호스트, Fetch-Metadata same-origin, JSON. */
export function isSameOriginJson(headers: { get(name: string): string | null }): boolean {
  const host = headers.get("host") ?? "";
  const origin = headers.get("origin") ?? "";
  let originHost = "";
  try {
    originHost = new URL(origin).host;
  } catch {
    return false;
  }
  const site = headers.get("sec-fetch-site");
  const type = (headers.get("content-type") ?? "").toLowerCase();
  return originHost === host && site === "same-origin" && type.startsWith("application/json");
}
