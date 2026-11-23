import ast
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src" / "works"

MOVES = {
    "config.py": "config/paths.py",
    "settings.py": "application/settings.py",
    "logs.py": "config/logging.py",
    "schema.py": "application/schema.py",
    "bootstrap.py": "config/bootstrap.py",
    "errors.py": "domain/errors.py",
    "state.py": "domain/state.py",
    "records.py": "domain/records.py",
    "evidence.py": "domain/evidence.py",
    "risk.py": "domain/risk.py",
    "policy.py": "domain/policy.py",
    "flow.py": "domain/flow.py",
    "trusted.py": "domain/trusted.py",
    "supervisor.py": "application/supervisor.py",
    "planner.py": "application/planning/service.py",
    "plan_eval.py": "application/planning/eval.py",
    "plan_memory.py": "application/planning/memory.py",
    "approvals.py": "application/approvals/gates.py",
    "decision.py": "application/approvals/decisions.py",
    "decision_eval.py": "application/approvals/eval.py",
    "readiness.py": "application/execution/readiness.py",
    "preview.py": "application/execution/preview.py",
    "artifacts.py": "application/execution/artifacts.py",
    "quarantine.py": "application/execution/quarantine.py",
    "verifier.py": "application/execution/verifier.py",
    "scenarios.py": "application/execution/scenarios.py",
    "flakes.py": "application/execution/flakes.py",
    "deliver.py": "application/delivery/deliver.py",
    "deploy.py": "application/delivery/deploy.py",
    "confirm.py": "application/delivery/confirm.py",
    "release.py": "application/delivery/release.py",
    "forge.py": "application/delivery/forge.py",
    "tracker.py": "application/delivery/tracker.py",
    "sources.py": "application/intake/sources.py",
    "detectors.py": "application/intake/detectors.py",
    "products.py": "application/intake/products.py",
    "memory.py": "application/memory/ppma.py",
    "memory_ops.py": "application/memory/backfill.py",
    "agent_chat.py": "application/assistant/chat.py",
    "team_task.py": "application/team/launcher.py",
    "team_verify.py": "application/team/verify.py",
    "metrics.py": "application/observability/metrics.py",
    "escapes.py": "application/observability/escapes.py",
    "features.py": "application/observability/features.py",
    "doctor.py": "application/doctor.py",
    "render.py": "interfaces/cli/render.py",
    "cli.py": "interfaces/cli/main.py",
    "ui/server.py": "interfaces/api/server.py",
    "gitops.py": "adapters/git/repo.py",
    "queue.py": "adapters/queue/store.py",
    "index.py": "adapters/queue/index.py",
    "fast.py": "adapters/queue/fast_read.py",
    "migrations.py": "adapters/queue/migrations.py",
    "ledger.py": "adapters/queue/ledger.py",
    "runner.py": "adapters/processes/runner.py",
    "harness/base.py": "adapters/harness/base.py",
    "harness/fake.py": "adapters/harness/fake.py",
    "harness/usage.py": "adapters/harness/usage.py",
    "harness/providers.py": "adapters/harness/openjiuwen/providers.py",
    "harness/openjiuwen.py": "adapters/harness/openjiuwen/builder.py",
    "harness/planner.py": "adapters/harness/openjiuwen/planner.py",
    "harness/swarm.py": "adapters/harness/swarm/harness.py",
}

PACKAGES = (
    "config",
    "domain",
    "application",
    "application/planning",
    "application/execution",
    "application/approvals",
    "application/delivery",
    "application/intake",
    "application/memory",
    "application/assistant",
    "application/team",
    "application/observability",
    "adapters",
    "adapters/git",
    "adapters/queue",
    "adapters/processes",
    "adapters/harness",
    "adapters/harness/openjiuwen",
    "adapters/harness/swarm",
    "interfaces",
    "interfaces/cli",
    "interfaces/api",
    "interfaces/ui",
)


def module_name(relative: str) -> str:
    path = pathlib.Path(relative)
    parts = list(path.with_suffix("").parts)
    return "works." + ".".join(parts)


