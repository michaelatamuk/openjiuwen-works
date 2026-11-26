"""`works proof` — verify, export or compare a proof."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.application.proof import verify
from works.domain.evidence import Evidence, render_summary, summary_digest
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_proof(args: argparse.Namespace) -> int:
    paths = _paths(args)
    if args.action == "summary":
        evidence_path = paths.run_dir(args.run) / "evidence.json"
        if not evidence_path.is_file():
            raise SystemExit(f"no evidence for run {args.run}")
        evidence = Evidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
        derived = not evidence.summary
        text = evidence.summary or render_summary(evidence)
        if args.json:
            _emit({"text": text, "sha256": summary_digest(text), "derived": derived})
        else:
            print(text, end="")
        return 0
    if args.action == "verify":
        result = verify.verify_run(paths, args.run)
        if args.json:
            _emit(result.model_dump(mode="json"))
        else:
            for check in result.checks:
                mark = "ok" if check.ok else "FAIL"
                print(f"{mark:4} {check.name}" + (f" — {check.detail}" if check.detail else ""))
        return 0 if result.ok else 1
    if args.action == "export":
        target = args.out or Path(f"{args.run}.tar.gz")
        exported = verify.export(paths, args.run, target)
        if args.json:
            _emit({"path": str(exported)})
        else:
            print(exported)
        return 0
    if not args.other:
        raise SystemExit("proof diff needs two run ids")
    data = verify.compare(paths, args.run, args.other)
    if args.json:
        _emit(data)
    else:
        print(f"verdict: {data['verdict'][0]} -> {data['verdict'][1]}")
        print(f"risk: {data['risk'][0]} -> {data['risk'][1]}")
        print(f"tokens: {data['tokens'][0]} -> {data['tokens'][1]}")
        print(f"usd: {data['usd'][0]} -> {data['usd'][1]}")
        print(f"files changed: {', '.join(data['files']) or 'none'}")
    return 0
