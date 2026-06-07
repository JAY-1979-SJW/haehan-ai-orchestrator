import { useState, useCallback, useRef } from "react";
import {
  cancelTask,
  approveLocalAgentTask,
  rejectLocalAgentTask,
  requestCaptureScreenshot,
  getLocalAgentTask,
  ApiError,
} from "@/lib/api";
import type { LocalAgent, LocalAgentTask, LocalAgentTaskDetail } from "@/types/local-agent";
import {
  roleAwareAuthMessage,
  cancelErrorMessage,
  approvalErrorMessage,
  captureErrorMessage,
  extractCaptureSuccessInfo,
} from "../components/helpers";
import type { CaptureSuccessInfo } from "../components/helpers";

export interface UseModalsResult {
  // Cancel modal
  cancelTargetTask: LocalAgentTask | null;
  setCancelTargetTask: React.Dispatch<React.SetStateAction<LocalAgentTask | null>>;
  cancelReason: string;
  setCancelReason: React.Dispatch<React.SetStateAction<string>>;
  cancelError: string | null;
  setCancelError: React.Dispatch<React.SetStateAction<string | null>>;
  cancelLoading: boolean;
  setCancelLoading: React.Dispatch<React.SetStateAction<boolean>>;
  handleCancelSubmit: () => Promise<void>;
  handleCancelClose: () => void;

  // Approval modal
  approvalTargetTask: LocalAgentTask | null;
  setApprovalTargetTask: React.Dispatch<React.SetStateAction<LocalAgentTask | null>>;
  approvalAction: "approve" | "reject" | null;
  setApprovalAction: React.Dispatch<React.SetStateAction<"approve" | "reject" | null>>;
  approvalReason: string;
  setApprovalReason: React.Dispatch<React.SetStateAction<string>>;
  approvalLoading: boolean;
  setApprovalLoading: React.Dispatch<React.SetStateAction<boolean>>;
  approvalError: string | null;
  setApprovalError: React.Dispatch<React.SetStateAction<string | null>>;
  handleOpenApprovalModal: (task: LocalAgentTask) => void;
  handleCloseApprovalModal: () => void;
  handleApprovalSubmit: () => Promise<void>;

  // Capture modal
  captureTargetAgent: LocalAgent | null;
  setCaptureTargetAgent: React.Dispatch<React.SetStateAction<LocalAgent | null>>;
  captureMode: "dry_run" | "real" | null;
  setCaptureMode: React.Dispatch<React.SetStateAction<"dry_run" | "real" | null>>;
  captureLoading: boolean;
  setCaptureLoading: React.Dispatch<React.SetStateAction<boolean>>;
  captureError: string | null;
  setCaptureError: React.Dispatch<React.SetStateAction<string | null>>;
  captureSuccess: CaptureSuccessInfo | null;
  setCaptureSuccess: React.Dispatch<React.SetStateAction<CaptureSuccessInfo | null>>;
  captureReason: string;
  setCaptureReason: React.Dispatch<React.SetStateAction<string>>;
  handleDryRun: (agent: LocalAgent) => Promise<void>;
  handleOpenCaptureModal: (agent: LocalAgent) => void;
  handleCloseCaptureModal: () => void;
  handleCaptureSubmit: () => Promise<void>;

  // Detail modal
  detailTargetTask: LocalAgentTask | null;
  setDetailTargetTask: React.Dispatch<React.SetStateAction<LocalAgentTask | null>>;
  detailData: LocalAgentTaskDetail | null;
  setDetailData: React.Dispatch<React.SetStateAction<LocalAgentTaskDetail | null>>;
  detailLoading: boolean;
  setDetailLoading: React.Dispatch<React.SetStateAction<boolean>>;
  detailError: string | null;
  setDetailError: React.Dispatch<React.SetStateAction<string | null>>;
  handleOpenDetail: (task: LocalAgentTask) => Promise<void>;
  handleCloseDetail: () => void;
}

export interface UseModalsParams {
  selectedAgentId: string | null;
  taskStatusFilter: string;
  currentUserRole: string | undefined;
  fetchTasks: (agentId: string, status: string) => Promise<void>;
  fetchAgents: () => Promise<void>;
}

