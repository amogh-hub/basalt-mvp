from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path


TOKENS = {
    "name": "Basalt Obsidian",
    "version": "1.1",
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
    "brand": {
        "wordmark": "basalt_proof/webui/brand/basalt-wordmark-mask.png",
        "dark_mode_color": "#f1f3f5",
        "light_mode_color": "#08090b",
        "background_dark": "#08090b",
        "background_light": "#f7f7f5",
        "rule": "The monochrome wordmark preserves its geometry and changes only foreground colour.",
    },
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
    brand_root = repo / "basalt_proof" / "webui" / "brand"
    required_brand_assets = {
        "basalt-wordmark-mask.png",
        "basalt-wordmark-dark.png",
        "basalt-wordmark-light.png",
        "basalt-mark-dark.png",
        "basalt-mark-light.png",
    }
    for asset in sorted(required_brand_assets):
        path = brand_root / asset
        if not path.exists() or path.stat().st_size < 128:
            findings.append(DesignFinding("HIGH", path.relative_to(repo).as_posix(), "brand_asset_missing", f"Required Basalt brand asset is missing or empty: {asset}."))
    excluded = {".git", ".venv", "venv", "node_modules", ".basalt", "dist", "build"}
    targets: list[Path] = []
    for current_root, directory_names, file_names in os.walk(repo):
        directory_names[:] = [name for name in directory_names if name not in excluded]
        root_path = Path(current_root)
        for file_name in file_names:
            if Path(file_name).suffix.lower() in {".css", ".html", ".js"}:
                targets.append(root_path / file_name)
    emoji_pattern = re.compile(r"[\U0001F300-\U0001FAFF]")
    for path in targets:
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
    styles_path = repo / "basalt_proof" / "webui" / "styles.css"
    if styles_path.exists() and "basalt-wordmark-mask.png" not in styles_path.read_text(encoding="utf-8", errors="ignore"):
        findings.append(DesignFinding("MEDIUM", styles_path.relative_to(repo).as_posix(), "brand_not_integrated", "The official Basalt wordmark mask is not integrated into the Command Center."))
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
        + "\n\n## Official wordmark\n\n"
        + "- Dark mode: soft off-white wordmark on obsidian.\n"
        + "- Light mode: near-black wordmark on a soft light surface.\n"
        + "- Geometry never changes; the mask inherits the interface foreground colour.\n",
        encoding="utf-8",
    )
    findings = audit_design_system(repo)
    audit_path.write_text(json.dumps([asdict(item) for item in findings], indent=2), encoding="utf-8")
    return [json_path, md_path, audit_path]
