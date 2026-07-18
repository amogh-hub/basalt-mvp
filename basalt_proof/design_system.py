from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path


TOKENS = {
    "name": "Basalt Obsidian",
    "version": "1.0",
    "color": {
        "background": "#08090b",
        "surface": "#101318",
        "surfaceElevated": "#151920",
        "surfaceQuiet": "#0c0f13",
        "border": "#252b33",
        "borderStrong": "#343c46",
        "text": "#f1f3f5",
        "textMuted": "#939daa",
        "textFaint": "#626d79",
        "accent": "#71859b",
        "accentStrong": "#92a4b6",
        "accentSoft": "rgba(113, 133, 155, 0.14)",
        "success": "#5db58a",
        "warning": "#c49a5a",
        "danger": "#c86f73",
        "review": "#8b829e",
    },
    "radius": {"small": "8px", "medium": "12px", "large": "18px", "panel": "22px"},
    "shadow": {"panel": "0 18px 60px rgba(0, 0, 0, 0.24)", "focus": "0 0 0 3px rgba(113, 133, 155, 0.25)"},
    "motion": {"fast": "120ms", "standard": "180ms", "slow": "260ms"},
    "principles": [
        "Stealth luxury and engineering precision.",
        "Truth before activity.",
        "No decorative neon, emojis, cartoon agents, or fake AI motion.",
        "Status colors communicate state only.",
        "Progressive disclosure keeps raw internals collapsed by default.",
    ],
}


@dataclass
class DesignFinding:
    level: str
    file: str
    rule: str
    message: str


def render_css_tokens() -> str:
    colors = TOKENS["color"]
    radius = TOKENS["radius"]
    shadow = TOKENS["shadow"]
    motion = TOKENS["motion"]
    return "\n".join(
        [
            ":root {",
            f"  --bg: {colors['background']};",
            f"  --panel: {colors['surface']};",
            f"  --panel-2: {colors['surfaceElevated']};",
            f"  --panel-quiet: {colors['surfaceQuiet']};",
            f"  --line: {colors['border']};",
            f"  --line-strong: {colors['borderStrong']};",
            f"  --text: {colors['text']};",
            f"  --muted: {colors['textMuted']};",
            f"  --faint: {colors['textFaint']};",
            f"  --accent: {colors['accent']};",
            f"  --accent-strong: {colors['accentStrong']};",
            f"  --accent-soft: {colors['accentSoft']};",
            f"  --good: {colors['success']};",
            f"  --warn: {colors['warning']};",
            f"  --bad: {colors['danger']};",
            f"  --review: {colors['review']};",
            f"  --radius-sm: {radius['small']};",
            f"  --radius-md: {radius['medium']};",
            f"  --radius: {radius['large']};",
            f"  --radius-panel: {radius['panel']};",
            f"  --shadow-panel: {shadow['panel']};",
            f"  --focus-ring: {shadow['focus']};",
            f"  --motion-fast: {motion['fast']};",
            f"  --motion-standard: {motion['standard']};",
            f"  --motion-slow: {motion['slow']};",
            "}",
            "",
        ]
    )


def audit_design_system(repo: Path) -> list[DesignFinding]:
    findings: list[DesignFinding] = []
    targets = [*repo.rglob("*.css"), *repo.rglob("*.html"), *repo.rglob("*.js")]
    excluded = {".git", ".venv", "venv", "node_modules", ".basalt"}
    emoji_pattern = re.compile(r"[\U0001F300-\U0001FAFF]")
    for path in targets:
        if any(part in excluded for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        relative = path.relative_to(repo).as_posix()
        if "#d7ff4f" in text.lower() or "215,255,79" in text.replace(" ", ""):
            findings.append(DesignFinding("HIGH", relative, "no_lime", "Legacy lime accent violates the Basalt Obsidian system."))
        if re.search(r"https?://[^\s\"']+", text) and path.suffix in {".html", ".css"}:
            findings.append(DesignFinding("MEDIUM", relative, "no_external_ui_dependencies", "External UI asset or stylesheet detected."))
        if emoji_pattern.search(text):
            findings.append(DesignFinding("MEDIUM", relative, "no_emoji_ui", "Emoji detected in product interface source."))
        if text.count("style=\"") + text.count("style='") > 3:
            findings.append(DesignFinding("LOW", relative, "token_governance", "Repeated inline styles should be converted to design tokens or classes."))
    return findings


def write_design_system_artifacts(repo: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "basalt-design-tokens.json"
    md_path = out_dir / "basalt-design-system.md"
    audit_path = out_dir / "design-system-audit.json"
    json_path.write_text(json.dumps(TOKENS, indent=2), encoding="utf-8")
    md_path.write_text(
        "# Basalt Obsidian Design System\n\n"
        "Basalt uses stealth luxury, dark operational control, and engineering precision.\n\n"
        "## Locked rules\n\n"
        + "\n".join(f"- {item}" for item in TOKENS["principles"])
        + "\n",
        encoding="utf-8",
    )
    findings = audit_design_system(repo)
    audit_path.write_text(json.dumps([asdict(item) for item in findings], indent=2), encoding="utf-8")
    return [json_path, md_path, audit_path]
