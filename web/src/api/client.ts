import type { ZodType } from "zod";

import type { components } from "./generated/schema";
import {
  healthSchema,
  jobSchema,
  settingsSchema,
  taskDetailSchema,
  taskListSchema,
} from "./schemas";

export type Health = components["schemas"]["Health"];
export type TaskSummary = components["schemas"]["TaskSummary"];
export type TaskList = components["schemas"]["TaskList"];

export type InboxTask = { id: string; state: string; title: string; source: string };
export type InboxGroup = { key: string; tasks: InboxTask[] };
export type InboxGate = {
  task_id: string;
  title: string;
  plan_version?: number;
  waiting_since?: string;
  waiting_hours?: number;
  overdue?: boolean;
};
export type Inbox = {
  ok: boolean;
  duplicates: InboxGroup[];
  groups: number;
  gates?: InboxGate[];
  reminder_hours?: number;
};
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

export interface Device {
  id: string;
  label: string;
  created_at: number;
  last_seen: number;
  expires_at?: number;
}

export interface Pairing {
  ok: boolean;
  code: string;
  label: string;
  expires_in: number;
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

const TOKEN_KEY = "works.token";

let session: Promise<void> | null = null;

function urlToken(): string | null {
  return new URLSearchParams(location.search).get("bootstrap");
}

export function rememberedToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function rememberToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private mode: the cookie still works for this browser session.
  }
}

export function forgetToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing to forget.
  }
  session = null;
}

function clearBootstrapParam(): void {
  const params = new URLSearchParams(location.search);
  if (!params.has("bootstrap")) return;
  params.delete("bootstrap");
  const query = params.toString();
  history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
}

async function exchange(token: string): Promise<void> {
  const response = await fetch(`${BASE}/session`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (response.ok) return;
  const text = await response.text().catch(() => "");
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  throw errorDetails(data, response.status);
}

function ensureSession(): Promise<void> {
  if (session) return session;
  const token = urlToken() ?? rememberedToken();
  if (!token) return Promise.resolve();
  session = (async () => {
    try {
      await exchange(token);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) forgetToken();
      throw error;
    }
    rememberToken(token);
    clearBootstrapParam();
  })();
  return session;
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/** Paste a daemon token once; the browser remembers it and re-exchanges after a restart. */
export async function signIn(token: string): Promise<void> {
  const clean = token.trim();
  if (!clean) throw new ApiError("Enter the token or a pairing code", 400, "bad_request");
  await exchange(clean);
  rememberToken(clean);
  clearBootstrapParam();
  session = Promise.resolve();
}

/** A one-time pairing code from `works daemon pair`, exchanged for a 30-day device token. */
export async function pairAndSignIn(code: string, label = "browser"): Promise<void> {
  const response = await fetch(`${BASE}/pair`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code.trim(), label }),
  });
  const text = await response.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!response.ok) throw errorDetails(data, response.status);
  const token = (data as { token?: unknown }).token;
  if (typeof token !== "string" || !token) {
    throw new ApiError("The daemon did not return a device token", 502, "bad_response");
  }
  await signIn(token);
}

export async function connect(credential: string): Promise<void> {
  const clean = credential.trim();
  if (!clean) throw new ApiError("Enter the token or a pairing code", 400, "bad_request");
  try {
    await signIn(clean);
    return;
  } catch (error) {
    if (!isUnauthorized(error)) throw error;
  }
  try {
    await pairAndSignIn(clean);
  } catch (error) {
    if (isUnauthorized(error)) {
      throw new ApiError("That is not a valid token or pairing code", 401, "unauthorized");
    }
    throw error;
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  await ensureSession();
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

export function parseResponse<T>(schema: ZodType, data: unknown, label: string): T {
  const result = schema.safeParse(data);
  if (!result.success) {
    const issue = result.error.issues[0];
    const detail = issue ? `${issue.path.join(".") || "payload"}: ${issue.message}` : "invalid";
    throw new ApiError(`unexpected ${label} payload (${detail})`, 502, "bad_response");
  }
  return result.data as T;
}

export const api = {
  health: async () => parseResponse<Health>(healthSchema, await request("/health"), "health"),
  tasks: async (limit = 200) =>
    parseResponse<TaskList>(taskListSchema, await request(`/tasks?limit=${limit}`), "task list"),
  task: async (taskId: string) =>
    parseResponse<TaskDetail>(
      taskDetailSchema,
      await request(`/tasks/${encodeURIComponent(taskId)}`),
      "task",
    ),
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
  job: async (jobId: string) =>
    parseResponse<Job>(jobSchema, await request(`/jobs/${encodeURIComponent(jobId)}`), "job"),
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
  inbox: () => request<Inbox>("/inbox"),
  mergeTask: (taskId: string, into: string) =>
    request<{ ok: boolean; merged: string; into: string }>(
      `/tasks/${encodeURIComponent(taskId)}/merge`,
      { method: "POST", body: { into }, idempotencyKey: newIdempotencyKey() },
    ),
  muteSource: (source: string) =>
    request<{ ok: boolean; source: { name: string; enabled: boolean } }>("/inbox/mute", {
      method: "POST",
      body: { source },
      idempotencyKey: newIdempotencyKey(),
    }),
  devices: () => request<{ ok: boolean; devices: Device[] }>("/admin/devices"),
  pairStart: (label = "device") =>
    request<Pairing>("/admin/pair", { method: "POST", body: { label } }),
  revokeDevice: (deviceId: string) =>
    request<{ ok: boolean; revoked: boolean }>(
      `/admin/devices/${encodeURIComponent(deviceId)}`,
      { method: "DELETE" },
    ),
  products: () => request<Json>("/products"),
  detectors: (refresh = false) => request<Json>(`/detectors?refresh=${refresh ? "1" : "0"}`),
  metrics: () => request<Json>("/metrics"),
  ledger: () => request<Json>("/ledger"),
  settings: async () =>
    parseResponse<{ ok: boolean; builder: Json }>(
      settingsSchema,
      await request("/settings/builder"),
      "settings",
    ),
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
