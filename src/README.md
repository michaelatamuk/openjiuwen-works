# src

The engine lives here. The window is a separate app, built only after M2, against the GUI
standard in the plan (§6.5).

```
src/works/
  cli.py           argparse commands, JSON output, exit codes
  bootstrap.py     startup hygiene (drops the working directory from sys.path)
  config.py        workspace paths, WORKS_HOME, directory creation
  records.py       persisted models, schema_version, enums
  state.py         the task state machine; every legal edge
  queue.py         append-only events, projection, replay, claims, idempotency
  index.py         derived SQLite index for fast status
  fast.py          stdlib-only read path used by status
  flow.py          flows as acyclic node graphs; gates, repair, paths
  policy.py        path policy; deny wins; test paths denied by default
  scenarios.py     scenario sets, P0/P1 weights, the verdict rule
  supervisor.py    reproduce -> plan -> build -> test -> scenarios -> proof
  evidence.py      computed proof page bound to the diff by SHA-256
  ledger.py        append-only ledger, one row per finished run
  runner.py        subprocess execution, timeout, process-tree kill, env sanitising
  gitops.py        typed git: worktree, apply, diff, diffstat
  harness/         the builder port and the replaying fake harness
  quarantine.py    lists that must live outside the repository
  doctor.py        environment checks
  schema.py        every persisted JSON Schema
  migrations.py    schema bumps with tested old fixtures
  logs.py          structured JSON logs on stderr
  render.py        plain-text tables without a CLI framework
```

The engine is the only component that decides what happens next. It calls the other products —
it does not modify them. Domain types never import infrastructure; the supervisor receives a
queue, a ledger, a harness and a command runner rather than constructing them.
