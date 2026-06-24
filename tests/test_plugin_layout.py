import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "xpk-decompress"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_shared_skill_layout_replaces_legacy_claude_skill() -> None:
    skill_dir = ROOT / "skills" / PLUGIN_NAME

    assert skill_dir.joinpath("SKILL.md").is_file()
    assert skill_dir.joinpath("scripts", "xpk_nuke_decompress.py").is_file()
    assert not ROOT.joinpath(".claude", "skills", PLUGIN_NAME).exists()


def test_claude_marketplace_manifest_points_at_root_plugin() -> None:
    plugin = read_json(".claude-plugin/plugin.json")
    marketplace = read_json(".claude-plugin/marketplace.json")
    entry = marketplace["plugins"][0]

    assert plugin["name"] == PLUGIN_NAME
    assert VERSION_RE.match(plugin["version"])
    assert "Decompress Amiga XPK/NUKE" in plugin["description"]
    assert marketplace["name"] == PLUGIN_NAME
    assert entry["name"] == PLUGIN_NAME
    assert entry["source"] == "./"
    assert entry["version"] == plugin["version"]


def test_codex_marketplace_manifest_points_at_root_plugin() -> None:
    plugin = read_json(".codex-plugin/plugin.json")
    marketplace = read_json(".agents/plugins/marketplace.json")
    entry = marketplace["plugins"][0]

    assert plugin["name"] == PLUGIN_NAME
    assert VERSION_RE.match(plugin["version"])
    assert plugin["skills"] == "./skills/"
    assert plugin["interface"]["displayName"] == "Amiga XPK Decompressor"
    assert marketplace["name"] == PLUGIN_NAME
    assert entry["name"] == PLUGIN_NAME
    assert entry["source"] == {"source": "local", "path": "./"}
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }


def test_skill_frontmatter_stays_codex_compatible() -> None:
    skill = ROOT.joinpath("skills", PLUGIN_NAME, "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    top_level_keys = {
        line.split(":", 1)[0]
        for line in frontmatter.splitlines()
        if line and not line.startswith(" ")
    }

    assert "name: xpk-decompress" in frontmatter
    assert "description:" in frontmatter
    assert "allowed-tools" not in top_level_keys
    assert "argument-hint" not in top_level_keys
    assert "metadata:" in frontmatter
    assert "  argument-hint:" in frontmatter


def test_decompressor_script_is_importable_from_shared_skill() -> None:
    script = ROOT / "skills" / PLUGIN_NAME / "scripts" / "xpk_nuke_decompress.py"
    spec = importlib.util.spec_from_file_location("xpk_nuke_decompress", script)

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert callable(module.decompress_xpk)
    assert callable(module.main)
