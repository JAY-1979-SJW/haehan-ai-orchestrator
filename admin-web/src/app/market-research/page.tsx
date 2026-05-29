import { readFile } from "fs/promises";
import path from "path";
import { PageShell } from "@/components/ui/PageShell";
import MarketResearchClient from "./MarketResearchClient";

export const metadata = {
  title: "Market Research | Haehan AI Admin",
};

async function readJsonFile(filePath: string) {
  try {
    return JSON.parse(await readFile(filePath, "utf-8"));
  } catch (error) {
    return { error: error instanceof Error ? error.message : "unknown_error" };
  }
}

async function readTextFile(filePath: string) {
  try {
    return await readFile(filePath, "utf-8");
  } catch {
    return "";
  }
}

export default async function MarketResearchPage() {
  const repoRoot = path.resolve(process.cwd(), "..");
  const latestPath = path.join(repoRoot, "data", "youtube_market_research_latest.json");
  const parsed = await readJsonFile(latestPath);
  const data = parsed.error ? null : parsed;
  const markdownPath =
    data?.markdown_report && typeof data.markdown_report === "string"
      ? data.markdown_report
      : "";
  const markdown = markdownPath ? await readTextFile(markdownPath) : "";

  return (
    <PageShell
      title="Market Research"
      description="YouTube keyword, video, comment, and transcript signal reports"
      chatDomain="market"
    >
      <MarketResearchClient
        data={data}
        markdown={markdown}
        error={parsed.error ? `Latest report unavailable: ${parsed.error}` : undefined}
      />
    </PageShell>
  );
}
