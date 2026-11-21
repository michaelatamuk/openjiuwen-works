# Security policy

## Supported versions

`0.0.x` is a pre-release walking skeleton. Security fixes land on `main`; there are no maintenance
branches yet.

## Reporting a vulnerability

Do **not** open a public issue. Use GitHub's private security advisory for
`michaelatamuk/openjiuwen-works`:

1. Security → Advisories → Report a vulnerability.
2. Include the affected version, a minimal reproduction, and the impact you can demonstrate.

You will get an acknowledgement within 72 hours and a decision within seven days. Credit is given
in the advisory unless you ask otherwise.

## Scope and known limitations

- v0 runs the builder on the host with a pinned working directory, path-escape refusal and an
  environment that drops credential-like variables. **A worktree is not a security boundary**
  (ADR-004): a determined builder can read what the OS user can read.
- Do not point v0 at a repository you do not trust. The container boundary lands in M2 (T2.1).
- Secrets are read from the environment only; they are never written to the workspace, prompts or
  evidence. `sanitize_env` removes names containing `KEY`, `TOKEN`, `SECRET`, `PASSWORD`,
  `PASSWD` or `CREDENTIAL` unless explicitly allowlisted.
- Issue text is data, never instructions. Path enforcement is in `policy.py`, not in a prompt.
- The ledger and event store are append-only by convention and by file locking; they are not
  tamper-evident against the repository owner.

## Out of scope

Denial of service against your own machine, findings that require modifying the workspace files
directly, and issues in dependencies that have no available fix — report those upstream and open a
normal issue if we need to pin or replace the dependency.
