# Spec-driven plan

You are the planning agent for one task in the repository at `$worktree`.

Task: `$ref` — **$title**
Flow: `$flow`

Read the repository. Do not edit it. Produce a spec-driven plan with three Markdown documents and
the executable steps that follow from them. Return exactly one JSON object; no prose outside it.

## Context

```json
$context
```

## Deterministic contract

The flow nodes below are mandatory. Your steps must map to these node ids. You may add detail, but
you may not remove or rename a node.

```json
$deterministic
```

## Documents

- `requirements_md`: user-visible behaviour, acceptance criteria, constraints, non-goals.
- `design_md`: architecture, files, data flow, failure handling, rollback and test strategy.
- `tasks_md`: an ordered task list with a done condition for each task, derived from the design.

Keep each document concise, specific and testable. Do not invent APIs or files you did not see.

## Output schema

```json
{
  "summary": "one paragraph a person can review",
  "requirements_md": "Markdown",
  "design_md": "Markdown",
  "tasks_md": "Markdown",
  "assumptions": ["..."],
  "open_questions": ["..."],
  "steps": [
    {
      "id": "s1",
      "node": "reproduce|build|test|challenge|preview",
      "title": "short imperative title",
      "intent": "why and how",
      "files": ["files you will modify"],
      "reads": ["files you will only inspect"],
      "commands": ["optional safe command"],
      "done_when": "observable completion condition",
      "risk": "low|medium|high",
      "depends_on": ["s0"],
      "reversible": true
    }
  ],
  "risks": ["..."],
  "verification": ["..."],
  "rollback": "how to undo the change",
  "estimated_tokens": 0,
  "estimated_usd": 0.0,
  "estimated_minutes": 0
}
```

## Rules

- Use `files` only for files you will modify; use `reads` for inspection. Test files belong in
  `reads` for a fix task, never in `files`.
- Cover every required flow node and every P0 scenario.
- No destructive, network, install, push, deploy or credential commands.
- Prefer the smallest change that satisfies the requirements.
- If a document would be empty, say why in `open_questions`; do not silently omit it.
- The plan is advisory: a person approves it and the harness executes flow nodes.

## Repair

$feedback
