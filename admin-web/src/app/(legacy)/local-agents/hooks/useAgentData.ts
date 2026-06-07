import { useState, useCallback, useEffect } from "react";
import { getLocalAgents, getLocalAgentsDiagnostics, ApiError } from "@/lib/api";
import type { LocalAgent, LocalAgentDiagnostics } from "@/types/local-agent";
import { fetchErrorMessage } from "../components/helpers";

export interface UseAgentDataResult {
  agents: LocalAgent[];
  agentsLoading: boolean;
  agentsError: string | null;
  selectedAgentId: string | null;
  setSelectedAgentId: React.Dispatch<React.SetStateAction<string | null>>;
  agentStatusFilter: string;
  setAgentStatusFilter: React.Dispatch<React.SetStateAction<string>>;
  diagnostics: LocalAgentDiagnostics | null;
  diagnosticsError: string | null;
  fetchAgents: () => Promise<void>;
  fetchDiagnostics: () => Promise<void>;
  backgroundFetchAgents: () => Promise<void>;
}

export interface UseAgentDataParams {
  currentUserRole: string | undefined;
  isPollingAgentsRef: React.MutableRefObject<boolean>;
  setLastRefreshedAt: React.Dispatch<React.SetStateAction<Date | null>>;
  setPollingError: React.Dispatch<React.SetStateAction<string | null>>;
}

export function useAgentData({
  currentUserRole,
  isPollingAgentsRef,
  setLastRefreshedAt,
  setPollingError,
}: UseAgentDataParams): UseAgentDataResult {
  const [agents, setAgents] = useState<LocalAgent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [agentStatusFilter, setAgentStatusFilter] = useState<string>("");
  const [diagnostics, setDiagnostics] = useState<LocalAgentDiagnostics | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);

  const fetchDiagnostics = useCallback(async () => {
    setDiagnosticsError(null);
    try {
      const res = await getLocalAgentsDiagnostics();
      setDiagnostics(res.diagnostics);
    } catch (err) {
      setDiagnosticsError(
        fetchErrorMessage(err, "진단 정보를 불러올 수 없음", currentUserRole)
      );
    }
  }, [currentUserRole]);

  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    setAgentsError(null);
    try {
      const data = await getLocalAgents();
      setAgents(data.agents);
      if (data.agents.length > 0) {
        setSelectedAgentId((prev) => prev ?? data.agents[0].agent_id);
      }
      setLastRefreshedAt(new Date());
    } catch (err) {
      setAgentsError(fetchErrorMessage(err, "에이전트 목록 조회 실패", currentUserRole));
    } finally {
      setAgentsLoading(false);
    }
  }, [currentUserRole, setLastRefreshedAt]);

  const backgroundFetchAgents = useCallback(async () => {
    if (isPollingAgentsRef.current) return;
    isPollingAgentsRef.current = true;
    try {
      const [agentsData, diagData] = await Promise.all([
        getLocalAgents(),
        getLocalAgentsDiagnostics().catch(() => null),
      ]);
      setAgents(agentsData.agents);
      if (diagData) {
        setDiagnostics(diagData.diagnostics);
        setDiagnosticsError(null);
      }
      setLastRefreshedAt(new Date());
      setPollingError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? `API ${err.status}` : "네트워크 오류";
      setPollingError(`자동 새로고침 실패: ${msg}`);
    } finally {
      isPollingAgentsRef.current = false;
    }
  }, [isPollingAgentsRef, setLastRefreshedAt, setPollingError]);

  useEffect(() => {
    fetchAgents();
    fetchDiagnostics();
  }, [fetchAgents, fetchDiagnostics]);

  return {
    agents,
    agentsLoading,
    agentsError,
    selectedAgentId,
    setSelectedAgentId,
    agentStatusFilter,
    setAgentStatusFilter,
    diagnostics,
    diagnosticsError,
    fetchAgents,
    fetchDiagnostics,
    backgroundFetchAgents,
  };
}
