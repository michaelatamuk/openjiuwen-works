export type ViewId = "story" | "evidence" | "release" | "thread";

export const VIEWS: ReadonlyArray<readonly [ViewId, string]> = [
  ["story", "Story"],
  ["evidence", "Evidence"],
  ["release", "Release"],
  ["thread", "Session"],
];

export const VIEW_NAMES: readonly ViewId[] = VIEWS.map(([id]) => id);

export type Route = {
  taskId: string | null;
  view: ViewId | null;
  at: number | null;
};

export function isViewId(value: string): value is ViewId {
  return VIEW_NAMES.some((id) => id === value);
}

export function parseHash(hash: string = location.hash): Route {
  const match = hash.match(/^#\/task\/([^/?]+)(?:\/(story|evidence|release|thread))?/);
  const query = match ? hash.split("?").slice(1).join("?") : "";
  const at = new URLSearchParams(query).get("at");
  const view = match?.[2];
  return {
    taskId: match ? decodeURIComponent(match[1]) : null,
    view: view && isViewId(view) ? view : null,
    at: at != null && at !== "" ? Number(at) : null,
  };
}

export function taskHash(id: string, view: ViewId, at: number | null = null): string {
  const suffix = view === "evidence" ? "/evidence" : view === "release" ? "/release" : view === "thread" ? "/thread" : "/story";
  const query = view === "story" && at != null ? `?at=${at}` : "";
  return `#/task/${encodeURIComponent(id)}${suffix}${query}`;
}

export function crumbFor(view: ViewId): string {
  if (view === "evidence") return "Evidence";
  if (view === "release") return "Release";
  if (view === "thread") return "Thread";
  return "Story";
}
