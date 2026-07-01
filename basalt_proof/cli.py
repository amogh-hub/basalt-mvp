from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

from .autofix import write_fix_bundle
from .compare import write_before_after_artifacts
from .config import infer_project_type, render_default_config
from .dashboard import write_dashboard
from .git_pr import write_pr_pack
from .models import GeneratedArtifact
from .proof import verify_repo
from .report import write_json_report, write_markdown_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="basalt", description="Basalt MVP v1.5: final Proof-to-PR demo MVP")
    subparsers = parser.add_subparsers(dest="command")

    verify = subparsers.add_parser("verify", help="Verify a repository and generate proof reports, dashboard, and PR evidence")
    verify.add_argument("repo", type=Path, help="Path to repository to verify")
    verify.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to <repo>/.basalt")
    verify.add_argument("--sandbox", choices=["temp", "docker"], default=None, help="Execution sandbox mode. Defaults to basalt.yaml sandbox.mode or temp")
    verify.add_argument("--keep-workspace", action="store_true", help="Keep temporary workspace for debugging")
    verify.add_argument("--no-dashboard", action="store_true", help="Do not generate Command Center HTML dashboard")

    init = subparsers.add_parser("init", help="Create a basalt.yaml in a repo")
    init.add_argument("repo", type=Path, nargs="?", default=Path("."), help="Repo path")
    init.add_argument("--type", choices=["python", "fastapi", "node", "react", "vite-react", "nextjs"], default=None, help="Project type")
    init.add_argument("--name", default=None, help="Project name")
    init.add_argument("--force", action="store_true", help="Overwrite existing basalt.yaml")

    fix = subparsers.add_parser("fix", help="Generate/apply additive proof-hardening fixes and optionally rerun proof")
    fix.add_argument("repo", type=Path, help="Path to repository to fix")
    fix.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to <repo>/.basalt")
    fix.add_argument("--apply", action="store_true", help="Apply generated additive tests to the repository")
    fix.add_argument("--rerun", action="store_true", help="After --apply, rerun verification and refresh reports")
    fix.add_argument("--sandbox", choices=["temp", "docker"], default=None, help="Execution sandbox mode")
    fix.add_argument("--keep-workspace", action="store_true", help="Keep temporary workspace for debugging")

    pr = subparsers.add_parser("pr", help="Generate a GitHub PR-ready pack, with optional local branch/commit")
    pr.add_argument("repo", type=Path, help="Path to repository")
    pr.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to <repo>/.basalt")
    pr.add_argument("--branch", default=None, help="Branch name to use in generated PR commands")
    pr.add_argument("--create-branch", action="store_true", help="Create/reset the local branch")
    pr.add_argument("--commit", action="store_true", help="Create a local git commit with current changes")
    pr.add_argument("--remote", default="origin", help="Remote name for generated push command")
    pr.add_argument("--sandbox", choices=["temp", "docker"], default=None, help="Execution sandbox mode")

    demo = subparsers.add_parser("demo", help="Run the final MVP demo flow in an isolated demo-run folder")
    demo.add_argument("--out", type=Path, default=Path("basalt-demo-run"), help="Folder for demo run output")
    demo.add_argument("--sandbox", choices=["temp", "docker"], default="temp", help="Execution sandbox mode")

    doctor = subparsers.add_parser("doctor", help="Check local Basalt MVP environment")
    doctor.add_argument("--json", action="store_true", help="Output JSON")

    explain = subparsers.add_parser("explain", help="Summarize an existing proof-report.json")
    explain.add_argument("report", type=Path, help="Path to proof-report.json")
    return parser


def _write_report_artifacts(report, out_dir: Path, no_dashboard: bool = False):
    json_path = out_dir / "proof-report.json"
    md_path = out_dir / "proof-report.md"
    write_json_report(report, json_path)
    write_markdown_report(report, md_path)
    # Avoid duplicate artifact entries on repeated writes.
    existing_paths = {a.path for a in report.artifacts}
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
        artifact = GeneratedArtifact("Command Center Dashboard", str(dashboard_path), "Browser-viewable final MVP dashboard")
        if artifact.path not in existing_paths:
            report.artifacts.append(artifact)
        write_json_report(report, json_path)
        write_markdown_report(report, md_path)
        write_dashboard(report, dashboard_path)
    return json_path, md_path, dashboard_path


def _print_report_result(report, artifacts: list[Path | str]) -> None:
    print("Basalt Final MVP v1.5")
    print(f"Project: {report.project_name}")
    print(f"Final Status: {report.final_status.value}")
    print(f"Proof Score: {report.score}/100")
    print(f"Sandbox: {report.sandbox}")
    print("Artifacts written:")
    for artifact in artifacts:
        if artifact:
            print(f"- {artifact}")


