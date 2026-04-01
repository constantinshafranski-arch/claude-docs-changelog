#!/usr/bin/env python3
"""Call the Anthropic API directly to generate changelog JSON.

Replaces claude-code-action to eliminate permission-denial failures.
Reads the pre-built prompt from build-context.py and makes a single API call
with forced tool use for structured output.

Usage:
    ANTHROPIC_API_KEY=... python3 scripts/call-claude-api.py
"""

import json
import os
import sys

import anthropic

PROMPT_PATH = "/tmp/changelog-prompt.md"
OUTPUT_PATH = "/tmp/claude-changelog.json"

# Same schema that was previously passed via --json-schema
CHANGELOG_SCHEMA = {
    "type": "object",
    "required": ["date", "has_updates", "highlights", "sections"],
    "additionalProperties": False,
    "properties": {
        "date": {"type": "string"},
        "has_updates": {"type": "boolean"},
        "highlights": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["category", "icon", "docs_updated", "docs_new", "entries"],
                "additionalProperties": False,
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "Claude Code CLI", "Agent SDK", "API Reference",
                            "Platform", "Resources", "About Claude",
                            "Agents & Tools", "Testing & Evaluation",
                            "Release Notes", "Prompt Library",
                            "Getting Started", "Other",
                        ],
                    },
                    "icon": {"type": "string"},
                    "docs_updated": {"type": "integer"},
                    "docs_new": {"type": "integer"},
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["title", "is_new", "summary", "changes", "source_url"],
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "is_new": {"type": "boolean"},
                                "summary": {"type": "string"},
                                "changes": {"type": "array", "items": {"type": "string"}},
                                "source_url": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    try:
        with open(PROMPT_PATH) as f:
            prompt = f.read()
    except FileNotFoundError:
        print(f"Error: {PROMPT_PATH} not found — run build-context.py first", file=sys.stderr)
        sys.exit(1)

    print(f"Prompt loaded: {len(prompt)} chars")

    client = anthropic.Anthropic(api_key=api_key)

    # Use forced tool_use for guaranteed structured output
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        tools=[{
            "name": "output_changelog",
            "description": "Output the completed changelog JSON",
            "input_schema": CHANGELOG_SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "output_changelog"},
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract the tool call input (our structured JSON)
    tool_block = next(
        (b for b in response.content if b.type == "tool_use"),
        None,
    )
    if not tool_block:
        print("Error: No tool_use block in response", file=sys.stderr)
        print(f"Response: {response.content}", file=sys.stderr)
        sys.exit(1)

    data = tool_block.input

    # Strip _context fields (safety net)
    for section in data.get("sections", []):
        for entry in section.get("entries", []):
            entry.pop("_context", None)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(data, f)

    section_count = len(data.get("sections", []))
    entry_count = sum(len(s.get("entries", [])) for s in data.get("sections", []))
    highlight_count = len(data.get("highlights", []))
    print(f"Output: {section_count} sections, {entry_count} entries, {highlight_count} highlights")
    print(f"Usage: {response.usage.input_tokens} input + {response.usage.output_tokens} output tokens")


if __name__ == "__main__":
    main()
