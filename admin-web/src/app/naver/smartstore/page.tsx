/** /naver/smartstore — 스마트스토어 관리 (read-only catalog + 제출 이력) */
import { readFile } from "fs/promises";
import path from "path";
import { PageShell } from "@/components/ui/PageShell";
import SmartStoreClient from "./SmartStoreClient";

export interface ActionItem {
  action_id: string;
  label: string;
  module: string;
  risk: "read" | "prepare" | "submit";
  status: string;
  required_fields?: string[];
  optional_fields?: string[];
}

export interface CatalogSection {
  name: string;
  actions: ActionItem[];
  summary: { total: number; implemented: number; approval_gated: number };
}

export interface ActionCatalog {
  generated_at: string;
  site_id: string;
  contract: Record<string, string>;
  sections: CatalogSection[];
}

export interface SubmitRecord {
  workflow?: string;
  dry_run?: boolean;
  generated_at?: string;
  [key: string]: unknown;
}

export default async function SmartStorePage() {
  const repoRoot = path.resolve(process.cwd(), "..");
  const dataDir = path.join(repoRoot, "data");

  let catalog: ActionCatalog | null = null;
  let submit: SubmitRecord | null = null;
  let catalogError: string | null = null;
  let submitError: string | null = null;

  try {
    const raw = await readFile(path.join(dataDir, "smartstore_action_catalog_latest.json"), "utf-8");
    catalog = JSON.parse(raw) as ActionCatalog;
  } catch (e) {
    catalogError = e instanceof Error ? e.message : String(e);
  }

  try {
    const raw = await readFile(path.join(dataDir, "smartstore_submit_latest.json"), "utf-8");
    submit = JSON.parse(raw) as SubmitRecord;
  } catch (e) {
    submitError = e instanceof Error ? e.message : String(e);
  }

  return (
    <PageShell title="스마트스토어 관리" description="네이버 스마트스토어 액션 카탈로그 및 제출 이력 조회">
      <SmartStoreClient
        catalog={catalog}
        catalogError={catalogError}
        submit={submit}
        submitError={submitError}
      />
    </PageShell>
  );
}