def run_verify(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    out_dir = (args.out.resolve() if args.out else repo / ".basalt")
    out_dir.mkdir(parents=True, exist_ok=True)
    report = verify_repo(repo, keep_workspace=args.keep_workspace, sandbox_override=args.sandbox, output_dir=out_dir)
    json_path, md_path, dashboard_path = _write_report_artifacts(report, out_dir, no_dashboard=args.no_dashboard)
    _print_report_result(report, [json_path, md_path, report.patch_plan_path or "", dashboard_path or ""])
    return 0 if report.final_status.value == "VERIFIED" else 1


def run_fix(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    out_dir = (args.out.resolve() if args.out else repo / ".basalt")
    out_dir.mkdir(parents=True, exist_ok=True)

    before_report = verify_repo(repo, keep_workspace=args.keep_workspace, sandbox_override=args.sandbox, output_dir=out_dir)
    bundle, fix_artifacts = write_fix_bundle(repo, before_report, out_dir, apply=args.apply)
    before_report.artifacts.extend(fix_artifacts)
    _write_report_artifacts(before_report, out_dir)

    print("Basalt Auto Fix Patch Generator v1.5")
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
        print("Rerunning Basalt verification after applying generated proof-hardening tests...")
        after_report = verify_repo(repo, keep_workspace=args.keep_workspace, sandbox_override=args.sandbox, output_dir=out_dir)
        comparison_artifacts = write_before_after_artifacts(before_report, after_report, out_dir)
        after_report.artifacts.extend(fix_artifacts + comparison_artifacts)
        _write_report_artifacts(after_report, out_dir)
        print(f"New Status: {after_report.final_status.value}")
        print(f"New Proof Score: {after_report.score}/100")
        print(f"Before/after comparison: {out_dir / 'before-after-proof.md'}")
        return 0 if after_report.final_status.value == "VERIFIED" else 1

    return 0 if bundle.generated_files else 1


def run_pr(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    out_dir = (args.out.resolve() if args.out else repo / ".basalt")
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
    bundle, fix_artifacts = write_fix_bundle(out / "demo_weak", weak_before, out / "demo_weak" / ".basalt", apply=True)
    weak_after = verify_repo(out / "demo_weak", sandbox_override=args.sandbox, output_dir=out / "demo_weak" / ".basalt")
    comparison_artifacts = write_before_after_artifacts(weak_before, weak_after, out / "demo_weak" / ".basalt")
    weak_after.artifacts.extend(fix_artifacts + comparison_artifacts)
    _write_report_artifacts(weak_after, out / "demo_weak" / ".basalt")
    policy = verify_repo(out / "demo_policy_violation", sandbox_override=args.sandbox, output_dir=out / "demo_policy_violation" / ".basalt")
    _write_report_artifacts(policy, out / "demo_policy_violation" / ".basalt")
    node_before = verify_repo(out / "demo_node_weak", sandbox_override=args.sandbox, output_dir=out / "demo_node_weak" / ".basalt")
    node_bundle, node_fix_artifacts = write_fix_bundle(out / "demo_node_weak", node_before, out / "demo_node_weak" / ".basalt", apply=True)
    node_after = verify_repo(out / "demo_node_weak", sandbox_override=args.sandbox, output_dir=out / "demo_node_weak" / ".basalt")
    node_comparison_artifacts = write_before_after_artifacts(node_before, node_after, out / "demo_node_weak" / ".basalt")
    node_after.artifacts.extend(node_fix_artifacts + node_comparison_artifacts)
    _write_report_artifacts(node_after, out / "demo_node_weak" / ".basalt")

    summary = out / "BASALT_MVP_V1_5_DEMO_SUMMARY.md"
    summary.write_text(
        "# Basalt MVP v1.5 Demo Summary\n\n"
        f"- demo_good: `{good.final_status.value}` ({good.score}/100)\n"
        f"- demo_weak before: `{weak_before.final_status.value}` ({weak_before.score}/100)\n"
        f"- demo_weak after auto-fix: `{weak_after.final_status.value}` ({weak_after.score}/100)\n"
        f"- demo_node_weak before: `{node_before.final_status.value}` ({node_before.score}/100)\n"
        f"- demo_node_weak after auto-fix: `{node_after.final_status.value}` ({node_after.score}/100)\n"
        f"- demo_policy_violation: `{policy.final_status.value}` ({policy.score}/100)\n\n"
        "Open `demo_weak/.basalt/basalt-dashboard.html` to show Python before/after proof hardening.\n"
        "Open `demo_node_weak/.basalt/basalt-dashboard.html` to show Node/JavaScript proof hardening.\n",
        encoding="utf-8",
    )
    print("Basalt final MVP demo completed.")
    print(f"Demo folder: {out}")
    print(f"Summary: {summary}")
    return 0 if weak_after.final_status.value == "VERIFIED" and node_after.final_status.value == "VERIFIED" and good.final_status.value == "VERIFIED" else 1


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


def run_doctor(args: argparse.Namespace) -> int:
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "docker_available": shutil.which("docker") is not None,
        "git_available": shutil.which("git") is not None,
        "node_available": shutil.which("node") is not None,
        "npm_available": shutil.which("npm") is not None,
        "basalt_version": "1.5.1",
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print("Basalt Doctor")
        for k, v in info.items():
            print(f"- {k}: {v}")
    return 0


def run_explain(args: argparse.Namespace) -> int:
    data = json.loads(args.report.read_text(encoding="utf-8"))
    print("Basalt Proof Report Summary")
    print(f"Project: {data.get('project_name')}")
    print(f"Status: {data.get('final_status')}")
    print(f"Score: {data.get('score')}/100")
    print(f"Project type: {data.get('project_type')}")
    print(f"Checks: {len(data.get('checks', []))}")
    print(f"Security/policy/quality findings: {len(data.get('security_findings', []))}")
    print(f"Mutations: {len(data.get('mutations', []))}")
    suggestions = data.get("fix_suggestions", [])
    if suggestions:
        print("Top actions:")
        for s in suggestions[:5]:
            print(f"- [{s.get('severity')}] {s.get('title')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "verify":
        return run_verify(args)
    if args.command == "init":
        return run_init(args)
    if args.command == "fix":
        return run_fix(args)
    if args.command == "pr":
        return run_pr(args)
    if args.command == "demo":
        return run_demo(args)
    if args.command == "doctor":
        return run_doctor(args)
    if args.command == "explain":
        return run_explain(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
