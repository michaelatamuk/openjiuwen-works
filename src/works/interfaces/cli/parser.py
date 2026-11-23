"""Argument parser for every CLI command."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.common import DESCRIPTION
from works.interfaces.cli.commands.delivery import (
    cmd_confirm,
    cmd_deliver,
    cmd_deploy,
    cmd_release,
)
from works.interfaces.cli.commands.inspect import (
    cmd_decision_replay,
    cmd_doctor,
    cmd_escapes,
    cmd_flake_add,
    cmd_flake_list,
    cmd_gate_list,
    cmd_gate_report,
    cmd_ledger,
    cmd_metrics,
    cmd_policy_check,
    cmd_readiness,
    cmd_risk,
    cmd_schema,
)
from works.interfaces.cli.commands.intake import (
    cmd_source_detector,
    cmd_source_github,
    cmd_source_jira,
    cmd_swarm_doctor,
)
from works.interfaces.cli.commands.memory import (
    cmd_memory_backfill,
    cmd_memory_recall,
)
from works.interfaces.cli.commands.plan import cmd_approve, cmd_plan
from works.interfaces.cli.commands.run import (
    cmd_dispatch,
    cmd_run,
    cmd_wait,
    cmd_wake,
)
from works.interfaces.cli.commands.tasks import (
    cmd_finding_add,
    cmd_finding_list,
    cmd_status,
    cmd_submit,
    cmd_task,
    cmd_trace,
    cmd_version,
)
from works.interfaces.cli.commands.team import cmd_team_verify
from works.interfaces.cli.commands.ui import cmd_ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="works", description=DESCRIPTION)
    parser.add_argument("--home", type=Path, default=None, help="Workspace root")
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="Print the version")
    version.add_argument("--json", action="store_true")
    version.set_defaults(func=cmd_version)

    submit = sub.add_parser("submit", help="Submit a signal; duplicate sources return one task")
    submit.add_argument("--ref", "-r", required=True, help="Source reference, e.g. GH-42")
    submit.add_argument("--title", "-t", default="", help="One-line title")
    submit.add_argument("--flow", default="fix-issue")
    submit.add_argument("--product", default="openjiuwen")
    submit.add_argument("--repo", type=Path, default=None)
    submit.add_argument("--kind", default="manual", help="manual, tracker or detector")
    submit.add_argument(
        "--task-kind",
        default="fix",
        choices=("fix", "check-change"),
        help="fix or check-change",
    )
    submit.add_argument("--json", action="store_true")
    submit.set_defaults(func=cmd_submit)

    source = sub.add_parser("source", help="Read a tracker and queue its open issues")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_github = source_sub.add_parser("github", help="GitHub Issues intake")
    source_github.add_argument("repository", help="owner/name")
    source_github.add_argument("--product", required=True)
    source_github.add_argument("--repo", type=Path, default=None)
    source_github.add_argument("--label", default=None)
    source_github.add_argument("--limit", type=int, default=20)
    source_github.add_argument("--json", action="store_true")
    source_github.set_defaults(func=cmd_source_github)
    source_jira = source_sub.add_parser("jira", help="Jira JQL intake")
    source_jira.add_argument("--url", required=True, help="Jira base URL")
    source_jira.add_argument("--jql", required=True)
    source_jira.add_argument("--product", required=True)
    source_jira.add_argument("--repo", type=Path, default=None)
    source_jira.add_argument("--limit", type=int, default=20)
    source_jira.add_argument("--json", action="store_true")
    source_jira.set_defaults(func=cmd_source_jira)
    source_detector = source_sub.add_parser("detector", help="Firing alerts into the queue")
    detector_target = source_detector.add_mutually_exclusive_group(required=True)
    detector_target.add_argument("--name", default=None, help="Configured detector name")
    detector_target.add_argument("--file", default=None, help="JSON or NDJSON alert file")
    detector_target.add_argument("--url", default=None, help="Alertmanager-style endpoint")
    source_detector.add_argument("--product", default=None)
    source_detector.add_argument("--repo", type=Path, default=None)
    source_detector.add_argument("--limit", type=int, default=50)
    source_detector.add_argument("--json", action="store_true")
    source_detector.set_defaults(func=cmd_source_detector)

    status = sub.add_parser("status", help="Show one task or the queue")
    status.add_argument("task_id", nargs="?", default=None)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    task = sub.add_parser("task", help="Print the task projection")
    task.add_argument("task_id")
    task.add_argument("--json", action="store_true")
    task.set_defaults(func=cmd_task)

    trace = sub.add_parser("trace", help="Render the event timeline")
    trace.add_argument("task_id")
    trace.add_argument("--json", action="store_true")
    trace.set_defaults(func=cmd_trace)

    plan = sub.add_parser("plan", help="Draft, show, lint or diff versioned plans")
    plan.add_argument("task_id")
    plan.add_argument("--action", choices=("draft", "show", "lint", "diff"), default="draft")
    plan.add_argument("--scenarios", default=None)
    plan.add_argument("--version", type=int, default=None)
    plan.add_argument("--from", dest="from_version", type=int, default=None)
    plan.add_argument("--to", dest="to_version", type=int, default=None)
    plan.add_argument(
        "--mode",
        choices=("deterministic", "shadow", "assisted", "deep", "spec", "auto"),
        default=None,
    )
    plan.add_argument("--model", default=None)
    plan.add_argument("--model-base", default=None)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)

    approve = sub.add_parser("approve", help="Approve the plan gate")
    approve.add_argument("task_id")
    approve.add_argument("--gate", default="plan", help="plan or release")
    approve.add_argument("--plan", default=None, help="Plan id to approve (default: latest)")
    approve.add_argument("--plan-hash", default=None, help="Exact plan hash to approve")
    approve.add_argument("--json", action="store_true")
    approve.set_defaults(func=cmd_approve)

    release = sub.add_parser("release", help="Build the read-only release packet")
    release.add_argument("task_id")
    release.add_argument("--json", action="store_true")
    release.set_defaults(func=cmd_release)

    deliver = sub.add_parser("deliver", help="Push the released change and open a pull request")
    deliver.add_argument("task_id")
    deliver.add_argument("--remote", default="origin")
    deliver.add_argument("--base", default="main", help="Pull-request base branch")
    deliver.add_argument("--provider", choices=("none", "github", "gitlab"), default="none")
    deliver.add_argument("--tracker", choices=("none", "github", "gitlab", "jira"), default=None)
    deliver.add_argument("--dry-run", action="store_true")
    deliver.add_argument("--json", action="store_true")
    deliver.set_defaults(func=cmd_deliver)

    deploy = sub.add_parser("deploy", help="Run the owner-approved deploy command")
    deploy.add_argument("task_id")
    deploy.add_argument("--command", default=None, help="Deploy command or JSON argv array")
    deploy.add_argument("--environment", default="staging", help="Target environment name")
    deploy.add_argument("--dry-run", action="store_true")
    deploy.add_argument("--force", action="store_true", help="Repeat a recorded deploy")
    deploy.add_argument("--json", action="store_true")
    deploy.set_defaults(func=cmd_deploy)

    confirm = sub.add_parser("confirm", help="Re-check the released commit and close the loop")
    confirm.add_argument("task_id")
    target = confirm.add_mutually_exclusive_group()
    target.add_argument("--url", default=None, help="HTTP endpoint to check")
    target.add_argument("--command", default=None, help="Command to run in a fresh worktree")
    target.add_argument("--preview", default=None, help="Playwright preview script (YAML)")
    confirm.add_argument("--provider", choices=("none", "github", "gitlab", "jira"), default="none")
    confirm.add_argument("--tracker", choices=("none", "github", "gitlab", "jira"), default=None)
    confirm.add_argument("--close", action="store_true", help="Close the source issue on success")
    confirm.add_argument("--force", action="store_true")
    confirm.add_argument("--json", action="store_true")
    confirm.set_defaults(func=cmd_confirm)

    team = sub.add_parser("team", help="Run the agent-core verification team")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    team_verify = team_sub.add_parser("verify", help="Inspector + challenger + reporter")
    team_verify.add_argument("task_id")
    team_verify.add_argument("--json", action="store_true")
    team_verify.set_defaults(func=cmd_team_verify)

    swarm = sub.add_parser("swarm", help="Check the JiuwenSwarm builder boundary")
    swarm_sub = swarm.add_subparsers(dest="swarm_command", required=True)
    swarm_doctor = swarm_sub.add_parser("doctor", help="Preflight the isolated builder")
    swarm_doctor.add_argument("--python", default=None)
    swarm_doctor.add_argument("--home", default=None)
    swarm_doctor.add_argument("--json", action="store_true")
    swarm_doctor.set_defaults(func=cmd_swarm_doctor)

    run = sub.add_parser("run", help="Reproduce, plan, build, check, prove")
    run.add_argument("task_id")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--approve-plan", action="store_true")
    run.add_argument("--scenarios", default=None)
    run.add_argument("--quarantine", default=None)
    run.add_argument("--trace", type=Path, default=None)
    run.add_argument("--live", action="store_true")
    run.add_argument("--swarm", action="store_true")
    run.add_argument("--swarm-python", default=None)
    run.add_argument("--swarm-home", default=None)
    run.add_argument("--model", default=None)
    run.add_argument("--model-base", default=None)
    run.add_argument("--prompt", type=Path, default=None)
    run.add_argument("--ppma", default=None)
    run.add_argument("--ppma-space", default="me")
    run.add_argument("--decision", choices=("off", "shadow", "laix"), default=None)
    run.add_argument("--verifier", choices=("local", "docker"), default="local")
    run.add_argument("--verifier-image", default=None)
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    wait = sub.add_parser("wait", help="Put a task into a waiting state")
    wait.add_argument("task_id")
    wait.add_argument("--on", choices=("review", "ci", "deploy"), required=True)
    wait.add_argument("--wake-on", required=True)
    wait.add_argument("--deadline", default=None)
    wait.add_argument("--next", default=None)
    wait.add_argument("--default", default=None)
    wait.add_argument("--json", action="store_true")
    wait.set_defaults(func=cmd_wait)

    wake = sub.add_parser("wake", help="Wake a waiting task on its event")
    wake.add_argument("task_id")
    wake.add_argument("--event", required=True)
    wake.add_argument("--json", action="store_true")
    wake.set_defaults(func=cmd_wake)

    dispatch = sub.add_parser("dispatch", help="Claim and run ready tasks")
    dispatch.add_argument("--limit", type=int, default=10)
    dispatch.add_argument("--watch", action="store_true")
    dispatch.add_argument("--interval", type=int, default=10)
    dispatch.add_argument("--approve-plan", action="store_true")
    dispatch.add_argument("--scenarios", default=None)
    dispatch.add_argument("--quarantine", default=None)
    dispatch.add_argument("--trace", type=Path, default=None)
    dispatch.add_argument("--live", action="store_true")
    dispatch.add_argument("--swarm", action="store_true")
    dispatch.add_argument("--swarm-python", default=None)
    dispatch.add_argument("--swarm-home", default=None)
    dispatch.add_argument("--model", default=None)
    dispatch.add_argument("--model-base", default=None)
    dispatch.add_argument("--prompt", type=Path, default=None)
    dispatch.add_argument("--ppma", default=None)
    dispatch.add_argument("--ppma-space", default="me")
    dispatch.add_argument("--decision", choices=("off", "shadow", "laix"), default=None)
    dispatch.add_argument("--verifier", choices=("local", "docker"), default="local")
    dispatch.add_argument("--verifier-image", default=None)
    dispatch.add_argument("--json", action="store_true")
    dispatch.set_defaults(func=cmd_dispatch)

    policy = sub.add_parser("policy", help="Path policy")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    check = policy_sub.add_parser("check", help="Check paths before any command runs")
    check.add_argument("paths", nargs="+")
    check.add_argument("--flow", default=None)
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_policy_check)

    ledger = sub.add_parser("ledger", help="Read the append-only ledger")
    ledger.add_argument("--json", action="store_true")
    ledger.set_defaults(func=cmd_ledger)

    finding = sub.add_parser("finding", help="Structured findings for a task")
    finding_sub = finding.add_subparsers(dest="finding_command", required=True)
    finding_add = finding_sub.add_parser("add", help="Record a finding")
    finding_add.add_argument("task_id")
    finding_add.add_argument("--summary", required=True)
    finding_add.add_argument("--step", default="")
    finding_add.add_argument("--confidence", default=None)
    finding_add.add_argument("--uncertainty", default="")
    finding_add.add_argument("--evidence", action="append", default=[])
    finding_add.add_argument("--json", action="store_true")
    finding_add.set_defaults(func=cmd_finding_add)
    finding_list = finding_sub.add_parser("list", help="List findings")
    finding_list.add_argument("task_id")
    finding_list.add_argument("--json", action="store_true")
    finding_list.set_defaults(func=cmd_finding_list)

    metrics = sub.add_parser("metrics", help="Attention and cost metrics")
    metrics.add_argument("--json", action="store_true")
    metrics.set_defaults(func=cmd_metrics)

    escapes = sub.add_parser("escapes", help="Attribute reverts, hotfixes and repeated work")
    escapes.add_argument("--days", type=int, default=14)
    escapes.add_argument("--dry-run", action="store_true", help="Scan without writing the report")
    escapes.add_argument("--json", action="store_true")
    escapes.set_defaults(func=cmd_escapes)

    memory = sub.add_parser("memory", help="PPMA memory tools")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    backfill = memory_sub.add_parser("backfill", help="Report already-finished runs to PPMA")
    backfill.add_argument("--ppma", default=None, help="PPMA base URL")
    backfill.add_argument("--space", default="me")
    backfill.add_argument("--limit", type=int, default=None)
    backfill.add_argument("--task", default=None)
    backfill.add_argument("--since", default=None)
    backfill.add_argument("--dry-run", action="store_true")
    backfill.add_argument("--json", action="store_true")
    backfill.set_defaults(func=cmd_memory_backfill)
    recall = memory_sub.add_parser("recall", help="Read PPMA memory statements")
    recall.add_argument("--ppma", default=None, help="PPMA base URL")
    recall.add_argument("--space", default="me")
    recall.add_argument("--view", default="about_me")
    recall.add_argument("--limit", type=int, default=8)
    recall.add_argument("--json", action="store_true")
    recall.set_defaults(func=cmd_memory_recall)

    risk = sub.add_parser("risk", help="Show the latest risk rating")
    risk.add_argument("task_id")
    risk.add_argument("--json", action="store_true")
    risk.set_defaults(func=cmd_risk)

    gate = sub.add_parser("gate", help="Inspect gate decisions and observe-mode blocks")
    gate_sub = gate.add_subparsers(dest="gate_command", required=True)
    gate_list = gate_sub.add_parser("list", help="List decisions for a task")
    gate_list.add_argument("task_id")
    gate_list.add_argument("--json", action="store_true")
    gate_list.set_defaults(func=cmd_gate_list)
    gate_report = gate_sub.add_parser("report", help="Summarize decisions and observe blocks")
    gate_report.add_argument("task_id", nargs="?", default=None)
    gate_report.add_argument("--json", action="store_true")
    gate_report.set_defaults(func=cmd_gate_report)

    flake = sub.add_parser("flake", help="Flaky tests are defects with an owner and an expiry")
    flake_sub = flake.add_subparsers(dest="flake_command", required=True)
    flake_add = flake_sub.add_parser("add", help="Record a flake")
    flake_add.add_argument("task_id")
    flake_add.add_argument("--scenario", required=True)
    flake_add.add_argument("--owner", required=True)
    flake_add.add_argument("--reason", required=True)
    flake_add.add_argument("--days", type=int, default=14)
    flake_add.add_argument("--json", action="store_true")
    flake_add.set_defaults(func=cmd_flake_add)
    flake_list = flake_sub.add_parser("list", help="List flakes")
    flake_list.add_argument("--active", action="store_true")
    flake_list.add_argument("--json", action="store_true")
    flake_list.set_defaults(func=cmd_flake_list)

    decision = sub.add_parser("decision", help="Replay historical gate cases")
    decision_sub = decision.add_subparsers(dest="decision_command", required=True)
    decision_replay = decision_sub.add_parser(
        "replay", help="Compare a candidate policy with the rule"
    )
    decision_replay.add_argument("--cases", required=True)
    decision_replay.add_argument("--provider", choices=("off", "shadow", "laix"), default="laix")
    decision_replay.add_argument("--json", action="store_true")
    decision_replay.set_defaults(func=cmd_decision_replay)

    ui = sub.add_parser("ui", help="Open the read-only preview window")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--read-only", action="store_true", help="Only supported mode")
    ui.add_argument("--write", action="store_true", help="Not implemented")
    ui.add_argument("--no-open", action="store_true", help="Do not open a browser")
    ui.add_argument("--json", action="store_true")
    ui.set_defaults(func=cmd_ui)

    schema = sub.add_parser("schema", help="Print every persisted schema")
    schema.add_argument("--json", action="store_true")
    schema.set_defaults(func=cmd_schema)

    doctor = sub.add_parser("doctor", help="Check config, git, harness, container, credentials")
    doctor.add_argument("--repo", type=Path, default=None)
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    readiness = sub.add_parser(
        "readiness", help="Decide whether a repository is ready for autonomous work"
    )
    readiness.add_argument("--repo", type=Path, default=None)
    readiness.add_argument("--no-run", action="store_true", help="Static checks only")
    readiness.add_argument("--timeout", type=int, default=120)
    readiness.add_argument("--json", action="store_true")
    readiness.set_defaults(func=cmd_readiness)
    return parser
