import type { components } from "./generated/schema";

export type Health = components["schemas"]["Health"];
export type TaskSummary = components["schemas"]["TaskSummary"];
export type TaskList = components["schemas"]["TaskList"];
export type TaskDetail = components["schemas"]["TaskDetail"];
export type RunSummary = components["schemas"]["RunSummary"];
export type RunList = components["schemas"]["RunList"];
export type Json = Record<string, unknown>;

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: string;
  action: string;
  task_id?: string | null;
  status: JobStatus;
  created_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  result?: unknown;
  error?: string | null;
  log_tail?: string;
  cancelable?: boolean;
}

export interface JobEnvelope {
  ok: boolean;
  action: string;
  job: Job;
}

export interface ActionRequest extends Json {
  action: string;
  task_id: string;
}

export interface ActionResponse extends Json {
  ok: boolean;
  action?: string;
  job?: Job;
  task?: TaskDetail["task"];
  event?: Json;
}

export interface CreateTaskRequest extends Json {
  repo: string;
  ref: string;
  title: string;
  product?: string;
  kind?: string;
  task_kind?: string;
  flow?: string;
}

export interface CreateTaskResponse extends Json {
  ok: boolean;
  created: boolean;
  task: TaskDetail["task"];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code = "http_error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const BASE = "/api/v1";

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  idempotencyKey?: string;
}

function newIdempotencyKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorDetails(data: unknown, status: number): ApiError {
  if (typeof data === "object" && data !== null) {
    const error = (data as { error?: { code?: unknown; message?: unknown } }).error;
    if (error && typeof error === "object") {
      const message = typeof error.message === "string" ? error.message : `HTTP ${status}`;
      const code = typeof error.code === "string" ? error.code : "http_error";
      return new ApiError(message, status, code);
    }
  }
  return new ApiError(`HTTP ${status}`, status);
}

let session: Promise<void> | null = null;

function ensureSession(): Promise<void> {
  if (session) return session;
  session = (async () => {
    const params = new URLSearchParams(location.search);
    const token = params.get("bootstrap");
    if (!token) return;
    await fetch(`${BASE}/session`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    params.delete("bootstrap");
    const query = params.toString();
    history.replaceState(
      null,
      "",
      `${location.pathname}${query ? `?${query}` : ""}${location.hash}`,
    );
  })();
  return session;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if ((options.method ?? "GET") !== "GET") await ensureSession();
  const headers: Record<string, string> = { ...(options.headers ?? {}) };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  const response = await fetch(`${BASE}${path}`, {
    method: options.method ?? "GET",
    credentials: "same-origin",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const text = await response.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: { message: text } };
  }
  if (!response.ok) throw errorDetails(data, response.status);
  return data as T;
}

export const api = {
  health: () => request<Health>("/health"),
  tasks: (limit = 200) => request<TaskList>(`/tasks?limit=${limit}`),
  task: (taskId: string) => request<TaskDetail>(`/tasks/${encodeURIComponent(taskId)}`),
  createTask: (body: CreateTaskRequest) =>
    request<CreateTaskResponse>("/tasks", {
      method: "POST",
      body,
      idempotencyKey: newIdempotencyKey(),
    }),
  action: (body: ActionRequest) =>
    request<ActionResponse>("/actions", {
      method: "POST",
      body,
      idempotencyKey: newIdempotencyKey(),
    }),
  job: (jobId: string) => request<Job>(`/jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId: string) =>
    request<Job>(`/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" }),
  readiness: (body: { repo?: string; task_id?: string }) =>
    request<JobEnvelope>("/readiness", { method: "POST", body }),
  sources: (body: Json) =>
    request<JobEnvelope>("/sources", {
      method: "POST",
      body,
      idempotencyKey: newIdempotencyKey(),
    }),
  products: () => request<Json>("/products"),
  detectors: (refresh = false) => request<Json>(`/detectors?refresh=${refresh ? "1" : "0"}`),
  metrics: () => request<Json>("/metrics"),
  ledger: () => request<Json>("/ledger"),
  settings: () => request<{ ok: boolean; builder: Json }>("/settings/builder"),
  saveSettings: (body: Json) =>
    request<{ ok: boolean; builder: Json }>("/settings/builder", { method: "POST", body }),
};

export async function waitForJob(jobId: string, timeoutMs = 180_000): Promise<Job> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const job = await api.job(jobId);
    if (!isActive(job.status)) return job;
    if (Date.now() > deadline) throw new ApiError("job timed out", 504, "timeout");
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

function isActive(status: JobStatus): boolean {
  return status === "queued" || status === "running";
}

export async function askStream(
  taskId: string,
  question: string,
  onEvent: (event: Json) => void,
): Promise<Json | null> {
  await ensureSession();
  const response = await fetch(`${BASE}/ask/stream`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, question }),
  });
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `HTTP ${response.status}`, response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: Json | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf("\n\n");
    while (split >= 0) {
      const chunk = buffer.slice(0, split).trim();
      buffer = buffer.slice(split + 2);
      for (const line of chunk.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        let event: Json;
        try {
          event = JSON.parse(line.slice(6)) as Json;
        } catch {
          continue;
        }
        onEvent(event);
        if (event.type === "done") final = event;
        if (event.type === "error") {
          throw new ApiError(String(event.error ?? "Mira failed"), 502, "harness_error");
        }
      }
      split = buffer.indexOf("\n\n");
    }
  }
  return final;
}
