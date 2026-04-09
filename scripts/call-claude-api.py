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


# ---------------------------------------------------------------------------
# Validation helpers — defense-in-depth for API responses
# ---------------------------------------------------------------------------

def validate_entry(entry: object, context: str) -> dict | None:
    """Validate and normalize a single entry. Returns cleaned entry or None."""
    if not isinstance(entry, dict):
        print(f"Warning: {context}: dropping non-dict entry ({type(entry).__name__})", file=sys.stderr)
        return None
    required = ("title", "is_new", "summary", "changes", "source_url")
    for field in required:
        if field not in entry:
            print(f"Warning: {context}: entry missing '{field}' (title={entry.get('title', '?')!r})", file=sys.stderr)
    changes = entry.get("changes", [])
    if not isinstance(changes, list):
        print(f"Warning: {context}: 'changes' is {type(changes).__name__}, resetting to []", file=sys.stderr)
        entry["changes"] = []
    else:
        entry["changes"] = [c for c in changes if isinstance(c, str)]
    return entry


def validate_api_response(chunk_data: object, label: str) -> dict:
    """Validate structure returned by a single API call. Returns cleaned data."""
    empty = {"date": "", "has_updates": True, "highlights": [], "sections": []}
    if not isinstance(chunk_data, dict):
        print(f"Error: {label}: API returned {type(chunk_data).__name__}, expected dict", file=sys.stderr)
        return empty

    # Validate sections
    sections = chunk_data.get("sections", [])
    if not isinstance(sections, list):
        print(f"Warning: {label}: 'sections' is {type(sections).__name__}, treating as empty", file=sys.stderr)
        sections = []

    cleaned_sections = []
    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            print(f"Warning: {label}: sections[{i}] is {type(section).__name__}, skipping", file=sys.stderr)
            continue
        if "category" not in section:
            print(f"Warning: {label}: sections[{i}] missing 'category', skipping", file=sys.stderr)
            continue
        cat = section["category"]
        entries = section.get("entries", [])
        if not isinstance(entries, list):
            print(f"Warning: {label}: {cat} entries is {type(entries).__name__}, treating as empty", file=sys.stderr)
            entries = []
        cleaned_entries = []
        for j, entry in enumerate(entries):
            clean = validate_entry(entry, f"{label}/{cat}[{j}]")
            if clean is not None:
                cleaned_entries.append(clean)
        section["entries"] = cleaned_entries
        cleaned_sections.append(section)

    chunk_data["sections"] = cleaned_sections

    # Validate highlights
    highlights = chunk_data.get("highlights", [])
    if not isinstance(highlights, list):
        chunk_data["highlights"] = []
    else:
        chunk_data["highlights"] = [h for h in highlights if isinstance(h, str)]

    return chunk_data


# ---------------------------------------------------------------------------
# API and prompt helpers
# ---------------------------------------------------------------------------

def call_api(client: anthropic.Anthropic, prompt: str) -> dict:
    """Make a single API call and return the structured JSON from tool use."""
    estimated_tokens = len(prompt) // 3
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


def recount_section_stats(sections: list[dict]) -> None:
    """Recalculate docs_updated/docs_new from actual entries."""
    for section in sections:
        entries = section.get("entries", [])
        new_count = sum(1 for e in entries if isinstance(e, dict) and e.get("is_new"))
        updated_count = len(entries) - new_count
        old_new = section.get("docs_new", 0)
        old_updated = section.get("docs_updated", 0)
        if old_new != new_count or old_updated != updated_count:
            print(f"  Recount {section.get('category', '?')}: "
                  f"{old_updated}u+{old_new}n -> {updated_count}u+{new_count}n")
        section["docs_updated"] = updated_count
        section["docs_new"] = new_count


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
        data = validate_api_response(data, "single-call")
    else:
        sections = scaffold.get("sections", [])
        scaffold_entry_count = sum(len(s.get("entries", [])) for s in sections)
        full_prompt = build_chunk_prompt(instructions, scaffold, sections)
        prompt_size = len(full_prompt)
        print(f"Prompt size: {prompt_size:,} chars ({prompt_size // 3:,} estimated tokens)")

        client = anthropic.Anthropic(api_key=api_key)

        if prompt_size <= CHAR_BUDGET:
            # Single call — fits in context
            print("Single API call (within budget)")
            data = call_api(client, full_prompt)
            data = validate_api_response(data, "single-call")
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

                # Defense-in-depth: warn if chunk is close to context limit
                est_tokens = len(chunk_prompt) // 3
                if est_tokens > 900_000:
                    print(f"  Warning: chunk is ~{est_tokens:,} tokens, close to 1M limit", file=sys.stderr)

                chunk_data = call_api(client, chunk_prompt)
                chunk_data = validate_api_response(chunk_data, f"chunk {i + 1}/{len(chunks)}")

                all_sections.extend(chunk_data.get("sections", []))
                all_highlights.extend(chunk_data.get("highlights", []))

            # Data loss tracking
            response_entry_count = sum(len(s.get("entries", [])) for s in all_sections)
            if response_entry_count < scaffold_entry_count:
                print(f"Warning: API returned {response_entry_count} entries, "
                      f"scaffold had {scaffold_entry_count} "
                      f"({scaffold_entry_count - response_entry_count} dropped)",
                      file=sys.stderr)

            # Merge sections with the same category
            merged_sections: dict[str, dict] = {}
            for section in all_sections:
                cat = section["category"]
                if cat in merged_sections:
                    merged_sections[cat]["entries"].extend(section.get("entries", []))
                else:
                    merged_sections[cat] = {**section, "entries": list(section.get("entries", []))}

            # Preserve original scaffold ordering
            scaffold_order = [s["category"] for s in sections]
            ordered_sections = []
            seen_cats: set[str] = set()
            for cat in scaffold_order:
                if cat in merged_sections and cat not in seen_cats:
                    ordered_sections.append(merged_sections[cat])
                    seen_cats.add(cat)
            for cat, sec in merged_sections.items():
                if cat not in seen_cats:
                    ordered_sections.append(sec)

            # Recalculate counts from actual merged entries
            recount_section_stats(ordered_sections)

            # Data loss tracking (post-merge)
            merged_entry_count = sum(len(s.get("entries", [])) for s in ordered_sections)
            if merged_entry_count < response_entry_count:
                print(f"Warning: merge reduced entries from {response_entry_count} "
                      f"to {merged_entry_count}", file=sys.stderr)

            # Deduplicate highlights, cap at 6
            seen_h: set[str] = set()
            unique_highlights = []
            for h in all_highlights:
                if h not in seen_h:
                    seen_h.add(h)
                    unique_highlights.append(h)
            unique_highlights = unique_highlights[:6]

            data = {
                "date": scaffold["date"],
                "has_updates": True,
                "highlights": unique_highlights,
                "sections": ordered_sections,
            }

    # Strip _context fields (safety net)
    for section in data.get("sections", []):
        for entry in section.get("entries", []):
            if isinstance(entry, dict):
                entry.pop("_context", None)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(data, f)

    section_count = len(data.get("sections", []))
    entry_count = sum(len(s.get("entries", [])) for s in data.get("sections", []))
    highlight_count = len(data.get("highlights", []))
    print(f"Output: {section_count} sections, {entry_count} entries, {highlight_count} highlights")


if __name__ == "__main__":
    main()
