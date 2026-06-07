import { useState, useCallback, useEffect } from "react";
import { getAgentTasks, ApiError } from "@/lib/api";
import type { LocalAgentTask } from "@/types/local-agent";
import { fetchErrorMessage } from "../components/helpers";

export interface UseTaskDataResult {
  tasks: LocalAgentTask[];
  tasksLoading: boolean;
  tasksError: string | null;
  taskStatusFilter: string;
  setTaskStatusFilter: React.Dispatch<React.SetStateAction<string>>;
  tasksTotal: number;
  fetchTasks: (agentId: string, status: string) => Promise<void>;
  backgroundFetchTasks: (agentId: string, status: string) => Promise<void>;
}

export interface UseTaskDataParams {
  currentUserRole: string | undefined;
  selectedAgentId: string | null;
  isPollingTasksRef: React.MutableRefObject<boolean>;
  setLastRefreshedAt: React.Dispatch<React.SetStateAction<Date | null>>;
  setPollingError: React.Dispatch<React.SetStateAction<string | null>>;
}

export function useTaskData({
  currentUserRole,
  selectedAgentId,
  isPollingTasksRef,
  setLastRefreshedAt,
  setPollingError,
}: UseTaskDataParams): UseTaskDataResult {
  const [tasks, setTasks] = useState<LocalAgentTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [taskStatusFilter, setTaskStatusFilter] = useState<string>("");
  const [tasksTotal, setTasksTotal] = useState(0);

  const fetchTasks = useCallback(async (agentId: string, status: string) => {
    setTasksLoading(true);
    setTasksError(null);
    try {
      const data = await getAgentTasks(agentId, {
        limit: 50,
        status: status || undefined,
      });
      setTasks(data.tasks);
      setTasksTotal(data.total);
      setLastRefreshedAt(new Date());
    } catch (err) {
      setTasksError(fetchErrorMessage(err, "작업 목록 조회 실패", currentUserRole));
      setTasks([]);
      setTasksTotal(0);
    } finally {
      setTasksLoading(false);
    }
  }, [currentUserRole, setLastRefreshedAt]);

  const backgroundFetchTasks = useCallback(async (agentId: string, status: string) => {
    if (isPollingTasksRef.current) return;
    isPollingTasksRef.current = true;
    try {
      const data = await getAgentTasks(agentId, {
        limit: 50,
        status: status || undefined,
      });
      setTasks(data.tasks);
      setTasksTotal(data.total);
      setLastRefreshedAt(new Date());
      setPollingError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? `API ${err.status}` : "네트워크 오류";
      setPollingError(`자동 새로고침 실패: ${msg}`);
    } finally {
      isPollingTasksRef.current = false;
    }
  }, [isPollingTasksRef, setLastRefreshedAt, setPollingError]);

  useEffect(() => {
    if (selectedAgentId) {
      fetchTasks(selectedAgentId, taskStatusFilter);
    }
  }, [selectedAgentId, taskStatusFilter, fetchTasks]);

  return {
    tasks,
    tasksLoading,
    tasksError,
    taskStatusFilter,
    setTaskStatusFilter,
    tasksTotal,
    fetchTasks,
    backgroundFetchTasks,
  };
}