export function useModals({
  selectedAgentId,
  taskStatusFilter,
  currentUserRole,
  fetchTasks,
  fetchAgents,
}: UseModalsParams): UseModalsResult {
  // Cancel modal
  const [cancelTargetTask, setCancelTargetTask] = useState<LocalAgentTask | null>(null);
  const [cancelReason, setCancelReason] = useState<string>("");
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [cancelLoading, setCancelLoading] = useState(false);

  // Detail modal
  const [detailTargetTask, setDetailTargetTask] = useState<LocalAgentTask | null>(null);
  const [detailData, setDetailData] = useState<LocalAgentTaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Capture modal
  const [captureTargetAgent, setCaptureTargetAgent] = useState<LocalAgent | null>(null);
  const [captureMode, setCaptureMode] = useState<"dry_run" | "real" | null>(null);
  const [captureLoading, setCaptureLoading] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [captureSuccess, setCaptureSuccess] = useState<CaptureSuccessInfo | null>(null);
  const [captureReason, setCaptureReason] = useState<string>("");

  // Approval modal
  const [approvalTargetTask, setApprovalTargetTask] = useState<LocalAgentTask | null>(null);
  const [approvalAction, setApprovalAction] = useState<"approve" | "reject" | null>(null);
  const [approvalReason, setApprovalReason] = useState<string>("");
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  // Cancel handlers
  const handleCancelSubmit = useCallback(async () => {
    if (!cancelTargetTask || !selectedAgentId) return;
    setCancelLoading(true);
    setCancelError(null);
    try {
      await cancelTask(selectedAgentId, cancelTargetTask.task_id, cancelReason);
      setCancelTargetTask(null);
      setCancelReason("");
      await Promise.all([
        fetchTasks(selectedAgentId, taskStatusFilter),
        fetchAgents(),
      ]);
    } catch (err) {
      setCancelError(cancelErrorMessage(err, currentUserRole));
    } finally {
      setCancelLoading(false);
    }
  }, [cancelTargetTask, selectedAgentId, cancelReason, taskStatusFilter, fetchTasks, fetchAgents, currentUserRole]);

  const handleCancelClose = useCallback(() => {
    if (cancelLoading) return;
    setCancelTargetTask(null);
    setCancelReason("");
    setCancelError(null);
  }, [cancelLoading]);

  // Approval handlers
  const handleOpenApprovalModal = useCallback((task: LocalAgentTask) => {
    setApprovalTargetTask(task);
    setApprovalAction(null);
    setApprovalReason("");
    setApprovalError(null);
  }, []);

  const handleCloseApprovalModal = useCallback(() => {
    if (approvalLoading) return;
    setApprovalTargetTask(null);
    setApprovalAction(null);
    setApprovalReason("");
    setApprovalError(null);
  }, [approvalLoading]);

  const handleApprovalSubmit = useCallback(async () => {
    if (!approvalTargetTask || !approvalAction || !selectedAgentId) return;
    setApprovalLoading(true);
    setApprovalError(null);
    try {
      const detail = await getLocalAgentTask(selectedAgentId, approvalTargetTask.task_id);
      if (!detail.token_id) {
        setApprovalError("승인 토큰을 찾을 수 없습니다. 작업 상태를 확인하세요.");
        return;
      }
      const body = {
        token_id: detail.token_id,
        reason: approvalReason.trim() || undefined,
      };
      if (approvalAction === "approve") {
        await approveLocalAgentTask(selectedAgentId, approvalTargetTask.task_id, body);
      } else {
        await rejectLocalAgentTask(selectedAgentId, approvalTargetTask.task_id, body);
      }
      setApprovalTargetTask(null);
      setApprovalAction(null);
      setApprovalReason("");
      await Promise.all([
        fetchTasks(selectedAgentId, taskStatusFilter),
        fetchAgents(),
      ]);
    } catch (err) {
      setApprovalError(approvalErrorMessage(err, currentUserRole));
    } finally {
      setApprovalLoading(false);
    }
  }, [
    approvalTargetTask, approvalAction, approvalReason, selectedAgentId,
    taskStatusFilter, fetchTasks, fetchAgents, currentUserRole,
  ]);

  // Detail handlers
  const handleOpenDetail = useCallback(async (task: LocalAgentTask) => {
    if (!selectedAgentId) return;
    setDetailTargetTask(task);
    setDetailData(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const detail = await getLocalAgentTask(selectedAgentId, task.task_id);
      setDetailData(detail);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401 || err.status === 403) {
          setDetailError(roleAwareAuthMessage(err.status as 401 | 403, currentUserRole));
        } else if (err.status === 404) {
          setDetailError("작업을 찾을 수 없습니다.");
        } else {
          setDetailError("작업 상세 조회에 실패했습니다.");
        }
      } else {
        setDetailError("작업 상세 조회에 실패했습니다.");
      }
    } finally {
      setDetailLoading(false);
    }
  }, [selectedAgentId, currentUserRole]);

  const handleCloseDetail = useCallback(() => {
    setDetailTargetTask(null);
    setDetailData(null);
    setDetailError(null);
    setDetailLoading(false);
  }, []);

  // Capture handlers
  const handleDryRun = useCallback(async (agent: LocalAgent) => {
    setCaptureSuccess(null);
    setCaptureError(null);
    setCaptureLoading(true);
    try {
      const res = await requestCaptureScreenshot(agent.agent_id, {
        dryRun: true,
        reason: "admin_web_dry_run_check",
      });
      setCaptureSuccess(extractCaptureSuccessInfo(res));
    } catch (err) {
      setCaptureError(captureErrorMessage(err, currentUserRole));
    } finally {
      setCaptureLoading(false);
    }
  }, [currentUserRole]);

  const handleOpenCaptureModal = useCallback((agent: LocalAgent) => {
    setCaptureTargetAgent(agent);
    setCaptureMode("real");
    setCaptureError(null);
    setCaptureSuccess(null);
    setCaptureReason("");
  }, []);

  const handleCloseCaptureModal = useCallback(() => {
    if (captureLoading) return;
    setCaptureTargetAgent(null);
    setCaptureMode(null);
    setCaptureError(null);
    setCaptureReason("");
  }, [captureLoading]);

  const handleCaptureSubmit = useCallback(async () => {
    if (!captureTargetAgent) return;
    setCaptureLoading(true);
    setCaptureError(null);
    try {
      const res = await requestCaptureScreenshot(captureTargetAgent.agent_id, {
        dryRun: false,
        reason: captureReason.trim() || undefined,
      });
      const info = extractCaptureSuccessInfo(res);
      setCaptureTargetAgent(null);
      setCaptureMode(null);
      setCaptureReason("");
      setCaptureSuccess(info);
      await Promise.all([
        fetchAgents(),
        ...(selectedAgentId === captureTargetAgent.agent_id
          ? [fetchTasks(captureTargetAgent.agent_id, taskStatusFilter)]
          : []),
      ]);
    } catch (err) {
      setCaptureError(captureErrorMessage(err, currentUserRole));
    } finally {
      setCaptureLoading(false);
    }
  }, [captureTargetAgent, captureReason, selectedAgentId, taskStatusFilter, fetchAgents, fetchTasks, currentUserRole]);

  return {
    // Cancel modal
    cancelTargetTask, setCancelTargetTask,
    cancelReason, setCancelReason,
    cancelError, setCancelError,
    cancelLoading, setCancelLoading,
    handleCancelSubmit, handleCancelClose,

    // Approval modal
    approvalTargetTask, setApprovalTargetTask,
    approvalAction, setApprovalAction,
    approvalReason, setApprovalReason,
    approvalLoading, setApprovalLoading,
    approvalError, setApprovalError,
    handleOpenApprovalModal, handleCloseApprovalModal, handleApprovalSubmit,

    // Capture modal
    captureTargetAgent, setCaptureTargetAgent,
    captureMode, setCaptureMode,
    captureLoading, setCaptureLoading,
    captureError, setCaptureError,
    captureSuccess, setCaptureSuccess,
    captureReason, setCaptureReason,
    handleDryRun, handleOpenCaptureModal, handleCloseCaptureModal, handleCaptureSubmit,

    // Detail modal
    detailTargetTask, setDetailTargetTask,
    detailData, setDetailData,
    detailLoading, setDetailLoading,
    detailError, setDetailError,
    handleOpenDetail, handleCloseDetail,
  };
}
