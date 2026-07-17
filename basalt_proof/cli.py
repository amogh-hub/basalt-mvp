from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .autofix import write_fix_bundle
from .compare import write_before_after_artifacts
from .config import infer_commands, infer_project_type, load_config, render_default_config
from .context_compiler import compile_context_for_repo
from .dashboard import write_dashboard
from .git_pr import write_pr_pack
from .knowledge_graph import (
    GraphStore,
    analyze_impact,
    build_project_graph,
    check_graph_freshness,
    query_graph,
    render_impact_markdown,
    write_graph_artifacts,
)
from .models import GeneratedArtifact
from .proof import verify_repo
from .report import write_json_report, write_markdown_report
from .runner import docker_status


PRODUCT_NAME = "Basalt v2.1 Alpha Knowledge Platform"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="basalt", description=PRODUCT_NAME)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    verify = subparsers.add_parser("verify", help="Verify a repository and generate proof evidence")
    verify.add_argument("repo", type=Path, help="Path to repository to verify")
    verify.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to <repo>/.basalt")
    verify.add_argument(
        "--sandbox",
        choices=["auto", "temp", "docker"],
        default=None,
        help="Execution sandbox. auto prefers Docker and safely falls back when permitted.",
    )
    verify.add_argument("--keep-workspace", action="store_true", help="Keep temporary workspace for debugging")
    verify.add_argument("--no-dashboard", action="store_true", help="Do not generate Command Center dashboard")

    init = subparsers.add_parser("init", help="Create a basalt.yaml in a repository")
    init.add_argument("repo", type=Path, nargs="?", default=Path("."), help="Repository path")
    init.add_argument(
        "--type",
        choices=["python", "fastapi", "node", "react", "vite-react", "nextjs"],
        default=None,
        help="Project type",
    )
    init.add_argument("--name", default=None, help="Project name")
    init.add_argument("--force", action="store_true", help="Overwrite an existing basalt.yaml")

    inspect = subparsers.add_parser("inspect", help="Show detected project type, commands, and sandbox policy")
    inspect.add_argument("repo", type=Path, nargs="?", default=Path("."), help="Repository path")
    inspect.add_argument("--json", action="store_true", help="Output JSON")

    fix = subparsers.add_parser("fix", help="Generate/apply additive proof-hardening fixes")
    fix.add_argument("repo", type=Path, help="Path to repository to fix")
    fix.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to <repo>/.basalt")
    fix.add_argument("--apply", action="store_true", help="Apply generated additive tests")
    fix.add_argument("--rerun", action="store_true", help="After --apply, rerun verification")
    fix.add_argument("--sandbox", choices=["auto", "temp", "docker"], default=None)
    fix.add_argument("--keep-workspace", action="store_true")

    pr = subparsers.add_parser("pr", help="Generate a GitHub PR-ready evidence pack")
    pr.add_argument("repo", type=Path, help="Path to repository")
    pr.add_argument("--out", type=Path, default=None)
    pr.add_argument("--branch", default=None)
    pr.add_argument("--create-branch", action="store_true")
    pr.add_argument("--commit", action="store_true")
    pr.add_argument("--remote", default="origin")
    pr.add_argument("--sandbox", choices=["auto", "temp", "docker"], default=None)

    demo = subparsers.add_parser("demo", help="Run the alpha proof demo flow")
    demo.add_argument("--out", type=Path, default=Path("basalt-demo-run"))
    demo.add_argument("--sandbox", choices=["auto", "temp", "docker"], default="temp")

    doctor = subparsers.add_parser("doctor", help="Check the local Basalt environment")
    doctor.add_argument("--json", action="store_true")

    explain = subparsers.add_parser("explain", help="Summarize an existing proof-report.json")
    explain.add_argument("report", type=Path)

    graph = subparsers.add_parser("graph", help="Build, inspect, and query the AST-anchored Project Knowledge Graph")
    graph_commands = graph.add_subparsers(dest="graph_command")
    graph_build = graph_commands.add_parser("build", help="Build or refresh the persistent project graph")
    graph_build.add_argument("repo", type=Path, nargs="?", default=Path("."))
    graph_build.add_argument("--out", type=Path, default=None)
    graph_build.add_argument("--force", action="store_true")
    graph_build.add_argument("--json", action="store_true")
    graph_status = graph_commands.add_parser("status", help="Check graph freshness against current files")
    graph_status.add_argument("repo", type=Path, nargs="?", default=Path("."))
    graph_status.add_argument("--out", type=Path, default=None)
    graph_status.add_argument("--json", action="store_true")
    graph_query = graph_commands.add_parser("query", help="Search files, symbols, and features")
    graph_query.add_argument("repo", type=Path)
    graph_query.add_argument("term")
    graph_query.add_argument("--kind", default=None)
    graph_query.add_argument("--limit", type=int, default=50)
    graph_query.add_argument("--out", type=Path, default=None)
    graph_query.add_argument("--json", action="store_true")

    impact = subparsers.add_parser("impact", help="Analyze downstream impact of a file, symbol, route, or feature")
    impact.add_argument("repo", type=Path)
    impact.add_argument("target")
    impact.add_argument("--depth", type=int, default=3)
    impact.add_argument("--out", type=Path, default=None)
    impact.add_argument("--json", action="store_true")

    context = subparsers.add_parser("context", help="Compile a minimal task-specific context pack")
    context.add_argument("repo", type=Path)
    context.add_argument("--task", required=True)
    context.add_argument("--role", default="CodeReviewAgent")
    context.add_argument("--target", action="append", default=[])
    context.add_argument("--budget", type=int, default=None)
    context.add_argument("--out", type=Path, default=None)
    context.add_argument("--no-refresh", action="store_true")
    context.add_argument("--json", action="store_true")
    return parser


