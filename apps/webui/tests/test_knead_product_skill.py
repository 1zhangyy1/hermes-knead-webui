"""knead-product skill: format (HARDLINE authoring rules) + builder-prompt wiring."""

import re
from pathlib import Path

from api.config import REPO_ROOT  # NOTE: this is apps/webui, not the git root
from api.product_context import product_ephemeral_prompt

GIT_ROOT = Path(REPO_ROOT).parents[1]
SKILL_DIR = GIT_ROOT / ".agents" / "skills" / "knead-product"
SKILL_MD = SKILL_DIR / "SKILL.md"


def test_skill_md_exists():
    assert SKILL_MD.is_file()


def test_description_hardline():
    text = SKILL_MD.read_text(encoding="utf-8")
    m = re.search(r"^description: (.*)$", text, re.MULTILINE)
    assert m, "frontmatter description missing"
    desc = m.group(1).strip()
    assert len(desc) <= 60, f"description too long: {len(desc)}"
    assert desc.endswith("."), "description must end with a period"
    assert "knead-product" not in desc.lower(), "must not repeat the skill name"
    for banned in ("powerful", "comprehensive", "seamless", "advanced"):
        assert banned not in desc.lower()


def test_modern_section_order():
    text = SKILL_MD.read_text(encoding="utf-8")
    sections = [
        "# Knead Product Skill",
        "## When to Use",
        "## Prerequisites",
        "## How to Run",
        "## Quick Reference",
        "## Procedure",
        "## Pitfalls",
        "## Verification",
    ]
    positions = [text.find(s) for s in sections]
    assert all(p >= 0 for p in positions), f"missing sections: {[s for s, p in zip(sections, positions) if p < 0]}"
    assert positions == sorted(positions), "sections out of order"


def test_supporting_files_exist():
    assert (SKILL_DIR / "references" / "layouts.md").is_file()
    assert (SKILL_DIR / "references" / "bridge.md").is_file()
    assert (SKILL_DIR / "templates" / "minimal-canvas.html").is_file()


def test_references_cover_contract():
    layouts = (SKILL_DIR / "references" / "layouts.md").read_text(encoding="utf-8")
    for layout in ("chat_only", "chat_left_canvas_right", "canvas_full"):
        assert layout in layouts
    bridge = (SKILL_DIR / "references" / "bridge.md").read_text(encoding="utf-8")
    assert "window.NextAI.chat.send" in bridge
    assert "product-bridge-sdk.js" in bridge


def test_template_keeps_bridge_before_app():
    html = (SKILL_DIR / "templates" / "minimal-canvas.html").read_text(encoding="utf-8")
    assert html.find("product-bridge-sdk.js") < html.find("./app.js")


def test_builder_prompt_points_to_skills():
    prompt = product_ephemeral_prompt(
        {"title": "Demo", "scope": "product_builder", "ui_mode": "workspace",
         "product_layout": "canvas_full", "tools": ["skills", "file"]}
    )
    assert "knead-product" in prompt
    assert "impeccable" in prompt


def test_use_prompt_does_not_load_builder_skills():
    prompt = product_ephemeral_prompt(
        {"title": "Demo", "scope": "product_usage", "ui_mode": "workspace",
         "product_layout": "canvas_full", "tools": ["skills"]}
    )
    assert "knead-product" not in prompt
