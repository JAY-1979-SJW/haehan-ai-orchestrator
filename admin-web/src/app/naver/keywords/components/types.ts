import type { SearchRunResult } from "@/lib/assistant/api";

export interface SearchState {
  running: boolean;
  result: SearchRunResult | null;
  error: string | null;
  listData: unknown[] | null;
  listLoading: boolean;
  listError: string | null;
}