def ensure_packages() -> None:
    for package in PACKAGES:
        directory = SRC / package
        directory.mkdir(parents=True, exist_ok=True)
        init = directory / "__init__.py"
        if not init.exists():
            init.write_text('"""Works package."""\n', encoding="utf-8")


def char_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def alias_text(alias: ast.alias) -> str:
    return f"{alias.name} as {alias.asname}" if alias.asname else alias.name


def transform_imports(source: str, old_module: str, mapping: dict[str, str]) -> str:
    tree = ast.parse(source)
    offsets = char_offsets(source)
    replacements: list[tuple[int, int, str]] = []

    def position(line: int, column: int) -> int:
        return offsets[line - 1] + column

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                parts = old_module.split(".")
                if node.level > len(parts):
                    continue
                base = parts[: len(parts) - node.level]
                if node.module:
                    base += node.module.split(".")
                old_target = ".".join(base)
            else:
                old_target = node.module or ""
            new_target = mapping.get(old_target, old_target)
            if node.level == 0 and new_target == old_target:
                continue
            if node.module is None and node.level:
                lines: list[str] = []
                for alias in node.names:
                    target = f"{old_target}.{alias.name}" if old_target else alias.name
                    target_new = mapping.get(target, target)
                    if target_new != target:
                        lines.append(f"from {target_new} import {alias_text(alias)}")
                    else:
                        lines.append(f"from {old_target} import {alias_text(alias)}")
                replacement = "\n".join(lines)
            else:
                names = ", ".join(alias_text(alias) for alias in node.names)
                replacement = f"from {new_target} import {names}"
            start = position(node.lineno, node.col_offset)
            end = position(node.end_lineno, node.end_col_offset)
            replacements.append((start, end, replacement))
        elif isinstance(node, ast.Import):
            names: list[str] = []
            changed = False
            for alias in node.names:
                new_name = mapping.get(alias.name, alias.name)
                changed = changed or new_name != alias.name
                names.append(f"{new_name} as {alias.asname}" if alias.asname else new_name)
            if not changed:
                continue
            start = position(node.lineno, node.col_offset)
            end = position(node.end_lineno, node.end_col_offset)
            replacements.append((start, end, "import " + ", ".join(names)))

    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def main() -> None:
    ensure_packages()
    mapping: dict[str, str] = {
        module_name(old): module_name(new) for old, new in MOVES.items()
    }
    for old, new in MOVES.items():
        old_path = SRC / old
        new_path = SRC / new
        if not old_path.exists():
            raise SystemExit(f"missing {old_path}")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", str(old_path), str(new_path)], check=True, cwd=ROOT)
        old_module = module_name(old)
        content = new_path.read_text(encoding="utf-8")
        content = transform_imports(content, old_module, mapping)
        new_path.write_text(content, encoding="utf-8")

    # The old config module is replaced by the config package; no shim can coexist.
    legacy = {
        old: new
        for old, new in MOVES.items()
        if old not in ("config.py", "ui/server.py")
    }
    for old, new in legacy.items():
        old_path = SRC / old
        old_module = module_name(old)
        new_module = module_name(new)
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text(
            f'"""Deprecated import path; use {new_module}."""\n'
            f"from {new_module} import *  # noqa: F401,F403\n",
            encoding="utf-8",
        )
    # The built assets belong to the interface layer.
    static_old = SRC / "ui" / "static"
    static_new = SRC / "interfaces" / "ui" / "static"
    if static_old.exists():
        static_new.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", str(static_old), str(static_new)], check=True, cwd=ROOT)
    # Keep the old ui.server import path for the tests and external callers.
    (SRC / "ui" / "server.py").write_text(
        '"""Deprecated import path; use works.interfaces.api.server."""\n'
        "from works.interfaces.api.server import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )
    # config is a package now; expose the old module names from it.
    config_init = SRC / "config" / "__init__.py"
    config_init.write_text(
        '"""Workspace paths and runtime configuration."""\n'
        "from .paths import WorksPaths, load_paths, resolve_root\n\n"
        "__all__ = [\"WorksPaths\", \"load_paths\", \"resolve_root\"]\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
    print("moved", len(MOVES), "modules")
