"use client";

import { useEffect, useRef, useState } from "react";
import type { components } from "@codeinsight/shared";

type TaskStatus = components["schemas"]["TaskStatus"];

/** SSE 进度事件载荷 */
interface SSEProgressPayload {
  current_step: TaskStatus;
  percent: number;
  files_processed: number;
  files_total: number;
  knowledge_points_found: number;
}

/** SSE 完整事件载荷 */
interface SSECompletePayload {
  task_id: string;
  status: string;
}

/** SSE 错误事件载荷 */
interface SSEErrorPayload {
  task_id: string;
  status: string;
  error: string;
}

/** useSSE 返回的进度数据 */
interface SSEData {
  taskId: string;
  status: TaskStatus;
  progress: {
    currentStep: TaskStatus;
    percent: number;
    filesProcessed: number;
    filesTotal: number;
    knowledgePointsFound: number;
  };
}

/** useSSE 返回值 */
interface UseSSEResult {
  /** 当前进度数据，未连接或连接初始时为 null */
  data: SSEData | null;
  /** 连接错误或任务错误消息 */
  error: string | null;
  /** 任务是否已完成或失败 */
  isComplete: boolean;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

/**
 * 实时任务进度 SSE Hook
 *
 * 通过 fetch streaming 消费 /api/v1/tasks/{taskId}/stream SSE 端点，
 * 实时推送任务进度、完成和错误事件。
 *
 * 当 taskId 为空或 enabled 为 false 时，不发起连接。
 * 当任务完成或失败后，连接自动关闭，isComplete 置为 true。
 *
 * @param taskId - Celery 任务 ID
 * @param enabled - 是否启用连接
 */
export function useSSE(taskId: string, enabled = true): UseSSEResult {
  const [data, setData] = useState<SSEData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // 不满足连接条件时跳过
    if (!taskId || !enabled) {
      return;
    }

    // 如果之前已完成，重置状态（允许重新连接）
    if (isComplete) {
      setData(null);
      setError(null);
      setIsComplete(false);
    }

    const abortController = new AbortController();
    abortRef.current = abortController;

    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    };
    if (API_KEY) {
      headers["X-API-Key"] = API_KEY;
    }

    const connect = async () => {
      try {
        const response = await fetch(
          `${BASE_URL}/api/v1/tasks/${taskId}/stream`,
          { headers, signal: abortController.signal },
        );

        if (!response.ok) {
          setError(`SSE 连接失败 (${response.status})`);
          setIsComplete(true);
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          setError("响应体不可读");
          setIsComplete(true);
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }

          buffer += decoder.decode(value, { stream: true });

          // SSE 事件以空行分隔
          const parts = buffer.split("\n\n");
          // 最后一段可能不完整，保留到下次读取
          buffer = parts.pop() || "";

          for (const part of parts) {
            const lines = part.split("\n");
            let eventType = "";
            let jsonData = "";

            for (const line of lines) {
              if (line.startsWith("event: ")) {
                eventType = line.slice(7).trim();
              } else if (line.startsWith("data: ")) {
                jsonData = line.slice(6);
              }
            }

            if (!jsonData) {
              continue;
            }

            try {
              const parsed = JSON.parse(jsonData);

              if (eventType === "progress") {
                const payload = parsed as SSEProgressPayload;
                setData({
                  taskId,
                  status: payload.current_step,
                  progress: {
                    currentStep: payload.current_step,
                    percent: payload.percent,
                    filesProcessed: payload.files_processed,
                    filesTotal: payload.files_total,
                    knowledgePointsFound: payload.knowledge_points_found,
                  },
                });
              } else if (eventType === "complete") {
                setData((prev) =>
                  prev
                    ? { ...prev, status: "completed" as TaskStatus }
                    : null,
                );
                setIsComplete(true);
                return; // 连接自然结束
              } else if (eventType === "error") {
                const errPayload = parsed as SSEErrorPayload;
                setError(errPayload.error || "任务执行失败");
                setIsComplete(true);
                return;
              }
            } catch {
              // 忽略格式异常的 JSON
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // 组件卸载或重新连接时主动取消，非错误
          return;
        }
        if (!abortController.signal.aborted) {
          setError(`SSE 连接异常: ${err}`);
          setIsComplete(true);
        }
      }
    };

    connect();

    return () => {
      abortController.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, enabled]);

  return { data, error, isComplete };
}