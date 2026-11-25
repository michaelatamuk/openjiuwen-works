import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

const ROOT = path.resolve(HERE, "../..");
const PORT = Number(process.env.WORKS_E2E_PORT || 8791);
const PYTHON =
  process.env.WORKS_E2E_PYTHON ||
  path.join(
    ROOT,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );

export default async function globalSetup() {
  const home = mkdtempSync(path.join(tmpdir(), "works-e2e-"));
  execFileSync(
    PYTHON,
    [path.join(ROOT, "scripts", "seed_home.py"), "--root", home, "--force"],
    { cwd: ROOT, stdio: "inherit" },
  );
  const child = spawn(
    PYTHON,
    [
      "-m",
      "works",
      "--home",
      home,
      "ui",
      "--port",
      String(PORT),
      "--write",
      "--no-open",
    ],
    { cwd: ROOT, stdio: "ignore", detached: process.platform !== "win32" },
  );
  const readonly = spawn(
    PYTHON,
    ["-m", "works", "--home", home, "ui", "--port", String(PORT + 1), "--no-open"],
    { cwd: ROOT, stdio: "ignore", detached: process.platform !== "win32" },
  );
  const statePath = path.join(HERE, "..", ".e2e-state.json");
  writeFileSync(
    statePath,
    JSON.stringify({ home, port: PORT, pid: child.pid, readonlyPort: PORT + 1, readonlyPid: readonly.pid }),
  );
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${PORT}/api/v1/health`);
      if (response.ok) {
        const token = readFileSync(
          path.join(home, ".works", "state", "http-token"),
          "utf8",
        ).trim();
        const readonlyDeadline = Date.now() + 30_000;
        while (Date.now() < readonlyDeadline) {
          try {
            const readonlyHealth = await fetch(`http://127.0.0.1:${PORT + 1}/api/v1/health`);
            if (readonlyHealth.ok) break;
          } catch {
            // still starting
          }
          await new Promise((resolve) => setTimeout(resolve, 250));
        }
        writeFileSync(
          statePath,
          JSON.stringify({
            home,
            port: PORT,
            pid: child.pid,
            readonlyPort: PORT + 1,
            readonlyPid: readonly.pid,
            token,
          }),
        );
        return;
      }
    } catch {
      // still starting
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("the E2E daemon did not become healthy");
}
