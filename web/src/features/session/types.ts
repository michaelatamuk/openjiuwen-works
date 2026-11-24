/** Domain types for the session screen. The API payload is loosely typed, so the
 *  screen narrows the parts it reads into these shapes. */

export type ThreadCardOption = {
  action: string;
  label: string;
  tone?: string;
  recommended?: boolean;
};

export type ThreadCardRow = [string, string | number | null | undefined];

export type ThreadCardData = {
  kind?: string;
  prompt?: string;
  rows?: ThreadCardRow[];
  options?: ThreadCardOption[];
};

export type ThreadMessage = {
  seq: number;
  type: string;
  at: string;
  role?: string;
  title?: string;
  body?: string;
  facts?: string[];
  generated?: boolean;
  generated_label?: string;
  stance?: string;
  tone?: string;
  card?: ThreadCardData | null;
};

export type ThreadReviewBlock = { key: string | number; review: ThreadMessage[] };
export type ThreadDividerBlock = { key: string | number; divider: string };
export type ThreadMessageBlock = { key: string | number; message: ThreadMessage };
export type ThreadBlock = ThreadReviewBlock | ThreadDividerBlock | ThreadMessageBlock;

export type PhaseId = "plan" | "build" | "check" | "release";

export type Phase = {
  id: PhaseId;
  label: string;
};

export type PhaseView = Phase & {
  state: string;
  summary: string;
  items: ThreadMessage[];
  blocks: ThreadBlock[];
};

export type SessionMode = "pipeline" | "log";

export type ComposerMode = "ask" | "note";

export type SessionDecision = {
  tone: string;
  label: string;
  text: string;
  action: string | null;
  view?: string;
  button: string;
};

export type SessionSource = {
  kind?: string;
  ref?: string;
  title?: string;
};

export type SessionTask = {
  id: string;
  state: string;
  product?: string;
  flow?: string;
  created_at?: string;
  source: SessionSource;
};

export type RailItem = {
  label: string;
  value?: string | number | null;
  href?: string;
};

export type RailAgent = {
  role: string;
  name?: string;
  detail?: string;
  tone?: string;
};

export type SessionRail = {
  factory?: {
    base_commit?: string | null;
    checks_sha?: string | null;
    flow?: string;
    run?: string | null;
  } | null;
  checks?: RailItem[] | null;
  deliverables?: RailItem[] | null;
  cost?: { usd?: number | null; tokens?: number | null; duration_ms?: number | null } | null;
  people?: Array<string | null | undefined> | null;
  agents?: RailAgent[] | null;
};

export type SessionRelease = {
  released?: boolean;
  ready?: boolean;
  blockers?: string[];
};

export type SessionEvidence = {
  files_changed?: string[];
  verdict?: { outcomes?: Array<{ passed?: boolean }> } | null;
};

export type SessionDetail = {
  task: SessionTask;
  thread?: ThreadMessage[] | null;
  rail?: SessionRail | null;
  release?: SessionRelease | null;
  evidence?: SessionEvidence | null;
  pipeline?: { blocked?: { why?: string } | null } | null;
};
