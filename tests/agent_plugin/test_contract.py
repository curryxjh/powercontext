from __future__ import annotations

import json
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "integrations" / "agent-plugin" / "powercontext"


def test_agent_plugin_manifest_uses_portable_schema_fields() -> None:
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))

    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert manifest["name"] == "powercontext"
    assert manifest["description"]
    assert manifest["license"] == "Apache-2.0"
    assert "mcp" in manifest["keywords"]

    allowed_fields = {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
    assert set(manifest) <= allowed_fields
    assert "skills" not in manifest
    assert "mcpServers" not in manifest


def test_agent_plugin_mcp_configuration_is_portable_and_secret_free() -> None:
    configuration = json.loads((PLUGIN_ROOT / "mcp.json").read_text(encoding="utf-8"))

    assert configuration == {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {
            "powercontext": {
                "type": "streamable-http",
                "url": "http://127.0.0.1:8000/mcp",
            }
        },
    }
    assert "headers" not in configuration["mcpServers"]["powercontext"]
    assert "env_http_headers" not in configuration["mcpServers"]["powercontext"]
    assert "POWERCONTEXT" not in json.dumps(configuration)


def test_project_context_skill_is_reusable_and_preserves_powercontext_workflows() -> None:
    content = (PLUGIN_ROOT / "skills" / "project-context" / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(content.split("---", 2)[1])

    assert frontmatter == {
        "name": "project-context",
        "description": (
            "Use PowerContext project memory and handoff tools through MCP when continuing prior work, "
            "recalling decisions, maintaining durable memory, or transferring work across tasks, sessions, or agents."
        ),
    }
    for required in (
        "search_memory",
        "list_memory_entries",
        "get_memory_entry",
        "remember_memory",
        "revise_memory_entry",
        "retire_memory_entry",
        "capture_content_source",
        "activate_handoff",
        "`boundary_source`",
        "finalize_handoff",
        'selection: "prepared"',
        "commit_handoff",
        "Degrade Safely",
    ):
        assert required in content

    forbidden_fragments = (
        "Codex",
        "OpenCode",
        "UserPromptSubmit",
        "prompt capture",
        "POWERCONTEXT_CODEX",
        "additionalContext",
    )
    for forbidden in forbidden_fragments:
        assert forbidden not in content


def test_agent_plugin_readme_documents_server_and_auth_boundaries() -> None:
    content = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")

    assert "powercontext server run" in content
    assert "http://127.0.0.1:8000/mcp" in content
    assert "static credentials" in content
    assert "does not embed" in content
    assert "storage" in content
