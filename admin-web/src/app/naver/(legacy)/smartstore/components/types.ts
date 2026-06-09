// ── 메시지 타입 ──────────────────────────────────────────────────────────────
export type StepItem = {
  step: number;
  tool: string;
  write: boolean;
  status: "running" | "ok" | "fail";
  detail?: string;
};

export type AiBlock =
  | { type: "text";    text: string }
  | { type: "step";    item: StepItem }
  | { type: "confirm"; tool: string; inputs: Record<string, unknown>; message: string }
  | { type: "done";    steps: number }
  | { type: "error";   message: string };

export type ActionChip = { label: string; prompt: string };

export type Message =
  | { role: "user";      text: string }
  | { role: "assistant"; blocks: AiBlock[]; streaming: boolean; actions?: ActionChip[] };

// ── Anthropic MessageParam 호환 타입 ─────────────────────────────────────────
export type ChatMessage = { role: "user" | "assistant"; content: string };
