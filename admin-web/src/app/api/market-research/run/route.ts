import { execFile } from "child_process";
import path from "path";
import { promisify } from "util";
import { NextResponse } from "next/server";

const execFileAsync = promisify(execFile);

const ALLOWED_TOPICS = new Set([
  "smartstore",
  "purchase_agency",
  "shopping_mall",
  "commerce_marketing",
  "ai_work_automation",
]);

type RunRequest = {
  topic?: string;
  perKeywordLimit?: number;
  comments?: number;
  commentPages?: number;
  collectTranscripts?: boolean;
  transcriptVideos?: number;
};

function clampNumber(value: unknown, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, Math.trunc(parsed)));
}

export async function POST(request: Request) {
  let body: RunRequest = {};
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, reason: "invalid_json" }, { status: 400 });
  }

  const topic = String(body.topic || "smartstore");
  if (!ALLOWED_TOPICS.has(topic)) {
    return NextResponse.json({ ok: false, reason: "unsupported_topic" }, { status: 400 });
  }

  const perKeywordLimit = clampNumber(body.perKeywordLimit, 10, 1, 25);
  const comments = clampNumber(body.comments, 100, 1, 100);
  const commentPages = clampNumber(body.commentPages, 3, 1, 10);
  const transcriptVideos = clampNumber(body.transcriptVideos, 5, 0, 10);
  const collectTranscripts = Boolean(body.collectTranscripts);

  const repoRoot = process.env.MARKET_RESEARCH_REPO_ROOT || process.cwd();
  const args = [
    path.join("scripts", "browser", "cdp_cli.py"),
    "google",
    "youtube",
    "research-run",
    `--topic=${topic}`,
    "--auto-keywords",
    `--per-keyword-limit=${perKeywordLimit}`,
    "--collect-comments=true",
    `--max-comments=${comments}`,
    `--max-comment-pages=${commentPages}`,
    `--collect-transcripts=${collectTranscripts ? "true" : "false"}`,
    `--max-transcript-videos=${transcriptVideos}`,
  ];

  try {
    const result = await execFileAsync("python", args, {
      cwd: repoRoot,
      timeout: 180_000,
      windowsHide: true,
      maxBuffer: 1024 * 1024,
    });
    return NextResponse.json({
      ok: true,
      command: ["python", ...args].join(" "),
      stdout: result.stdout,
      stderr: result.stderr,
      latestJson: path.join(repoRoot, "data", "youtube_market_research_latest.json"),
    });
  } catch (error) {
    const err = error as { stdout?: string; stderr?: string; message?: string; code?: number | string };
    return NextResponse.json(
      {
        ok: false,
        reason: "market_research_run_failed",
        command: ["python", ...args].join(" "),
        exitCode: err.code ?? null,
        stdout: err.stdout ?? "",
        stderr: err.stderr ?? "",
        error: err.message ?? "unknown_error",
      },
      { status: 500 },
    );
  }
}
