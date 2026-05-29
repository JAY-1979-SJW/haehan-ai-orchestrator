/**
 * POST /api/smartstore/chat
 * provider: "claude" | "gpt" 선택 가능. 단일 LLM → FastAPI 도구 직접 호출 → SSE 스트리밍.
 * 도구 정의는 @/lib/smartstore/tools 단일 소스에서 가져옵니다.
 */
import Anthropic from "@anthropic-ai/sdk";
import OpenAI    from "openai";
import { TOOL_DEFS, WRITE_TOOL_NAMES, toClaudeTools, toGptTools } from "@/lib/smartstore/tools";

const BACKEND  = process.env.BACKEND_URL ?? "http://localhost:8400";
const API_USER = process.env.NEXT_PUBLIC_API_USER ?? "owner";
const API_PASS = process.env.NEXT_PUBLIC_API_PASS ?? "haehan2024!";
const AUTH     = `Basic ${Buffer.from(`${API_USER}:${API_PASS}`).toString("base64")}`;

const CLAUDE_MODEL = "claude-haiku-4-5-20251001";
const GPT_MODEL    = "gpt-4o-mini";

const SYSTEM_PROMPT = `당신은 스마트스토어 셀러센터 AI 에이전트입니다.
사용자의 자연어 명령을 이해하고 적절한 도구를 호출하세요.
- 상품 등록·수정 등 쓰기 작업은 confirmed=true일 때만 실행합니다
- 조회·수집은 바로 실행합니다
- 결과가 많으면 핵심만 요약해서 한국어로 간결하게 답변합니다
- 도구 결과의 rows/items 배열은 건수와 주요 항목만 요약합니다`;

// ── FastAPI 도구 호출 프록시 ──────────────────────────────────────────────────
async function callTool(name: string, input: Record<string, unknown>): Promise<unknown> {
  const headers = { "Content-Type": "application/json", Authorization: AUTH };
  const qs = input.limit !== undefined ? `?limit=${input.limit}` : "";
  const G  = (path: string) => fetch(`${BACKEND}${path}`, { method: "GET", headers }).then((r) => r.json());
  const P  = (path: string, body?: unknown) =>
    fetch(`${BACKEND}${path}`, { method: "POST", headers, body: body !== undefined ? JSON.stringify(body) : undefined }).then((r) => r.json());

  switch (name) {
    case "list_products":         return G("/api/v1/smartstore/products");
    case "collect_products":      return P(`/api/v1/smartstore/products/collect${qs}`);
    case "list_orders":           return G("/api/v1/smartstore/orders");
    case "collect_orders":        return P(`/api/v1/smartstore/orders/collect${qs}`);
    case "list_settlements":      return G("/api/v1/smartstore/settlements");
    case "collect_settlements":   return P(`/api/v1/smartstore/settlements/collect${qs}`);
    case "list_reviews":          return G("/api/v1/smartstore/reviews");
    case "collect_reviews":       return P(`/api/v1/smartstore/reviews/collect${qs}`);
    case "list_stats":            return G("/api/v1/smartstore/stats");
    case "collect_stats":         return P("/api/v1/smartstore/stats/collect");
    case "open_seller_center":    return P(`/api/v1/smartstore/open?page_key=${input.page_key ?? "dashboard"}`);
    case "auto_register_product": return P("/api/v1/smartstore/products/auto-register", { data: input, dry_run: true });
    case "edit_product": {
      const { product_id, ...fields } = input;
      return P(`/api/v1/smartstore/products/${product_id}/edit`, { fields, dry_run: true });
    }
    case "generate_description":  return P("/api/v1/smartstore/description/ai-generate", { data: input.data, model: input.model ?? null });
    case "search_categories":     return G(`/api/v1/smartstore/categories/search?q=${encodeURIComponent(String(input.q))}`);
    case "popup_handle":          return P("/api/v1/smartstore/popup/handle");
    default:                      return { ok: false, error: `알 수 없는 도구: ${name}` };
  }
}

// ── SSE 헬퍼 ─────────────────────────────────────────────────────────────────
function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

