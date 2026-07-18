from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .agent_runtime import (
    AgentRunError,
    apply_agent_run,
    approve_agent_run,
    list_agent_runs,
    load_agent_run,
    plan_agent_fix,
    reject_agent_run,
    revise_agent_run,
    rollback_agent_run,
)
from .autofix import write_fix_bundle
from .compare import write_before_after_artifacts
from .config import infer_commands, infer_project_type, load_config, render_default_config
from .context_compiler import compile_context_for_repo
from .command_center import CommandCenterService
from .command_center_server import serve_command_center
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
from .design_system import audit_design_system, write_design_system_artifacts
from .model_router import ModelRouter
from .private_beta import PrivateBetaPlatform, PrivateBetaError
from .job_queue import JobQueueError
from .state_coordinator import ContractLockError, StateConflictError
from .software_factory import (
    FactoryError,
    build_factory_run,
    create_product,
    factory_snapshot,
    list_factory_runs,
    load_factory_run,
    plan_factory_run,
)


PRODUCT_NAME = "Basalt v2.5 Private Beta Full Build System"


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

    agent = subparsers.add_parser("agent", help="Plan, approve, apply, and audit governed agent-assisted fixes")
    agent_commands = agent.add_subparsers(dest="agent_command")

    agent_plan = agent_commands.add_parser("plan", help="Compile context and produce a policy-checked patch proposal")
    agent_plan.add_argument("repo", type=Path)
    agent_plan.add_argument("--task", required=True)
    agent_plan.add_argument("--role", default="ImplementationAgent")
    agent_plan.add_argument("--target", action="append", default=[])
    agent_plan.add_argument("--patch", type=Path, default=None, help="External unified diff to govern")
    agent_plan.add_argument("--out", type=Path, default=None)
    agent_plan.add_argument("--sandbox", choices=["auto", "temp", "docker"], default=None)
    agent_plan.add_argument("--budget", type=int, default=None)
    agent_plan.add_argument("--json", action="store_true")

    agent_approve = agent_commands.add_parser("approve", help="Record human approval and issue a one-time apply token")
    agent_approve.add_argument("repo", type=Path)
    agent_approve.add_argument("run_id")
    agent_approve.add_argument("--by", required=True)
    agent_approve.add_argument("--reason", required=True)
    agent_approve.add_argument("--out", type=Path, default=None)
    agent_approve.add_argument("--json", action="store_true")

    agent_apply = agent_commands.add_parser("apply", help="Apply an approved patch transaction and run full proof")
    agent_apply.add_argument("repo", type=Path)
    agent_apply.add_argument("run_id")
    agent_apply.add_argument("--token", default=None)
    agent_apply.add_argument("--out", type=Path, default=None)
    agent_apply.add_argument("--sandbox", choices=["auto", "temp", "docker"], default=None)
    agent_apply.add_argument("--json", action="store_true")

    agent_status = agent_commands.add_parser("status", help="Show one agent run or list recent runs")
    agent_status.add_argument("repo", type=Path)
    agent_status.add_argument("run_id", nargs="?", default=None)
    agent_status.add_argument("--out", type=Path, default=None)
    agent_status.add_argument("--json", action="store_true")

    agent_reject = agent_commands.add_parser("reject", help="Reject a pending proposal")
    agent_reject.add_argument("repo", type=Path)
    agent_reject.add_argument("run_id")
    agent_reject.add_argument("--by", required=True)
    agent_reject.add_argument("--reason", required=True)
    agent_reject.add_argument("--out", type=Path, default=None)
    agent_reject.add_argument("--json", action="store_true")

    agent_revise = agent_commands.add_parser("revise", help="Submit a revised patch under the Loop Governor")
    agent_revise.add_argument("repo", type=Path)
    agent_revise.add_argument("run_id")
    agent_revise.add_argument("--patch", type=Path, required=True)
    agent_revise.add_argument("--out", type=Path, default=None)
    agent_revise.add_argument("--json", action="store_true")

    factory = subparsers.add_parser(
        "factory",
        help="Plan and assemble proof-backed alpha products through governed specialist agents",
    )
    factory_commands = factory.add_subparsers(dest="factory_command")

    factory_plan = factory_commands.add_parser("plan", help="Create a Product Brain blueprint, prevention plan, task graph, and model assignments")
    factory_plan.add_argument("repo", type=Path, nargs="?", default=Path("."))
    factory_plan.add_argument("--prompt", required=True, help="Product intent")
    factory_plan.add_argument("--name", required=True, help="Product name")
    factory_plan.add_argument("--template", choices=["python-service", "api-service", "fullstack-lite", "web-app", "saas-starter"], default="python-service")
    factory_plan.add_argument("--users", action="append", default=[], help="Target user; repeatable")
    factory_plan.add_argument("--constraint", action="append", default=[], help="Product or engineering constraint; repeatable")
    factory_plan.add_argument("--privacy", choices=["local", "private", "standard"], default="local")
    factory_plan.add_argument("--out", type=Path, default=None)
    factory_plan.add_argument("--json", action="store_true")

    factory_build = factory_commands.add_parser("build", help="Build and verify an existing factory plan before atomic assembly")
    factory_build.add_argument("repo", type=Path)
    factory_build.add_argument("run_id")
    factory_build.add_argument("--target", type=Path, required=True)
    factory_build.add_argument("--sandbox", choices=["auto", "temp", "docker"], default="temp")
    factory_build.add_argument("--out", type=Path, default=None)
    factory_build.add_argument("--json", action="store_true")

    factory_create = factory_commands.add_parser("create", help="Plan, build, prove, and assemble a supported alpha product")
    factory_create.add_argument("repo", type=Path, nargs="?", default=Path("."))
    factory_create.add_argument("--prompt", required=True, help="Product intent")
    factory_create.add_argument("--name", required=True, help="Product name")
    factory_create.add_argument("--target", type=Path, required=True)
    factory_create.add_argument("--template", choices=["python-service", "api-service", "fullstack-lite", "web-app", "saas-starter"], default="python-service")
    factory_create.add_argument("--users", action="append", default=[])
    factory_create.add_argument("--constraint", action="append", default=[])
    factory_create.add_argument("--privacy", choices=["local", "private", "standard"], default="local")
    factory_create.add_argument("--sandbox", choices=["auto", "temp", "docker"], default="temp")
    factory_create.add_argument("--out", type=Path, default=None)
    factory_create.add_argument("--json", action="store_true")

    factory_status = factory_commands.add_parser("status", help="Show one factory run or list recent factory runs")
    factory_status.add_argument("repo", type=Path, nargs="?", default=Path("."))
    factory_status.add_argument("run_id", nargs="?", default=None)
    factory_status.add_argument("--out", type=Path, default=None)
    factory_status.add_argument("--json", action="store_true")

    factory_models = factory_commands.add_parser("models", help="Show provider-neutral model routing inventory")
    factory_models.add_argument("repo", type=Path, nargs="?", default=Path("."))
    factory_models.add_argument("--json", action="store_true")

    factory_design = factory_commands.add_parser("design-system", help="Write and audit the locked Basalt Obsidian design system")
    factory_design.add_argument("repo", type=Path, nargs="?", default=Path("."))
    factory_design.add_argument("--out", type=Path, default=None)
    factory_design.add_argument("--json", action="store_true")

    beta = subparsers.add_parser("beta", help="Operate the persistent private-beta workspace, jobs, providers, and deployments")
    beta_commands = beta.add_subparsers(dest="beta_command")

    beta_bootstrap = beta_commands.add_parser("bootstrap", help="Create the first private-beta user and team")
    beta_bootstrap.add_argument("repo", type=Path, nargs="?", default=Path("."))
    beta_bootstrap.add_argument("--email", required=True)
    beta_bootstrap.add_argument("--name", required=True, help="Display name")
    beta_bootstrap.add_argument("--team", required=True, help="Team name")
    beta_bootstrap.add_argument("--json", action="store_true")

    beta_status = beta_commands.add_parser("status", help="Show the private-beta control-plane snapshot")
    beta_status.add_argument("repo", type=Path, nargs="?", default=Path("."))
    beta_status.add_argument("--json", action="store_true")

    beta_project = beta_commands.add_parser("project-add", help="Register a project in a private-beta team")
    beta_project.add_argument("repo", type=Path, nargs="?", default=Path("."), help="Basalt repository")
    beta_project.add_argument("--team-id", required=True)
    beta_project.add_argument("--created-by", required=True)
    beta_project.add_argument("--name", required=True)
    beta_project.add_argument("--project-repo", type=Path, required=True)
    beta_project.add_argument("--template", choices=["python-service", "api-service", "fullstack-lite", "web-app", "saas-starter"], default="fullstack-lite")
    beta_project.add_argument("--privacy", choices=["local", "private", "standard"], default="local")
    beta_project.add_argument("--json", action="store_true")

    beta_submit = beta_commands.add_parser("job-submit", help="Submit a durable private-beta job")
    beta_submit.add_argument("repo", type=Path, nargs="?", default=Path("."))
    beta_submit.add_argument("--project-id", required=True)
    beta_submit.add_argument("--type", choices=["VERIFY_PROJECT", "FACTORY_PLAN", "FACTORY_CREATE", "PACKAGE_PREVIEW"], required=True)
    beta_submit.add_argument("--created-by", required=True)
    beta_submit.add_argument("--payload", default="{}", help="JSON object payload")
    beta_submit.add_argument("--idempotency-key", default="")
    beta_submit.add_argument("--json", action="store_true")

    beta_run = beta_commands.add_parser("job-run", help="Run one queued private-beta job")
    beta_run.add_argument("repo", type=Path, nargs="?", default=Path("."))
    beta_run.add_argument("job_id")
    beta_run.add_argument("--worker", default="beta-cli-worker")
    beta_run.add_argument("--json", action="store_true")

    beta_jobs = beta_commands.add_parser("jobs", help="List durable private-beta jobs")
    beta_jobs.add_argument("repo", type=Path, nargs="?", default=Path("."))
    beta_jobs.add_argument("--json", action="store_true")

    beta_providers = beta_commands.add_parser("providers", help="Show secret-safe model provider inventory")
    beta_providers.add_argument("repo", type=Path, nargs="?", default=Path("."))
    beta_providers.add_argument("--json", action="store_true")

    beta_deployments = beta_commands.add_parser("deployments", help="List private-beta deployment records")
    beta_deployments.add_argument("repo", type=Path, nargs="?", default=Path("."))
    beta_deployments.add_argument("--json", action="store_true")

    command_center = subparsers.add_parser(
        "command-center",
        help="Launch the local truth-compression web app for proof, graph, transactions, approvals, and evidence",
    )
    command_center.add_argument("repo", type=Path, nargs="?", default=Path("."), help="Repository path")
    command_center.add_argument("--out", type=Path, default=None, help="Evidence directory. Defaults to <repo>/.basalt")
    command_center.add_argument("--host", default="127.0.0.1", help="Bind host. Localhost is enforced by default.")
    command_center.add_argument("--port", type=int, default=7337, help="Bind port")
    command_center.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    command_center.add_argument(
        "--allow-actions",
        action="store_true",
        help="Enable governed verify, approve, reject, apply, and rollback actions",
    )
    command_center.add_argument(
        "--unsafe-bind",
        action="store_true",
        help="Allow a non-loopback bind. Use only inside a trusted network.",
    )
    command_center.add_argument("--snapshot", action="store_true", help="Print a Command Center JSON snapshot and exit")
    command_center.add_argument("--json", action="store_true", help="Use JSON output for --snapshot")

    agent_rollback = agent_commands.add_parser("rollback", help="Roll back a previously verified transaction")
    agent_rollback.add_argument("repo", type=Path)
    agent_rollback.add_argument("run_id")
    agent_rollback.add_argument("--by", required=True)
    agent_rollback.add_argument("--reason", required=True)
    agent_rollback.add_argument("--out", type=Path, default=None)
    agent_rollback.add_argument("--json", action="store_true")
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
        "agents": {
            "enabled": config.agents_enabled,
            "max_files": config.agent_max_files,
            "max_changed_lines": config.agent_max_changed_lines,
            "max_attempts": config.agent_max_attempts,
            "require_human_approval_for_source": config.agent_require_human_approval_for_source,
            "allow_test_only_auto_apply": config.agent_allow_test_only_auto_apply,
            "protected_paths": config.agent_protected_paths,
            "allowed_roles": config.agent_allowed_roles,
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


def _print_agent_run(run) -> None:
    print("Basalt Agent-Assisted Safe Fix")
    print(f"- run: {run.run_id}")
    print(f"- status: {run.status.value}")
    print(f"- task: {run.task}")
    print(f"- role: {run.agent_role}")
    print(f"- base state: {run.base_state_hash}")
    if run.policy_decision:
        print(f"- policy: {run.policy_decision.verdict.value}")
        print(f"- risk: {run.policy_decision.risk_level}")
        print(f"- files: {run.policy_decision.patch_stats.files_changed}")
        print(f"- changed lines: {run.policy_decision.patch_stats.changed_lines}")
    if run.verification_delta:
        print(
            f"- proof: {run.verification_delta.before_status} "
            f"({run.verification_delta.before_score}) -> "
            f"{run.verification_delta.after_status} "
            f"({run.verification_delta.after_score})"
        )
    print(f"- message: {run.message}")


def run_agent(args: argparse.Namespace) -> int:
    if not args.agent_command:
        print("Choose one of: plan, approve, apply, status, reject, revise, rollback", file=sys.stderr)
        return 2
    repo = args.repo.resolve()
    out_dir = args.out.resolve() if getattr(args, "out", None) else None
    try:
        if args.agent_command == "plan":
            run = plan_agent_fix(
                repo,
                task=args.task,
                agent_role=args.role,
                targets=args.target,
                patch_file=args.patch,
                out_dir=out_dir,
                sandbox=args.sandbox,
                token_budget=args.budget,
            )
            if args.json:
                print(json.dumps(run.to_dict(), indent=2))
            else:
                _print_agent_run(run)
                print(f"- artifacts: {(out_dir or repo / '.basalt') / 'agent-runs' / run.run_id}")
                if run.status.value == "AWAITING_APPROVAL":
                    print(f"Next: basalt agent approve {repo} {run.run_id} --by <name> --reason <reason>")
            return 0 if run.status.value in {"AWAITING_APPROVAL", "APPROVED"} else 1

        if args.agent_command == "approve":
            run, token = approve_agent_run(repo, args.run_id, args.by, args.reason, out_dir=out_dir)
            if args.json:
                data = run.to_dict()
                data["approval_token"] = token
                print(json.dumps(data, indent=2))
            else:
                _print_agent_run(run)
                print("- one-time approval token:")
                print(token)
                print("Store this token now. Basalt stores only its hash and will not display it again.")
            return 0

        if args.agent_command == "apply":
            run = apply_agent_run(
                repo,
                args.run_id,
                approval_token=args.token,
                out_dir=out_dir,
                sandbox=args.sandbox,
            )
            if args.json:
                print(json.dumps(run.to_dict(), indent=2))
            else:
                _print_agent_run(run)
            return 0 if run.status.value == "VERIFIED" else 1

        if args.agent_command == "status":
            if args.run_id:
                run, run_dir = load_agent_run(repo, args.run_id, out_dir)
                if args.json:
                    print(json.dumps(run.to_dict(), indent=2))
                else:
                    _print_agent_run(run)
                    print(f"- artifacts: {run_dir}")
            else:
                runs = list_agent_runs(repo, out_dir)
                if args.json:
                    print(json.dumps(runs, indent=2))
                else:
                    print("Basalt Agent Runs")
                    if not runs:
                        print("- no runs found")
                    for item in runs:
                        print(
                            f"- {item.get('run_id')}: {item.get('status')} "
                            f"[{item.get('risk')}] {item.get('task')}"
                        )
            return 0

        if args.agent_command == "reject":
            run = reject_agent_run(repo, args.run_id, args.by, args.reason, out_dir=out_dir)
        elif args.agent_command == "revise":
            run = revise_agent_run(repo, args.run_id, args.patch, out_dir=out_dir)
        else:
            run = rollback_agent_run(repo, args.run_id, args.by, args.reason, out_dir=out_dir)
        if args.json:
            print(json.dumps(run.to_dict(), indent=2))
        else:
            _print_agent_run(run)
        return 0 if run.status.value not in {"FAILED", "STUCK", "STALE_STATE"} else 1
    except (AgentRunError, OSError, ValueError) as exc:
        print(f"Basalt agent error: {exc}", file=sys.stderr)
        return 1



def _print_factory_run(run) -> None:
    print("Basalt Private Beta Full Build System")
    print(f"- run: {run.run_id}")
    print(f"- product: {run.product_name}")
    print(f"- template: {run.template}")
    print(f"- status: {run.status.value}")
    print(f"- base state: {run.base_state_version}")
    if run.committed_state_version:
        print(f"- committed state: {run.committed_state_version}")
    print(f"- tasks / epochs: {len(run.tasks)} / {len(run.epochs)}")
    print(f"- proof: {run.proof_status or 'NOT_RUN'} ({run.proof_score}/100)")
    if run.target_path:
        print(f"- target: {run.target_path}")
    print(f"- message: {run.message}")


def run_factory(args: argparse.Namespace) -> int:
    if not args.factory_command:
        print("Choose one of: plan, build, create, status, models, design-system", file=sys.stderr)
        return 2
    repo = args.repo.resolve()
    out_dir = args.out.resolve() if getattr(args, "out", None) else None
    try:
        if args.factory_command == "plan":
            run = plan_factory_run(
                repo,
                args.prompt,
                args.name,
                template=args.template,
                target_users=args.users,
                constraints=args.constraint,
                privacy_mode=args.privacy,
                out_dir=out_dir,
            )
        elif args.factory_command == "build":
            run = build_factory_run(repo, args.run_id, args.target, sandbox=args.sandbox, out_dir=out_dir)
        elif args.factory_command == "create":
            run = create_product(
                repo,
                args.prompt,
                args.name,
                args.target,
                template=args.template,
                target_users=args.users,
                constraints=args.constraint,
                privacy_mode=args.privacy,
                sandbox=args.sandbox,
                out_dir=out_dir,
            )
        elif args.factory_command == "status":
            if args.run_id:
                run = load_factory_run(repo, args.run_id, out_dir)
                if args.json:
                    print(json.dumps(run.to_dict(), indent=2))
                else:
                    _print_factory_run(run)
                return 0
            runs = list_factory_runs(repo, out_dir)
            if args.json:
                print(json.dumps(runs, indent=2))
            else:
                print("Basalt Factory Runs")
                if not runs:
                    print("- no factory runs found")
                for item in runs:
                    print(f"- {item.get('run_id')}: {item.get('status')} — {item.get('product_name')}")
            return 0
        elif args.factory_command == "models":
            data = ModelRouter().inventory()
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print("Basalt Model Router")
                for item in data:
                    print(f"- {item['provider']}/{item['model']}: {'available' if item['available'] else 'not configured'}")
            return 0
        else:
            output = out_dir or repo / ".basalt"
            paths = write_design_system_artifacts(repo, output)
            findings = audit_design_system(repo)
            payload = {"artifacts": [str(path) for path in paths], "findings": [item.__dict__ for item in findings]}
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print("Basalt Obsidian Design System")
                print(f"- findings: {len(findings)}")
                for path in paths:
                    print(f"- artifact: {path}")
            return 1 if any(item.level == "HIGH" for item in findings) else 0
        if args.json:
            print(json.dumps(run.to_dict(), indent=2))
        else:
            _print_factory_run(run)
            print(f"- artifacts: {(out_dir or repo / '.basalt') / 'factory-runs' / run.run_id}")
        return 0 if run.status.value in {"PLANNED", "VERIFIED"} else 1
    except (FactoryError, OSError, ValueError, StateConflictError, ContractLockError) as exc:
        print(f"Basalt factory error: {exc}", file=sys.stderr)
        return 1


def run_beta(args: argparse.Namespace) -> int:
    if not args.beta_command:
        print("Choose one of: bootstrap, status, project-add, job-submit, job-run, jobs, providers, deployments", file=sys.stderr)
        return 2
    repo = args.repo.resolve()
    platform = PrivateBetaPlatform(repo / ".basalt" / "private-beta")
    try:
        if args.beta_command == "bootstrap":
            result = platform.bootstrap(args.email, args.name, args.team)
        elif args.beta_command == "status":
            result = platform.snapshot()
        elif args.beta_command == "project-add":
            result = platform.add_project(
                args.team_id, args.name, args.project_repo, args.created_by, args.template, args.privacy
            )
        elif args.beta_command == "job-submit":
            try:
                payload = json.loads(args.payload)
            except json.JSONDecodeError as exc:
                raise ValueError("--payload must be valid JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError("--payload must be a JSON object.")
            result = platform.submit_job(
                args.project_id, args.type, payload, args.created_by, args.idempotency_key
            )
        elif args.beta_command == "job-run":
            result = platform.run_job(args.job_id, args.worker)
        elif args.beta_command == "jobs":
            result = {"items": platform.jobs.list()}
        elif args.beta_command == "providers":
            result = platform.providers.snapshot()
        else:
            result = platform.deployments.snapshot()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("Basalt Private Beta")
            print(json.dumps(result, indent=2))
        return 0
    except (PrivateBetaError, OSError, ValueError, JobQueueError) as exc:
        print(f"Basalt private beta error: {exc}", file=sys.stderr)
        return 1


def run_command_center(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    out_dir = args.out.resolve() if args.out else None
    if args.snapshot:
        try:
            snapshot = CommandCenterService(repo, out_dir).overview()
        except (OSError, ValueError) as exc:
            print(f"Basalt Command Center error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(snapshot, indent=2))
        else:
            print("Basalt v2.5 Private Beta Snapshot")
            print(f"- project: {snapshot['project']['name']}")
            print(f"- verdict: {snapshot['truth']['status']}")
            print(f"- proof score: {snapshot['truth']['score']}/100")
            print(f"- risk: {snapshot['truth']['risk']}")
            print(f"- graph fresh: {snapshot['truth']['graph_fresh']}")
            print(f"- symbols: {snapshot['graph']['symbols']}")
            print(f"- edges: {snapshot['graph']['edges']}")
            print(f"- pending approvals: {snapshot['approvals']['pending']}")
            print(f"- transactions: {snapshot['transactions']['total']}")
        return 0
    try:
        serve_command_center(
            repo,
            host=args.host,
            port=args.port,
            allow_actions=args.allow_actions,
            unsafe_bind=args.unsafe_bind,
            open_browser=not args.no_open,
            out_dir=out_dir,
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"Basalt Command Center error: {exc}", file=sys.stderr)
        return 1

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
        "agent": run_agent,
        "command-center": run_command_center,
        "factory": run_factory,
        "beta": run_beta,
    }
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