def _write_report_artifacts(report, out_dir: Path, no_dashboard: bool = False):
    json_path = out_dir / "proof-report.json"
    md_path = out_dir / "proof-report.md"
    write_json_report(report, json_path)
    write_markdown_report(report, md_path)
    existing_paths = {artifact.path for artifact in report.artifacts}
    for artifact in [
        GeneratedArtifact("Proof Report JSON", str(json_path), "Machine-readable proof evidence"),
        GeneratedArtifact("Proof Report Markdown", str(md_path), "Human-readable proof report"),
    ]:
        if artifact.path not in existing_paths:
            report.artifacts.append(artifact)
            existing_paths.add(artifact.path)
    dashboard_path = None
    if not no_dashboard:
        dashboard_path = out_dir / "basalt-dashboard.html"
        report.dashboard_path = str(dashboard_path)
        artifact = GeneratedArtifact(
            "Command Center Dashboard",
            str(dashboard_path),
            "Browser-viewable proof dashboard",
        )
        if artifact.path not in existing_paths:
            report.artifacts.append(artifact)
        write_json_report(report, json_path)
        write_markdown_report(report, md_path)
        write_dashboard(report, dashboard_path)
    return json_path, md_path, dashboard_path


def _print_report_result(report, artifacts: list[Path | str]) -> None:
    print(PRODUCT_NAME)
    print(f"Project: {report.project_name}")
    print(f"Final Status: {report.final_status.value}")
    print(f"Proof Score: {report.score}/100")
    print(f"Sandbox: {report.sandbox} (requested: {report.sandbox_requested})")
    if report.sandbox_fallback_reason:
        print(f"Sandbox fallback: {report.sandbox_fallback_reason}")
    print("Artifacts written:")
    for artifact in artifacts:
        if artifact:
            print(f"- {artifact}")