// ── Claude 루프 ───────────────────────────────────────────────────────────────
async function runClaude(
  messages: Anthropic.MessageParam[],
  confirmed: boolean,
  push: (s: string) => void,
) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) { push(sse("error", { message: "ANTHROPIC_API_KEY 미설정" })); return; }

  const client = new Anthropic({ apiKey });
  const allTools = toClaudeTools();
  const tools = confirmed ? allTools : allTools.filter((t) => !WRITE_TOOL_NAMES.has(t.name));
  const history = [...messages];
  let step = 0;

  while (true) {
    const res = await client.messages.create({
      model: CLAUDE_MODEL, max_tokens: 2048,
      system: SYSTEM_PROMPT, tools, messages: history,
    });

    for (const b of res.content)
      if (b.type === "text" && b.text) push(sse("text", { text: b.text }));

    if (res.stop_reason !== "tool_use") break;

    const toolResults: Anthropic.ToolResultBlockParam[] = [];
    for (const b of res.content) {
      if (b.type !== "tool_use") continue;
      const isWrite = WRITE_TOOL_NAMES.has(b.name);
      if (isWrite && !confirmed) {
        push(sse("confirm_required", { tool: b.name, inputs: b.input,
          message: `'${(b.input as Record<string, unknown>).name ?? b.name}' 작업에 승인이 필요합니다.` }));
        return;
      }
      step++;
      push(sse("step_start", { step, tool: b.name, inputs: b.input, write: isWrite }));
      let result: unknown;
      try { result = await callTool(b.name, b.input as Record<string, unknown>); }
      catch (e) { result = { ok: false, error: String(e) }; }
      push(sse("step_done", { step, tool: b.name, ok: (result as { ok?: boolean }).ok !== false, result }));
      toolResults.push({ type: "tool_result", tool_use_id: b.id, content: JSON.stringify(result) });
    }
    history.push({ role: "assistant", content: res.content });
    history.push({ role: "user",      content: toolResults });
  }
  push(sse("done", { steps: step }));
}

// ── GPT 루프 ─────────────────────────────────────────────────────────────────
async function runGPT(
  messages: Array<{ role: "user" | "assistant" | "system"; content: string }>,
  confirmed: boolean,
  push: (s: string) => void,
) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) { push(sse("error", { message: "OPENAI_API_KEY 미설정" })); return; }

  const client = new OpenAI({ apiKey });
  const allTools = toGptTools();
  const tools = confirmed ? allTools : allTools.filter((t) => {
    const n = (t as { function?: { name?: string } }).function?.name ?? "";
    return !WRITE_TOOL_NAMES.has(n);
  });
  const history: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: "system", content: SYSTEM_PROMPT }, ...messages,
  ];
  let step = 0;

  while (true) {
    const res = await client.chat.completions.create({
      model: GPT_MODEL, max_tokens: 2048, tools, tool_choice: "auto", messages: history,
    });
    const msg = res.choices[0].message;
    if (msg.content) push(sse("text", { text: msg.content }));
    if (!msg.tool_calls?.length) break;

    const toolResults: OpenAI.Chat.ChatCompletionToolMessageParam[] = [];
    for (const tc of msg.tool_calls) {
      const fn      = (tc as { id: string; function: { name: string; arguments: string } }).function;
      const name    = fn.name;
      const input   = JSON.parse(fn.arguments || "{}") as Record<string, unknown>;
      const isWrite = WRITE_TOOL_NAMES.has(name);
      if (isWrite && !confirmed) {
        push(sse("confirm_required", { tool: name, inputs: input,
          message: `'${input.name ?? name}' 작업에 승인이 필요합니다.` }));
        return;
      }
      step++;
      push(sse("step_start", { step, tool: name, inputs: input, write: isWrite }));
      let result: unknown;
      try { result = await callTool(name, input); }
      catch (e) { result = { ok: false, error: String(e) }; }
      push(sse("step_done", { step, tool: name, ok: (result as { ok?: boolean }).ok !== false, result }));
      toolResults.push({ role: "tool", tool_call_id: tc.id, content: JSON.stringify(result) });
    }
    history.push(msg);
    history.push(...toolResults);
  }
  push(sse("done", { steps: step }));
}

// ── Route Handler ─────────────────────────────────────────────────────────────
export async function POST(req: Request) {
  const { messages, confirmed = false, provider = "claude" } = await req.json() as {
    messages: Array<{ role: "user" | "assistant"; content: string }>;
    confirmed?: boolean;
    provider?: "claude" | "gpt";
  };

  const encoder = new TextEncoder();
  const stream  = new ReadableStream({
    async start(controller) {
      const push = (chunk: string) => controller.enqueue(encoder.encode(chunk));
      try {
        if (provider === "gpt") {
          await runGPT(messages, confirmed, push);
        } else {
          await runClaude(
            messages.map((m) => ({ role: m.role, content: m.content } as Anthropic.MessageParam)),
            confirmed, push,
          );
        }
      } catch (e) {
        push(sse("error", { message: String(e) }));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" },
  });
}

// TOOL_DEFS re-export (필요 시 다른 라우터에서 사용)
export { TOOL_DEFS };
