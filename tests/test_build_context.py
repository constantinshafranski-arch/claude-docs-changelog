"""Tests for scripts/build-context.py pure functions."""

import json
import sys
import os
import importlib

# Add scripts dir to path so we can import build-context as a module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
bc = importlib.import_module("build-context")


class TestCategorize:
    def test_claude_code_cli(self):
        assert bc.categorize("docs/claude-code__hooks.md") == "Claude Code CLI"
        assert bc.categorize("docs/claude-code__settings.md") == "Claude Code CLI"

    def test_agent_sdk(self):
        assert bc.categorize("docs/docs__en__agent-sdk__python.md") == "Agent SDK"

    def test_api_reference(self):
        assert bc.categorize("docs/docs__en__api__service-tiers.md") == "API Reference"

    def test_platform(self):
        assert bc.categorize("docs/docs__en__build-with-claude__extended-thinking.md") == "Platform"

    def test_about_claude(self):
        assert bc.categorize("docs/docs__en__about-claude__models__overview.md") == "About Claude"

    def test_agents_and_tools(self):
        assert bc.categorize("docs/docs__en__agents-and-tools__tool-use.md") == "Agents & Tools"

    def test_testing_evaluation(self):
        assert bc.categorize("docs/docs__en__test-and-evaluate__eval.md") == "Testing & Evaluation"

    def test_release_notes(self):
        assert bc.categorize("docs/docs__en__release-notes__overview.md") == "Release Notes"

    def test_prompt_library(self):
        assert bc.categorize("docs/docs__en__resources__prompt-library__foo.md") == "Prompt Library"

    def test_resources(self):
        assert bc.categorize("docs/docs__en__resources__overview.md") == "Resources"

    def test_getting_started(self):
        assert bc.categorize("docs/docs__en__get-started.md") == "Getting Started"
        assert bc.categorize("docs/docs__en__intro.md") == "Getting Started"

    def test_other(self):
        assert bc.categorize("docs/something__random.md") == "Other"


class TestDeriveUrl:
    def test_claude_code(self):
        assert bc.derive_url("docs/claude-code__hooks.md") == "https://code.claude.com/docs/en/hooks"

    def test_claude_code_nested(self):
        assert bc.derive_url("docs/claude-code__vs-code.md") == "https://code.claude.com/docs/en/vs-code"

    def test_platform_simple(self):
        assert bc.derive_url("docs/docs__en__api__service-tiers.md") == "https://platform.claude.com/docs/en/api/service-tiers"

    def test_platform_deep(self):
        assert bc.derive_url("docs/docs__en__about-claude__models__overview.md") == "https://platform.claude.com/docs/en/about-claude/models/overview"

    def test_platform_build(self):
        assert bc.derive_url("docs/docs__en__build-with-claude__extended-thinking.md") == "https://platform.claude.com/docs/en/build-with-claude/extended-thinking"


class TestHumanizeFilename:
    def test_claude_code(self):
        assert bc.humanize_filename("docs/claude-code__hooks.md") == "Hooks"

    def test_platform_nested(self):
        assert bc.humanize_filename("docs/docs__en__build-with-claude__extended-thinking.md") == "Extended Thinking"

    def test_dashes(self):
        assert bc.humanize_filename("docs/claude-code__vs-code.md") == "Vs Code"


class TestGeneratePrompt:
    def test_contains_scaffold(self):
        scaffold = {"date": "2026-03-31", "has_updates": True, "highlights": [], "sections": []}
        prompt = bc.generate_prompt(scaffold)
        assert '"date": "2026-03-31"' in prompt
        assert "# Task" in prompt
        assert "# Rules" in prompt
        assert "# Scaffold" in prompt
        assert "Output ONLY the completed JSON" in prompt

    def test_no_markdown_fences_around_json(self):
        scaffold = {"date": "2026-03-31", "has_updates": True, "highlights": [], "sections": []}
        prompt = bc.generate_prompt(scaffold)
        assert "```json" not in prompt


class TestLoadSearchIndex:
    def test_missing_file_returns_empty(self, tmp_path):
        result = bc.load_search_index(str(tmp_path))
        assert result == {}

    def test_valid_index(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        index_data = {
            "version": 1,
            "index": {
                "/claude-code/hooks": {
                    "title": "Hooks reference",
                    "content_preview": "Hooks let you...",
                    "keywords": ["hooks"],
                    "word_count": 100,
                    "file_path": "docs/claude-code__hooks.md",
                }
            }
        }
        (docs_dir / ".search_index.json").write_text(json.dumps(index_data))
        result = bc.load_search_index(str(tmp_path))
        assert "docs/claude-code__hooks.md" in result
        assert result["docs/claude-code__hooks.md"]["title"] == "Hooks reference"
