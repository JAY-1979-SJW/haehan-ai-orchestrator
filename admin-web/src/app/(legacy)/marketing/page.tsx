import { readFile } from "fs/promises";
import path from "path";
import { PageShell } from "@/components/ui/PageShell";
import MarketingClient from "./MarketingClient";

export const metadata = {
  title: "마케팅 자료 | Haehan AI Admin",
};

async function readJsonFile(filePath: string) {
  try {
    return JSON.parse(await readFile(filePath, "utf-8"));
  } catch (error) {
    return { error: error instanceof Error ? error.message : "unknown_error" };
  }
}

export default async function MarketingPage() {
  const repoRoot = path.resolve(process.cwd(), "..");
  const latestPath = path.join(repoRoot, "data", "marketing", "summary_latest.json");
  const parsed = await readJsonFile(latestPath);
  const data = parsed.error ? null : parsed;

  return (
    <PageShell
      title="마케팅 자료"
      description="건설공무 카페·YouTube 조사 기반 전략·콘텐츠 소재·홍보 문구"
      chatDomain="marketing"
    >
      <MarketingClient
        data={data}
        error={parsed.error ? `자료를 불러오지 못했습니다: ${parsed.error}` : undefined}
      />
    </PageShell>
  );
}
