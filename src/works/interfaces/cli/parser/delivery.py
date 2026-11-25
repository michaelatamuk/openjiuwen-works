"""`delivery` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.delivery import (
    cmd_confirm,
    cmd_deliver,
    cmd_deploy,
    cmd_release,
)


def add_delivery_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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
    confirm.add_argument("--expect-status", type=int, default=None, help="Expected HTTP status")
    confirm.add_argument(
        "--expect-text", default=None, help="Text that must appear in the response"
    )
    confirm.add_argument(
        "--expect-commit",
        default=None,
        help="Short commit the target must report (fails as wrong_commit)",
    )
    confirm.add_argument(
        "--attempts", type=int, default=1, help="Retries for transient failures (1-3)"
    )
    confirm.add_argument("--close", action="store_true", help="Close the source issue on success")
    confirm.add_argument("--force", action="store_true")
    confirm.add_argument("--json", action="store_true")
    confirm.set_defaults(func=cmd_confirm)
