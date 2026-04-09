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


class TestCategorizeManaged:
    def test_managed_agents(self):
        assert bc.categorize("docs/docs__en__managed-agents__overview.md") == "Managed Agents"
        assert bc.categorize("docs/docs__en__managed-agents__sessions.md") == "Managed Agents"


class TestExtractSdkKey:
    def test_python_sdk(self):
        result = bc.extract_sdk_key("docs/docs__en__api__python__beta__agents__create.md")
        assert result == ("python", "beta__agents__create.md")

    def test_typescript_sdk(self):
        result = bc.extract_sdk_key("docs/docs__en__api__typescript__beta__sessions__list.md")
        assert result == ("typescript", "beta__sessions__list.md")

    def test_cli_sdk(self):
        result = bc.extract_sdk_key("docs/docs__en__api__cli__beta__agents__create.md")
        assert result == ("cli", "beta__agents__create.md")

    def test_all_languages(self):
        for lang in ("python", "typescript", "ruby", "go", "csharp", "java", "cli"):
            result = bc.extract_sdk_key(f"docs/docs__en__api__{lang}__beta__agents.md")
            assert result is not None
            assert result[0] == lang

    def test_core_api_returns_none(self):
        assert bc.extract_sdk_key("docs/docs__en__api__beta__agents__create.md") is None

    def test_non_api_returns_none(self):
        assert bc.extract_sdk_key("docs/claude-code__hooks.md") is None

    def test_single_segment_returns_none(self):
        assert bc.extract_sdk_key("docs/docs__en__api__messages.md") is None


class TestGroupApiEntries:
    def _make_entry(self, lang, endpoint, is_new=False):
        url = f"https://platform.claude.com/docs/en/api/{lang}/{endpoint.replace('__', '/').removesuffix('.md')}"
        return {
            "title": f"{endpoint.replace('__', ' ').removesuffix('.md').title()}",
            "is_new": is_new,
            "summary": "",
            "changes": [],
            "source_url": url,
            "_context": {"diff": f"diff for {lang}", "keywords": ["test"]},
        }

    def _make_core_entry(self, name):
        return {
            "title": name,
            "is_new": False,
            "summary": "",
            "changes": [],
            "source_url": f"https://platform.claude.com/docs/en/api/{name}",
            "_context": {"diff": "core diff"},
        }

    def test_groups_same_endpoint(self):
        entries = [
            self._make_entry("python", "beta__agents__create.md"),
            self._make_entry("typescript", "beta__agents__create.md"),
            self._make_entry("ruby", "beta__agents__create.md"),
        ]
        result = bc.group_api_entries(entries)
        assert len(result) == 1
        assert "(3 SDKs)" in result[0]["title"]

    def test_preserves_core_entries(self):
        entries = [
            self._make_core_entry("messages"),
            self._make_entry("python", "beta__agents__create.md"),
            self._make_entry("typescript", "beta__agents__create.md"),
        ]
        result = bc.group_api_entries(entries)
        # 1 core + 1 grouped
        assert len(result) == 2
        core = [e for e in result if "SDKs)" not in e["title"]]
        assert len(core) == 1

    def test_single_language_not_grouped(self):
        entries = [self._make_entry("python", "beta__special.md")]
        result = bc.group_api_entries(entries)
        assert len(result) == 1
        assert "SDKs)" not in result[0]["title"]

    def test_representative_prefers_python(self):
        entries = [
            self._make_entry("ruby", "beta__agents.md"),
            self._make_entry("python", "beta__agents.md"),
            self._make_entry("go", "beta__agents.md"),
        ]
        result = bc.group_api_entries(entries)
        assert len(result) == 1
        assert "python" in result[0]["source_url"]

    def test_is_new_any(self):
        entries = [
            self._make_entry("python", "beta__new.md", is_new=False),
            self._make_entry("typescript", "beta__new.md", is_new=True),
        ]
        result = bc.group_api_entries(entries)
        assert result[0]["is_new"] is True

    def test_sdk_languages_in_context(self):
        entries = [
            self._make_entry("python", "beta__agents.md"),
            self._make_entry("go", "beta__agents.md"),
        ]
        result = bc.group_api_entries(entries)
        langs = result[0]["_context"]["sdk_languages"]
        assert "go" in langs
        assert "python" in langs


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
