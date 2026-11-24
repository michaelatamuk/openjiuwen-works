"""`intake` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.intake import (
    cmd_source_detector,
    cmd_source_github,
    cmd_source_jira,
    cmd_swarm_doctor,
)
from works.interfaces.cli.commands.team import cmd_team_verify


def add_intake_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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
