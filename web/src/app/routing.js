export const VIEWS = [
  ["story", "Story"],
  ["evidence", "Evidence"],
  ["release", "Release"],
  ["thread", "Session"],
];

export const VIEW_NAMES = VIEWS.map(([id]) => id);

export function parseHash(hash = location.hash) {
  const match = hash.match(/^#\/task\/([^/?]+)(?:\/(story|evidence|release|thread))?/);
  const query = match ? hash.split("?").slice(1).join("?") : "";
  const at = new URLSearchParams(query).get("at");
  return {
    taskId: match ? decodeURIComponent(match[1]) : null,
    view: match?.[2] || null,
    at: at != null && at !== "" ? Number(at) : null,
  };
}

export function taskHash(id, view, at = null) {
  const suffix = view === "evidence" ? "/evidence" : view === "release" ? "/release" : view === "thread" ? "/thread" : "/story";
  const query = view === "story" && at != null ? `?at=${at}` : "";
  return `#/task/${encodeURIComponent(id)}${suffix}${query}`;
}

export function crumbFor(view) {
  if (view === "evidence") return "Evidence";
  if (view === "release") return "Release";
  if (view === "thread") return "Thread";
  return "Story";
}
