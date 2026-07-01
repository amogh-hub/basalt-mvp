from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import GeneratedArtifact, ProofReport


def _mutation_summary(report: ProofReport) -> dict[str, int]:
    total = len(report.mutations)
    survived = sum(1 for m in report.mutations if m.survived)
    killed = total - survived
    return {"total": total, "killed": killed, "survived": survived}


def build_before_after(before: ProofReport, after: ProofReport) -> dict[str, Any]:
    before_mut = _mutation_summary(before)
    after_mut = _mutation_summary(after)
    return {
        "project": after.project_name,
        "before": {
            "status": before.final_status.value,
            "score": before.score,
            "mutations": before_mut,
            "security_findings": len(before.security_findings),
            "fix_suggestions": len(before.fix_suggestions),
        },
        "after": {
            "status": after.final_status.value,
            "score": after.score,
            "mutations": after_mut,
            "security_findings": len(after.security_findings),
            "fix_suggestions": len(after.fix_suggestions),
        },
        "delta": {
            "score": after.score - before.score,
            "survived_mutations": after_mut["survived"] - before_mut["survived"],
            "security_findings": len(after.security_findings) - len(before.security_findings),
        },
        "final_acceptance": after.final_status.value == "VERIFIED",
    }


def render_before_after_markdown(before: ProofReport, after: ProofReport) -> str:
    comparison = build_before_after(before, after)
    b = comparison["before"]
    a = comparison["after"]
    d = comparison["delta"]
    lines = [
        "# Basalt Before/After Proof Comparison",
        "",
        f"**Project:** `{after.project_name}`",
        "",
        "## Executive Summary",
        "",
        f"- Before: `{b['status']}` with proof score `{b['score']}/100`",
        f"- After: `{a['status']}` with proof score `{a['score']}/100`",
        f"- Score delta: `{d['score']:+}`",
        f"- Survived mutation delta: `{d['survived_mutations']:+}`",
        "",
        "## Proof Movement",
        "",
        "| Metric | Before | After | Delta |",
        "|---|---:|---:|---:|",
        f"| Proof score | {b['score']} | {a['score']} | {d['score']:+} |",
        f"| Survived mutations | {b['mutations']['survived']} | {a['mutations']['survived']} | {d['survived_mutations']:+} |",
        f"| Security/policy findings | {b['security_findings']} | {a['security_findings']} | {d['security_findings']:+} |",
        f"| Fix suggestions | {b['fix_suggestions']} | {a['fix_suggestions']} | {a['fix_suggestions'] - b['fix_suggestions']:+} |",
        "",
        "## Acceptance Decision",
        "",
    ]
    if after.final_status.value == "VERIFIED":
        lines.append("Basalt accepts the after-state as **VERIFIED** under the configured MVP proof policy.")
    else:
        lines.append("Basalt does **not** accept the after-state yet. Continue hardening until the final status is `VERIFIED` or every remaining high-risk item has explicit human approval.")
    lines.append("")
    return "\n".join(lines)


def write_before_after_artifacts(before: ProofReport, after: ProofReport, output_dir: Path) -> list[GeneratedArtifact]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "before-after-proof.json"
    md_path = output_dir / "before-after-proof.md"
    json_path.write_text(json.dumps(build_before_after(before, after), indent=2), encoding="utf-8")
    md_path.write_text(render_before_after_markdown(before, after), encoding="utf-8")
    return [
        GeneratedArtifact("Before/After Proof JSON", str(json_path), "Machine-readable proof movement after Basalt fix"),
        GeneratedArtifact("Before/After Proof Markdown", str(md_path), "Human-readable before/after proof comparison"),
    ]
