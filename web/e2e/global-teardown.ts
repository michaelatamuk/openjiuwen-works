import { execFileSync } from "node:child_process";
import { readFileSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

export default async function globalTeardown() {
  const statePath = path.join(HERE, "..", ".e2e-state.json");
  let state: { home?: string; pid?: number; readonlyPid?: number } = {};
  try {
    state = JSON.parse(readFileSync(statePath, "utf8"));
  } catch {
    return;
  }
  if (state.pid) {
    if (process.platform === "win32") {
      try {
        execFileSync("taskkill", ["/PID", String(state.pid), "/T", "/F"], {
          stdio: "ignore",
        });
      } catch {
        // already gone
      }
    } else {
      try {
        process.kill(-state.pid, "SIGKILL");
      } catch {
        // already gone
      }
    }
  }
  if (state.readonlyPid) {
    try {
      process.kill(state.readonlyPid, "SIGKILL");
    } catch {
      // already gone
    }
  }
  if (state.home) rmSync(state.home, { recursive: true, force: true });
  rmSync(statePath, { force: true });
}
