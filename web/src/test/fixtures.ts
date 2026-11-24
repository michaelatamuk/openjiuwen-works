import blocked from "../../../tests/contract/fixtures/task-seed-blocked-1.json";
import health from "../../../tests/contract/fixtures/health.json";
import proved from "../../../tests/contract/fixtures/task-seed-proved-1.json";
import released from "../../../tests/contract/fixtures/task-seed-released-1.json";

// The contract fixtures are canonicalized snapshots of the API payloads; the screens only read
// fields, so the masked ids and paths are fine for parity tests.
export const provedDetail: any = proved;
export const releasedDetail: any = released;
export const blockedDetail: any = blocked;
export const builderHealth: any = (health as any).builder;

export function taskRow(overrides: Record<string, any> = {}): any {
  return {
    id: "t-1",
    state: "queued",
    title: "A queued report",
    product: "Fixture",
    source: "manual:GH-1",
    flow: "fix-issue",
    risk: "low",
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}