def run_verify(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    out_dir = args.out.resolve() if args.out else repo / ".basalt"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = verify_repo(
        repo,
        keep_workspace=args.keep_workspace,
        sandbox_override=args.sandbox,
        output_dir=out_dir,
    )
    json_path, md_path, dashboard_path = _write_report_artifacts(report, out_dir, no_dashboard=args.no_dashboard)
    _print_report_result(report, [json_path, md_path, report.patch_plan_path or "", dashboard_path or ""])
    return 0 if report.final_status.value == "VERIFIED" else 1


def run_fix(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    out_dir = args.out.resolve() if args.out else repo / ".basalt"
    out_dir.mkdir(parents=True, exist_ok=True)
    before_report = verify_repo(repo, keep_workspace=args.keep_workspace, sandbox_override=args.sandbox, output_dir=out_dir)
    bundle, fix_artifacts = write_fix_bundle(repo, before_report, out_dir, apply=args.apply)
    before_report.artifacts.extend(fix_artifacts)
    _write_report_artifacts(before_report, out_dir)

    print("Basalt Alpha Fix Generator")
    print(f"Project: {before_report.project_name}")
    print(f"Source Status: {before_report.final_status.value}")
    print(f"Source Proof Score: {before_report.score}/100")
    print(bundle.message)
    if bundle.patch_path:
        print(f"Fix patch: {bundle.patch_path}")
    if bundle.generated_tests_path:
        print(f"Generated tests: {bundle.generated_tests_path}")
    if bundle.summary_path:
        print(f"Fix summary: {bundle.summary_path}")

    if args.rerun and not args.apply:
        print("Note: --rerun only runs after --apply. No repository files were changed.")
    if args.apply and args.rerun:
        after_report = verify_repo(repo, keep_workspace=args.keep_workspace, sandbox_override=args.sandbox, output_dir=out_dir)
        comparison_artifacts = write_before_after_artifacts(before_report, after_report, out_dir)
        after_report.artifacts.extend(fix_artifacts + comparison_artifacts)
        _write_report_artifacts(after_report, out_dir)
        print(f"New Status: {after_report.final_status.value}")
        print(f"New Proof Score: {after_report.score}/100")
        return 0 if after_report.final_status.value == "VERIFIED" else 1
    return 0 if bundle.generated_files else 1


def run_pr(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    out_dir = args.out.resolve() if args.out else repo / ".basalt"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = verify_repo(repo, sandbox_override=args.sandbox, output_dir=out_dir)
    _write_report_artifacts(report, out_dir)
    pack, artifacts = write_pr_pack(
        repo,
        report,
        out_dir,
        branch=args.branch,
        create_branch=args.create_branch,
        commit=args.commit,
        remote=args.remote,
    )
    report.artifacts.extend(artifacts)
    _write_report_artifacts(report, out_dir)
    print("Basalt GitHub PR Pack")
    print(f"Branch: {pack.branch_name}")
    print(pack.message)
    print(f"PR body: {pack.body_path}")
    print(f"PR commands: {pack.commands_path}")
    return 0


def run_demo(args: argparse.Namespace) -> int:
    source_root = Path(__file__).resolve().parents[1] / "examples"
    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in ("demo_good", "demo_weak", "demo_policy_violation", "demo_node_weak"):
        shutil.copytree(source_root / name, out / name)

    good = verify_repo(out / "demo_good", sandbox_override=args.sandbox, output_dir=out / "demo_good" / ".basalt")
    _write_report_artifacts(good, out / "demo_good" / ".basalt")
    weak_before = verify_repo(out / "demo_weak", sandbox_override=args.sandbox, output_dir=out / "demo_weak" / ".basalt")
    _, fix_artifacts = write_fix_bundle(out / "demo_weak", weak_before, out / "demo_weak" / ".basalt", apply=True)
    weak_after = verify_repo(out / "demo_weak", sandbox_override=args.sandbox, output_dir=out / "demo_weak" / ".basalt")
    weak_after.artifacts.extend(
        fix_artifacts + write_before_after_artifacts(weak_before, weak_after, out / "demo_weak" / ".basalt")
    )
    _write_report_artifacts(weak_after, out / "demo_weak" / ".basalt")

    policy = verify_repo(
        out / "demo_policy_violation",
        sandbox_override=args.sandbox,
        output_dir=out / "demo_policy_violation" / ".basalt",
    )
    _write_report_artifacts(policy, out / "demo_policy_violation" / ".basalt")

    node_before = verify_repo(
        out / "demo_node_weak",
        sandbox_override=args.sandbox,
        output_dir=out / "demo_node_weak" / ".basalt",
    )
    _, node_fix_artifacts = write_fix_bundle(
        out / "demo_node_weak",
        node_before,
        out / "demo_node_weak" / ".basalt",
        apply=True,
    )
    node_after = verify_repo(
        out / "demo_node_weak",
        sandbox_override=args.sandbox,
        output_dir=out / "demo_node_weak" / ".basalt",
    )
    node_after.artifacts.extend(
        node_fix_artifacts
        + write_before_after_artifacts(node_before, node_after, out / "demo_node_weak" / ".basalt")
    )
    _write_report_artifacts(node_after, out / "demo_node_weak" / ".basalt")

    summary = out / "BASALT_V2_ALPHA_DEMO_SUMMARY.md"
    summary.write_text(
        "# Basalt v2.0 Alpha Demo Summary\n\n"
        f"- demo_good: `{good.final_status.value}` ({good.score}/100)\n"
        f"- demo_weak before: `{weak_before.final_status.value}` ({weak_before.score}/100)\n"
        f"- demo_weak after: `{weak_after.final_status.value}` ({weak_after.score}/100)\n"
        f"- demo_node_weak before: `{node_before.final_status.value}` ({node_before.score}/100)\n"
        f"- demo_node_weak after: `{node_after.final_status.value}` ({node_after.score}/100)\n"
        f"- demo_policy_violation: `{policy.final_status.value}` ({policy.score}/100)\n",
        encoding="utf-8",
    )
    print("Basalt v2.0 alpha demo completed.")
    print(f"Demo folder: {out}")
    print(f"Summary: {summary}")
    return 0 if good.final_status.value == weak_after.final_status.value == node_after.final_status.value == "VERIFIED" else 1


def run_init(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    repo.mkdir(parents=True, exist_ok=True)
    config_path = repo / "basalt.yaml"
    if config_path.exists() and not args.force:
        print(f"basalt.yaml already exists at {config_path}. Use --force to overwrite.", file=sys.stderr)
        return 1
    project_type = args.type or infer_project_type(repo)
    if project_type == "unknown":
        project_type = "python"
    project_name = args.name or repo.name
    config_path.write_text(render_default_config(project_name, project_type), encoding="utf-8")
    print(f"Created {config_path}")
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    project_type = infer_project_type(repo)
    inferred = infer_commands(repo, project_type)
    config = load_config(repo)
    data = {
        "repo": str(repo),
        "project_name": config.project_name,
        "project_type": config.project_type,
        "inferred_project_type": project_type,
        "inferred_commands": inferred,
        "configured_commands": {
            command.name: {
                "command": command.command,
                "required": command.required,
                "allow_network": command.allow_network,
            }
            for command in config.commands
        },
        "sandbox": {
            "mode": config.sandbox,
            "docker_image": config.docker_image,
            "network": config.docker_network,
            "fallback_to_temp": config.docker_fallback,
        },
        "knowledge_graph": {
            "auto_refresh": config.graph_auto_refresh,
            "exclude": config.graph_exclude,
        },
        "context": {
            "token_budget": config.context_token_budget,
        },
    }
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("Basalt Repository Inspection")
        print(f"- repository: {repo}")
        print(f"- project: {config.project_name}")
        print(f"- type: {config.project_type}")
        print(f"- sandbox: {config.sandbox}")
        print(f"- docker image: {config.docker_image}")
        print("- commands:")
        for name, details in data["configured_commands"].items():
            print(f"  - {name}: {details['command'] or 'not configured'} (required={details['required']})")
    return 0


def _graph_paths(repo: Path, out: Path | None) -> tuple[Path, Path]:
    output_dir = out.resolve() if out else repo / ".basalt"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, output_dir / "knowledge-graph.sqlite3"


def run_graph(args: argparse.Namespace) -> int:
    if not args.graph_command:
        print("Choose one of: build, status, query", file=sys.stderr)
        return 2
    repo = args.repo.resolve()
    output_dir, store_path = _graph_paths(repo, args.out)
    config = load_config(repo)
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    if args.graph_command == "build":
        graph = build_project_graph(
            repo,
            store_path=store_path,
            excluded_paths=graph_exclude,
            force=args.force,
        )
        artifacts = write_graph_artifacts(graph, output_dir)
        data = {
            "state_hash": graph.state_hash,
            "fresh": graph.fresh,
            "files": graph.files_scanned,
            "symbols": len(graph.symbols),
            "edges": len(graph.edges),
            "features": len(graph.features),
            "test_mappings": len(graph.test_mappings),
            "routes": len(graph.routes),
            "schemas": len(graph.schemas),
            "changed_files": graph.changed_files,
            "reused_files": graph.reused_files,
            "removed_files": graph.removed_files,
            "store": str(store_path),
            "artifacts": [str(item) for item in artifacts],
        }
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print("Basalt Project Knowledge Graph")
            print(f"- state: {graph.state_hash}")
            print(f"- files: {graph.files_scanned}")
            print(f"- symbols: {len(graph.symbols)}")
            print(f"- edges: {len(graph.edges)}")
            print(f"- features: {len(graph.features)}")
            print(f"- test mappings: {len(graph.test_mappings)}")
            print(f"- changed/new: {len(graph.changed_files)}")
            print(f"- unchanged: {len(graph.reused_files)}")
            print(f"- store: {store_path}")
        return 0
    if args.graph_command == "status":
        freshness = check_graph_freshness(repo, store_path, graph_exclude)
        data = {
            "fresh": freshness.fresh,
            "reason": freshness.reason,
            "current_state_hash": freshness.current_state_hash,
            "stored_state_hash": freshness.stored_state_hash,
            "changed_files": freshness.changed_files,
            "new_files": freshness.new_files,
            "removed_files": freshness.removed_files,
        }
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print("Basalt Graph Freshness")
            print(f"- fresh: {freshness.fresh}")
            print(f"- reason: {freshness.reason}")
            print(f"- changed: {len(freshness.changed_files)}")
            print(f"- new: {len(freshness.new_files)}")
            print(f"- removed: {len(freshness.removed_files)}")
        return 0 if freshness.fresh else 1
    graph = build_project_graph(repo, store_path, graph_exclude)
    write_graph_artifacts(graph, output_dir)
    result = query_graph(graph, args.term, kind=args.kind, limit=max(1, args.limit))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Basalt Graph Query: {args.term}")
        for item in result["symbols"]:
            print(f"- symbol {item['kind']} {item['qualified_name'] or item['name']} @ {item['file']}:{item['line']}")
        for item in result["files"]:
            print(f"- file {item['path']} ({item['language']})")
        for item in result["features"]:
            print(f"- feature {item['name']} ({item['source']})")
    return 0


def run_impact(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    output_dir, store_path = _graph_paths(repo, args.out)
    config = load_config(repo)
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    graph = build_project_graph(repo, store_path, graph_exclude)
    result = analyze_impact(graph, args.target, depth=max(0, args.depth))
    json_path = output_dir / "impact-analysis.json"
    md_path = output_dir / "impact-analysis.md"
    json_path.write_text(json.dumps(result.__dict__, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_impact_markdown(result), encoding="utf-8")
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print("Basalt Change Impact Analysis")
        print(f"- target: {result.target}")
        print(f"- found: {result.found}")
        print(f"- risk: {result.risk_level}")
        print(f"- files: {len(result.impacted_files)}")
        print(f"- tests: {len(result.impacted_tests)}")
        print(f"- features: {len(result.impacted_features)}")
        print(f"- report: {md_path}")
    return 0 if result.found else 1


def run_context(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    output_dir = args.out.resolve() if args.out else repo / ".basalt"
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(repo)
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    budget = args.budget if args.budget is not None else config.context_token_budget
    try:
        pack, artifacts = compile_context_for_repo(
            repo,
            output_dir,
            task=args.task,
            agent_role=args.role,
            targets=args.target,
            token_budget=max(500, budget),
            excluded_paths=graph_exclude,
            refresh=(not args.no_refresh) and config.graph_auto_refresh,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(pack.__dict__, indent=2))
    else:
        print("Basalt Context Compiler")
        print(f"- context pack: {pack.context_pack_id}")
        print(f"- state: {pack.project_state_hash}")
        print(f"- task type: {pack.task_type}")
        print(f"- role: {pack.agent_role}")
        print(f"- selected files: {len(pack.files)}")
        print(f"- estimated tokens: {pack.estimated_tokens}/{pack.token_budget}")
        print(f"- context precision: {pack.context_precision_score:.4f}")
        print(f"- artifact: {artifacts[2]}")
    return 0


def run_doctor(args: argparse.Namespace) -> int:
    docker_ok, docker_reason = docker_status()
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "docker_cli_available": shutil.which("docker") is not None,
        "docker_daemon_available": docker_ok,
        "docker_detail": docker_reason,
        "git_available": shutil.which("git") is not None,
        "node_available": shutil.which("node") is not None,
        "npm_available": shutil.which("npm") is not None,
        "basalt_version": __version__,
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print("Basalt Doctor")
        for key, value in info.items():
            print(f"- {key}: {value}")
    return 0


def run_explain(args: argparse.Namespace) -> int:
    data = json.loads(args.report.read_text(encoding="utf-8"))
    print("Basalt Proof Report Summary")
    print(f"Project: {data.get('project_name')}")
    print(f"Status: {data.get('final_status')}")
    print(f"Score: {data.get('score')}/100")
    print(f"Project type: {data.get('project_type')}")
    print(f"Sandbox: {data.get('sandbox')} (requested: {data.get('sandbox_requested')})")
    print(f"Checks: {len(data.get('checks', []))}")
    print(f"Security/policy/dependency/quality findings: {len(data.get('security_findings', []))}")
    print(f"Mutations: {len(data.get('mutations', []))}")
    suggestions = data.get("fix_suggestions", [])
    if suggestions:
        print("Top actions:")
        for suggestion in suggestions[:5]:
            print(f"- [{suggestion.get('severity')}] {suggestion.get('title')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "verify": run_verify,
        "init": run_init,
        "inspect": run_inspect,
        "fix": run_fix,
        "pr": run_pr,
        "demo": run_demo,
        "doctor": run_doctor,
        "explain": run_explain,
        "graph": run_graph,
        "impact": run_impact,
        "context": run_context,
    }
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
