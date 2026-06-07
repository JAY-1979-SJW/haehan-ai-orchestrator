import { useState, useEffect, useRef, useCallback } from "react";

const POLLING_INTERVAL_MS = 15_000;

export interface UsePollingRefs {
  isPollingAgentsRef: React.MutableRefObject<boolean>;
  isPollingTasksRef: React.MutableRefObject<boolean>;
  selectedAgentIdRef: React.MutableRefObject<string | null>;
  taskStatusFilterRef: React.MutableRefObject<string>;
  cancelModalOpenRef: React.MutableRefObject<boolean>;
  captureModalOpenRef: React.MutableRefObject<boolean>;
  approvalModalOpenRef: React.MutableRefObject<boolean>;
}

export interface UsePollingResult extends UsePollingRefs {
  pollingEnabled: boolean;
  setPollingEnabled: React.Dispatch<React.SetStateAction<boolean>>;
  pollingError: string | null;
  setPollingError: React.Dispatch<React.SetStateAction<string | null>>;
  lastRefreshedAt: Date | null;
  setLastRefreshedAt: React.Dispatch<React.SetStateAction<Date | null>>;
  isDocumentHidden: boolean;
}

export interface UsePollingCallbacks {
  backgroundFetchAgents: () => Promise<void>;
  backgroundFetchTasks: (agentId: string, status: string) => Promise<void>;
  selectedAgentId: string | null;
  taskStatusFilter: string;
  cancelTargetTask: unknown | null;
  captureMode: string | null;
  captureTargetAgent: unknown | null;
  approvalTargetTask: unknown | null;
}

/**
 * Phase 1: call with no callbacks to get refs + state setters.
 * Phase 2: call usePollingInterval with real callbacks once data hooks are ready.
 */
export function usePollingState(): UsePollingResult {
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const [pollingEnabled, setPollingEnabled] = useState(true);
  const [isDocumentHidden, setIsDocumentHidden] = useState(false);

  const isPollingAgentsRef = useRef(false);
  const isPollingTasksRef = useRef(false);
  const selectedAgentIdRef = useRef<string | null>(null);
  const taskStatusFilterRef = useRef<string>("");
  const cancelModalOpenRef = useRef(false);
  const captureModalOpenRef = useRef(false);
  const approvalModalOpenRef = useRef(false);

  return {
    pollingEnabled,
    setPollingEnabled,
    pollingError,
    setPollingError,
    lastRefreshedAt,
    setLastRefreshedAt,
    isDocumentHidden,
    isPollingAgentsRef,
    isPollingTasksRef,
    selectedAgentIdRef,
    taskStatusFilterRef,
    cancelModalOpenRef,
    captureModalOpenRef,
    approvalModalOpenRef,
    // isDocumentHidden setter is internal — expose via the effect below
  };
}

/**
 * Phase 2: wire up polling effects with real callbacks and ref sync.
 * Call this after all data hooks are initialized.
 */
export function usePollingInterval(
  pollingState: UsePollingResult,
  callbacks: UsePollingCallbacks,
  setIsDocumentHidden: React.Dispatch<React.SetStateAction<boolean>>,
) {
  const {
    pollingEnabled,
    isPollingAgentsRef,
    isPollingTasksRef,
    selectedAgentIdRef,
    taskStatusFilterRef,
    cancelModalOpenRef,
    captureModalOpenRef,
    approvalModalOpenRef,
  } = pollingState;

  const {
    backgroundFetchAgents,
    backgroundFetchTasks,
    selectedAgentId,
    taskStatusFilter,
    cancelTargetTask,
    captureMode,
    captureTargetAgent,
    approvalTargetTask,
  } = callbacks;

  const pollingEnabledRef = useRef(true);
  const prevPollingEnabledRef = useRef(true);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Keep refs in sync with state
  useEffect(() => { selectedAgentIdRef.current = selectedAgentId; }, [selectedAgentId, selectedAgentIdRef]);
  useEffect(() => { taskStatusFilterRef.current = taskStatusFilter; }, [taskStatusFilter, taskStatusFilterRef]);
  useEffect(() => { cancelModalOpenRef.current = cancelTargetTask !== null; }, [cancelTargetTask, cancelModalOpenRef]);
  useEffect(() => {
    captureModalOpenRef.current = captureMode === "real" && captureTargetAgent !== null;
  }, [captureMode, captureTargetAgent, captureModalOpenRef]);
  useEffect(() => {
    approvalModalOpenRef.current = approvalTargetTask !== null;
  }, [approvalTargetTask, approvalModalOpenRef]);
  useEffect(() => { pollingEnabledRef.current = pollingEnabled; }, [pollingEnabled]);

  // Polling interval
  useEffect(() => {
    if (!pollingEnabled) return;

    const tick = () => {
      if (document.hidden) return;
      if (!pollingEnabledRef.current) return;

      const captureOpen = captureModalOpenRef.current;
      const cancelOpen = cancelModalOpenRef.current;
      const agentId = selectedAgentIdRef.current;
      const statusFilter = taskStatusFilterRef.current;

      if (!captureOpen) {
        backgroundFetchAgents();
      }
      if (!captureOpen && !cancelOpen && agentId) {
        backgroundFetchTasks(agentId, statusFilter);
      }
    };

    pollingIntervalRef.current = setInterval(tick, POLLING_INTERVAL_MS);

    return () => {
      if (pollingIntervalRef.current !== null) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [pollingEnabled, backgroundFetchAgents, backgroundFetchTasks,
      captureModalOpenRef, cancelModalOpenRef, selectedAgentIdRef, taskStatusFilterRef]);

  // ON 복귀 시 즉시 background refresh 1회
  useEffect(() => {
    if (pollingEnabled && !prevPollingEnabledRef.current) {
      backgroundFetchAgents();
      const agentId = selectedAgentIdRef.current;
      const statusFilter = taskStatusFilterRef.current;
      if (agentId) backgroundFetchTasks(agentId, statusFilter);
    }
    prevPollingEnabledRef.current = pollingEnabled;
  }, [pollingEnabled, backgroundFetchAgents, backgroundFetchTasks, selectedAgentIdRef, taskStatusFilterRef]);

  // visibilitychange: 탭 복귀 시 즉시 background refresh
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsDocumentHidden(document.hidden);
      if (document.hidden) return;
      if (!pollingEnabledRef.current) return;

      const captureOpen = captureModalOpenRef.current;
      const cancelOpen = cancelModalOpenRef.current;
      const agentId = selectedAgentIdRef.current;
      const statusFilter = taskStatusFilterRef.current;

      if (!captureOpen) {
        backgroundFetchAgents();
      }
      if (!captureOpen && !cancelOpen && agentId) {
        backgroundFetchTasks(agentId, statusFilter);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [backgroundFetchAgents, backgroundFetchTasks, setIsDocumentHidden,
      captureModalOpenRef, cancelModalOpenRef, selectedAgentIdRef, taskStatusFilterRef]);
}
