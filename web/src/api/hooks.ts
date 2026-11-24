import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type ActionRequest,
  type ActionResponse,
  type ApiError,
  type Job,
  type JobStatus,
} from "./client";

export const queryKeys = {
  tasks: ["tasks"] as const,
  metrics: ["metrics"] as const,
  settings: ["settings"] as const,
  task: (taskId: string) => ["task", taskId] as const,
  job: (jobId: string) => ["job", jobId] as const,
};

export function isActiveStatus(status: JobStatus): boolean {
  return status === "queued" || status === "running";
}

export function isTerminalStatus(status: JobStatus): boolean {
  return !isActiveStatus(status);
}

export function useTasks(limit = 200) {
  return useQuery({ queryKey: queryKeys.tasks, queryFn: () => api.tasks(limit) });
}

export function useTaskDetail(taskId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.task(taskId ?? ""),
    queryFn: () => api.task(taskId as string),
    enabled: Boolean(taskId),
  });
}

export function useMetrics() {
  return useQuery({ queryKey: queryKeys.metrics, queryFn: () => api.metrics() });
}

export function useSettings() {
  return useQuery({ queryKey: queryKeys.settings, queryFn: () => api.settings() });
}

export function useAction() {
  const client = useQueryClient();
  return useMutation<ActionResponse, ApiError, ActionRequest>({
    mutationFn: (request) => api.action(request),
    onSuccess: (result, request) => {
      void client.invalidateQueries({ queryKey: queryKeys.tasks });
      void client.invalidateQueries({ queryKey: queryKeys.task(request.task_id) });
      if (result.job?.task_id) {
        void client.invalidateQueries({ queryKey: queryKeys.task(result.job.task_id) });
      }
    },
  });
}

export function useJob(jobId: string | null | undefined, onDone?: (job: Job) => void) {
  const client = useQueryClient();
  const onDoneRef = useRef(onDone);
  const doneRef = useRef("");
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  const query = useQuery({
    queryKey: queryKeys.job(jobId ?? ""),
    queryFn: () => api.job(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (current) => {
      const job = current.state.data as Job | undefined;
      return job && isActiveStatus(job.status) ? 1000 : false;
    },
  });

  const job = query.data;
  useEffect(() => {
    if (!job || !isTerminalStatus(job.status)) return;
    const marker = `${job.id}:${job.status}`;
    if (doneRef.current === marker) return;
    doneRef.current = marker;
    void client.invalidateQueries({ queryKey: queryKeys.tasks });
    if (job.task_id) void client.invalidateQueries({ queryKey: queryKeys.task(job.task_id) });
    onDoneRef.current?.(job);
  }, [job, client]);

  return query;
}

export function useEvents() {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource("/api/v1/events");
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    const listen = (name: string, handler: (data: Record<string, unknown>) => void) => {
      source.addEventListener(name, (event) => {
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse((event as MessageEvent).data) as Record<string, unknown>;
        } catch {
          data = {};
        }
        handler(data);
      });
    };

    listen("queue.changed", () => {
      void client.invalidateQueries({ queryKey: queryKeys.tasks });
    });
    listen("task.changed", (data) => {
      void client.invalidateQueries({ queryKey: queryKeys.tasks });
      if (typeof data.task_id === "string") {
        void client.invalidateQueries({ queryKey: queryKeys.task(data.task_id) });
      }
    });
    listen("run.changed", (data) => {
      if (typeof data.task_id === "string") {
        void client.invalidateQueries({ queryKey: queryKeys.task(data.task_id) });
      }
    });
    listen("job.changed", (data) => {
      void client.invalidateQueries({ queryKey: queryKeys.tasks });
      if (typeof data.job_id === "string") {
        void client.invalidateQueries({ queryKey: queryKeys.job(data.job_id) });
      }
    });
    listen("settings.changed", () => {
      void client.invalidateQueries({ queryKey: queryKeys.settings });
    });
    listen("resync", () => {
      void client.invalidateQueries();
    });

    return () => source.close();
  }, [client]);

  return { connected };
}
