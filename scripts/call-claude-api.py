#!/usr/bin/env python3
"""Call the Anthropic API directly to generate changelog JSON.

Reads the pre-built prompt from build-context.py and makes one or more API calls
with forced tool use for structured output. If the prompt exceeds the char budget,
sections are split into chunks and called separately, then merged.

Usage:
    ANTHROPIC_API_KEY=... python3 scripts/call-claude-api.py
"""

import json
import os
import sys

import anthropic

SCAFFOLD_PATH = "/tmp/changelog-scaffold.json"
INSTRUCTIONS_PATH = "/tmp/changelog-instructions.md"
PROMPT_PATH = "/tmp/changelog-prompt.md"
OUTPUT_PATH = "/tmp/claude-changelog.json"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16384
CHAR_BUDGET = 2_000_000  # ~667k tokens at ~3 chars/token, safe within Sonnet's 1M window

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
                            "Managed Agents",
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

TOOLS = [{
    "name": "output_changelog",
    "description": "Output the completed changelog JSON",
    "input_schema": CHANGELOG_SCHEMA,
}]
TOOL_CHOICE = {"type": "tool", "name": "output_changelog"}


def call_api(client: anthropic.Anthropic, prompt: str) -> dict:
    """Make a single API call and return the structured JSON from tool use."""
    estimated_tokens = len(prompt) // 4
    print(f"  API call: ~{estimated_tokens:,} estimated input tokens")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            tools=TOOLS,
            tool_choice=TOOL_CHOICE,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIStatusError as e:
        print(f"Error: API returned {e.status_code}: {e.message}", file=sys.stderr)
        sys.exit(1)

    tool_block = next(
        (b for b in response.content if b.type == "tool_use"),
        None,
    )
    if not tool_block:
        print("Error: No tool_use block in response", file=sys.stderr)
        print(f"Response: {response.content}", file=sys.stderr)
        sys.exit(1)

    print(f"  Usage: {response.usage.input_tokens} input + {response.usage.output_tokens} output tokens")
    return tool_block.input


def build_chunk_prompt(instructions: str, scaffold: dict, sections: list[dict]) -> str:
    """Build a prompt for a subset of sections."""
    chunk_scaffold = {
        "date": scaffold["date"],
        "has_updates": True,
        "highlights": [],
        "sections": sections,
    }
    scaffold_json = json.dumps(chunk_scaffold, indent=2, ensure_ascii=False)
    return f"{instructions}\n\n# Scaffold\n\n{scaffold_json}"


def split_into_chunks(
    instructions: str, sections: list[dict],
) -> list[list[dict]]:
    """Split sections into chunks that each fit within CHAR_BUDGET.

    Tries to keep sections intact. If a single section exceeds the budget,
    its entries are split into sub-sections with the same category metadata.
    """
    overhead = len(instructions) + 200  # instructions + JSON boilerplate
    chunks: list[list[dict]] = []
    current_chunk: list[dict] = []
    current_size = overhead

    for section in sections:
        section_size = len(json.dumps(section, ensure_ascii=False))

        if section_size + overhead > CHAR_BUDGET:
            # This section alone exceeds budget — split its entries
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = overhead

            entries = section.get("entries", [])
            sub_entries: list[dict] = []
            sub_size = overhead + 500  # section metadata overhead

            for entry in entries:
                entry_size = len(json.dumps(entry, ensure_ascii=False))
                if sub_size + entry_size > CHAR_BUDGET and sub_entries:
                    # Flush current sub-section
                    sub_section = {**section, "entries": sub_entries}
                    chunks.append([sub_section])
                    sub_entries = []
                    sub_size = overhead + 500
                sub_entries.append(entry)
                sub_size += entry_size

            if sub_entries:
                sub_section = {**section, "entries": sub_entries}
                chunks.append([sub_section])
            continue

        if current_size + section_size > CHAR_BUDGET and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = overhead

        current_chunk.append(section)
        current_size += section_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Load instructions and scaffold separately for potential splitting
    try:
        with open(INSTRUCTIONS_PATH) as f:
            instructions = f.read()
    except FileNotFoundError:
        instructions = None

    try:
        with open(SCAFFOLD_PATH) as f:
            scaffold = json.load(f)
    except FileNotFoundError:
        scaffold = None

    # Fall back to combined prompt if separate files aren't available
    if instructions is None or scaffold is None:
        try:
            with open(PROMPT_PATH) as f:
                prompt = f.read()
        except FileNotFoundError:
            print(f"Error: Neither split files nor {PROMPT_PATH} found", file=sys.stderr)
            sys.exit(1)

        print(f"Prompt loaded: {len(prompt):,} chars (combined mode)")
        client = anthropic.Anthropic(api_key=api_key)
        data = call_api(client, prompt)
    else:
        sections = scaffold.get("sections", [])
        full_prompt = build_chunk_prompt(instructions, scaffold, sections)
        prompt_size = len(full_prompt)
        print(f"Prompt size: {prompt_size:,} chars ({prompt_size // 4:,} estimated tokens)")

        client = anthropic.Anthropic(api_key=api_key)

        if prompt_size <= CHAR_BUDGET:
            # Single call — fits in context
            print("Single API call (within budget)")
            data = call_api(client, full_prompt)
        else:
            # Split sections into chunks that fit
            chunks = split_into_chunks(instructions, sections)
            print(f"Prompt exceeds budget — splitting into {len(chunks)} chunks")

            all_sections = []
            all_highlights = []

            for i, chunk_sections in enumerate(chunks):
                cat_names = [s["category"] for s in chunk_sections]
                print(f"Chunk {i + 1}/{len(chunks)}: {', '.join(cat_names)}")
                chunk_prompt = build_chunk_prompt(instructions, scaffold, chunk_sections)
                chunk_data = call_api(client, chunk_prompt)

                all_sections.extend(chunk_data.get("sections", []))
                all_highlights.extend(chunk_data.get("highlights", []))

            # Merge: deduplicate highlights, cap at 6
            seen = set()
            unique_highlights = []
            for h in all_highlights:
                if h not in seen:
                    seen.add(h)
                    unique_highlights.append(h)
            unique_highlights = unique_highlights[:6]

            data = {
                "date": scaffold["date"],
                "has_updates": True,
                "highlights": unique_highlights,
                "sections": all_sections,
            }

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


if __name__ == "__main__":
    main()
