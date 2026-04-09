#!/usr/bin/env python3
"""Build a pre-computed scaffold for Claude changelog summarization.

Replaces detect-changes.sh. Reads the docs mirror's search index and git log
to produce a JSON scaffold with all deterministic fields filled in, plus a
self-contained prompt file for Claude.

Usage:
    python3 scripts/build-context.py <docs-mirror-dir> [lookback]
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ICONS = {
    "Claude Code CLI": ">_",
    "Agent SDK": "{}",
    "API Reference": "\u26a1",
    "Managed Agents": "\u25c8",
    "Platform": "\u25c8",
    "Resources": "\U0001f4da",
    "About Claude": "\u2139\ufe0f",
    "Agents & Tools": "\U0001f527",
    "Testing & Evaluation": "\U0001f9ea",
    "Release Notes": "\U0001f4cb",
    "Prompt Library": "\u270e",
    "Getting Started": "\U0001f680",
    "Other": "\U0001f4c4",
}

DIFF_LIMIT = 300
DIFF_LIMIT_LARGE = 150
SYNOPSIS_THRESHOLD = 10

SDK_LANGUAGES = {"python", "typescript", "ruby", "go", "csharp", "java", "cli"}


def categorize(filename: str) -> str:
    name = filename.removeprefix("docs/")
    if name.startswith("claude-code__"):
        return "Claude Code CLI"
    if name.startswith("docs__en__agent-sdk__"):
        return "Agent SDK"
    if name.startswith("docs__en__managed-agents__"):
        return "Managed Agents"
    if name.startswith("docs__en__api__"):
        return "API Reference"
    if name.startswith("docs__en__build-with-claude__") or name.startswith("docs__en__build-"):
        return "Platform"
    if name.startswith("docs__en__about-claude__"):
        return "About Claude"
    if name.startswith("docs__en__agents-and-tools__"):
        return "Agents & Tools"
    if name.startswith("docs__en__test-and-evaluate__"):
        return "Testing & Evaluation"
    if name.startswith("docs__en__release-notes__"):
        return "Release Notes"
    if name.startswith("docs__en__resources__prompt-library__"):
        return "Prompt Library"
    if name.startswith("docs__en__resources__"):
        return "Resources"
    if name in ("docs__en__get-started.md", "docs__en__intro.md"):
        return "Getting Started"
    return "Other"


def derive_url(filename: str) -> str:
    name = filename.removeprefix("docs/").removesuffix(".md")
    if name.startswith("claude-code__"):
        slug = name.removeprefix("claude-code__").replace("__", "/")
        return f"https://code.claude.com/docs/en/{slug}"
    path = name.replace("__", "/")
    return f"https://platform.claude.com/{path}"


def git(*args, cwd=None) -> str:
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd, capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()


def load_search_index(mirror_dir: str) -> dict[str, dict]:
    index_path = os.path.join(mirror_dir, "docs", ".search_index.json")
    try:
        with open(index_path) as f:
            data = json.load(f)
        index = data.get("index", data)
        return {
            entry["file_path"]: entry
            for entry in index.values()
            if "file_path" in entry
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"Warning: could not load search index: {exc}", file=sys.stderr)
        return {}


def detect_changed_files(mirror_dir: str, lookback: str) -> list[str]:
    raw = git(
        "log", f"--since={lookback}", "--diff-filter=AMR",
        "--name-only", "--pretty=", "--", "docs/*.md",
        cwd=mirror_dir,
    )
    if not raw:
        return []
    exclude = {"docs_manifest", "search_index", "changelog.md"}
    seen = set()
    result = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or any(ex in line for ex in exclude):
            continue
        if line not in seen:
            seen.add(line)
            result.append(line)
    result.sort()
    return result


def is_new_file(filename: str, mirror_dir: str, lookback: str) -> bool:
    out = git(
        "log", f"--since={lookback}", "--diff-filter=A",
        "--name-only", "--pretty=", "--", filename,
        cwd=mirror_dir,
    )
    return bool(out.strip())


def get_diff(filename: str, mirror_dir: str, lookback: str, limit: int) -> str:
    raw = git(
        "log", f"--since={lookback}", "-p", "--", filename,
        cwd=mirror_dir,
    )
    lines = raw.splitlines()[:limit]
    return "\n".join(lines)


def extract_h1(filepath: str) -> str | None:
    """Extract title from markdown headings only. No content guessing."""
    try:
        with open(filepath) as f:
            lines = [l.rstrip() for l in f.readlines()[:10]]
    except FileNotFoundError:
        return None
    for line in lines:
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            return m.group(1)
    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            return m.group(1)
    return None


def extract_api_title(filepath: str) -> str | None:
    """Build a deterministic title for API endpoint docs from heading + endpoint path.

    Parses the ## heading (operation verb) and the HTTP method line (resource path),
    then combines them: "Archive" + "/v1/agents/{id}/archive" → "Archive Agents".
    """
    try:
        with open(filepath) as f:
            lines = [l.rstrip() for l in f.readlines()[:10]]
    except FileNotFoundError:
        return None

    heading = None
    path = None
    for line in lines:
        if not heading:
            m = re.match(r"^##\s+(.+)$", line)
            if m:
                heading = m.group(1).strip()
        if not path:
            m = re.match(r"^\*\*(?:get|post|put|patch|delete)\*\*\s+`(/[^`]+)`", line)
            if m:
                path = m.group(1)
    if not heading:
        return None
    if not path:
        return heading

    # Extract resource segments: /v1/agents/{id}/archive → ["agents"]
    segments = [s for s in path.split("/")
                if s and s != "v1" and not s.startswith("{")]
    # Drop trailing action that matches the heading
    if segments and segments[-1].lower() == heading.lower():
        segments = segments[:-1]
    if not segments:
        return heading

    resource = segments[-1].replace("_", " ").replace("-", " ").title()
    return f"{heading} {resource}"


def humanize_filename(filename: str) -> str:
    name = filename.removeprefix("docs/").removesuffix(".md")
    for prefix in ("claude-code__", "docs__en__"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    last_segment = name.rsplit("__", 1)[-1]
    return last_segment.replace("-", " ").replace("_", " ").title()


def extract_sdk_key(filename: str) -> tuple[str, str] | None:
    """Detect SDK-language API docs and return (language, endpoint_path).

    Matches patterns like docs/docs__en__api__python__beta__agents__create.md
    Returns None for core API docs or non-API files.
    """
    name = filename.removeprefix("docs/")
    prefix = "docs__en__api__"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    # Extract the first segment (potential SDK language)
    parts = rest.split("__", 1)
    if len(parts) < 2:
        return None
    lang = parts[0]
    if lang not in SDK_LANGUAGES:
        return None
    return (lang, parts[1])


def group_api_entries(entries: list[dict]) -> list[dict]:
    """Collapse SDK-language variants of the same endpoint into one entry.

    For each unique endpoint path documented in multiple SDK languages,
    keeps one representative entry (preferring Python, then TypeScript).
    """
    core = []
    sdk_by_endpoint: dict[str, list[tuple[str, dict]]] = {}

    for entry in entries:
        # Recover filename from source_url to check SDK pattern
        url = entry.get("source_url", "")
        # Reconstruct filename from URL for matching
        # Platform URLs: https://platform.claude.com/docs/en/api/...
        path = url.replace("https://platform.claude.com/", "").replace("/", "__") + ".md"
        sdk_key = extract_sdk_key("docs/" + path)

        if sdk_key is None:
            core.append(entry)
        else:
            lang, endpoint = sdk_key
            sdk_by_endpoint.setdefault(endpoint, []).append((lang, entry))

    grouped = []
    singles = []

    # Preferred representative order
    pref = ["python", "typescript", "ruby", "go", "csharp", "java", "cli"]

    for endpoint, variants in sorted(sdk_by_endpoint.items()):
        if len(variants) == 1:
            singles.append(variants[0][1])
            continue

        langs = {lang for lang, _ in variants}
        # Pick representative
        rep_entry = None
        for p in pref:
            for lang, entry in variants:
                if lang == p:
                    rep_entry = entry
                    break
            if rep_entry:
                break
        if rep_entry is None:
            rep_entry = variants[0][1]

        # Build grouped entry
        grouped_entry = {
            "title": f"{rep_entry['title']} ({len(variants)} SDKs)",
            "is_new": any(e["is_new"] for _, e in variants),
            "summary": "",
            "changes": [],
            "source_url": rep_entry["source_url"],
            "_context": {
                **rep_entry.get("_context", {}),
                "sdk_languages": sorted(langs),
            },
        }
        grouped.append(grouped_entry)

    return core + grouped + singles


def get_title(filename: str, search_index: dict, mirror_dir: str) -> str:
    entry = search_index.get(filename)
    if entry and entry.get("title") and entry["title"] != "Untitled":
        return entry["title"]
    filepath = os.path.join(mirror_dir, filename)
    # For API endpoint docs, use deterministic heading+path title
    if categorize(filename) == "API Reference":
        api_title = extract_api_title(filepath)
        if api_title:
            return api_title
    h1 = extract_h1(filepath)
    if h1 and h1.strip():
        return h1
    return humanize_filename(filename)


def get_synopsis(filepath: str) -> str | None:
    try:
        with open(filepath) as f:
            lines = []
            for i, line in enumerate(f):
                if i >= 30:
                    break
                lines.append(line.rstrip())
            headings = [ln for ln in lines if re.match(r"^##?\s+", ln)]
            for line in f:
                m = re.match(r"^##\s+(.+)$", line.strip())
                if m:
                    headings.append(f"## {m.group(1)}")
        first_30 = "\n".join(lines)
        heading_outline = "\n".join(headings)
        return f"First 30 lines:\n{first_30}\n\nHeading outline:\n{heading_outline}"
    except FileNotFoundError:
        return None


def build_scaffold(
    changed_files: list[str],
    mirror_dir: str,
    lookback: str,
    search_index: dict,
) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_count = len(changed_files)
    if file_count > 500:
        diff_limit = 50
    elif file_count > 200:
        diff_limit = 75
    elif file_count > 50:
        diff_limit = DIFF_LIMIT_LARGE
    else:
        diff_limit = DIFF_LIMIT

    categories: dict[str, list[dict]] = {}
    for filename in changed_files:
        cat = categorize(filename)
        is_new = is_new_file(filename, mirror_dir, lookback)
        diff = get_diff(filename, mirror_dir, lookback, diff_limit)
        title = get_title(filename, search_index, mirror_dir)
        url = derive_url(filename)

        idx_entry = search_index.get(filename, {})
        context = {
            "content_preview": idx_entry.get("content_preview", ""),
            "keywords": idx_entry.get("keywords", []),
            "diff": diff,
        }
        diff_line_count = len(diff.splitlines()) if diff else 0
        if is_new or diff_line_count < SYNOPSIS_THRESHOLD:
            filepath = os.path.join(mirror_dir, filename)
            synopsis = get_synopsis(filepath)
            if synopsis:
                context["synopsis"] = synopsis

        entry = {
            "title": title,
            "is_new": is_new,
            "summary": "",
            "changes": [],
            "source_url": url,
            "_context": context,
        }
        categories.setdefault(cat, []).append(entry)

    # Group SDK-language duplicates within API Reference
    if "API Reference" in categories:
        before = len(categories["API Reference"])
        categories["API Reference"] = group_api_entries(categories["API Reference"])
        after = len(categories["API Reference"])
        if before != after:
            print(f"SDK grouping: {before} API entries → {after} grouped entries")

    sections = []
    for cat_name, entries in sorted(categories.items()):
        new_count = sum(1 for e in entries if e["is_new"])
        sections.append({
            "category": cat_name,
            "icon": ICONS.get(cat_name, "\U0001f4c4"),
            "docs_updated": len(entries) - new_count,
            "docs_new": new_count,
            "entries": entries,
        })

    return {
        "date": today,
        "has_updates": True,
        "highlights": [],
        "sections": sections,
    }


PROMPT_INSTRUCTIONS = """You are a technical writer generating a changelog for a development team.

# Task

Complete the changelog JSON below. For each entry with an empty `summary` and
`changes` array, use the `_context` (diff, preview, keywords) to write:

- `summary`: One sentence describing what changed (or what the doc covers if new)
- `changes`: Array of bullet strings, each formatted as:
  <strong>keyword</strong> &mdash; concise description of the change

Then write the top-level `highlights` array: 3-6 most impactful changes across
all categories, same bullet format.

# Rules

- Summarize what CHANGED based on the diff, not what the doc contains overall
- For new docs (is_new: true), give a richer summary since all content is new
- Write for senior engineers — be specific about APIs, configs, features
- Use &mdash; (not --) for em dashes in bullets
- Do NOT include _context fields in your output
- For grouped SDK entries (title ending with "N SDKs"), summarize the endpoint
  once and note which SDKs are covered. Do not write separate summaries per language.
- If entries were omitted due to volume, mention this in highlights.

Output ONLY the completed JSON. No markdown fences, no explanation."""


def validate_scaffold(scaffold: dict) -> list[str]:
    """Validate scaffold structure. Returns list of warnings (empty = clean)."""
    warnings = []
    if not scaffold.get("sections"):
        warnings.append("Scaffold has no sections")
        return warnings

    for i, section in enumerate(scaffold["sections"]):
        cat = section.get("category", "<missing>")
        for field in ("category", "icon", "docs_updated", "docs_new", "entries"):
            if field not in section:
                warnings.append(f"Section {i} ({cat}): missing '{field}'")

        entries = section.get("entries", [])
        if not isinstance(entries, list):
            warnings.append(f"Section {i} ({cat}): 'entries' is {type(entries).__name__}, not list")
            continue

        actual_new = sum(1 for e in entries if isinstance(e, dict) and e.get("is_new"))
        actual_updated = len(entries) - actual_new
        for j, entry in enumerate(entries):
            if not isinstance(entry, dict):
                warnings.append(f"Section {i} ({cat}), entry {j}: not a dict")
                continue
            title = entry.get("title", "")
            if not title or title == "Untitled":
                warnings.append(f"Section {i} ({cat}), entry {j}: title is {title!r}")
            if "source_url" not in entry:
                warnings.append(f"Section {i} ({cat}), entry {j} ({title}): missing source_url")

        if section.get("docs_new", 0) != actual_new or section.get("docs_updated", 0) != actual_updated:
            warnings.append(
                f"Section {i} ({cat}): count mismatch — "
                f"declared {section.get('docs_updated', 0)}u+{section.get('docs_new', 0)}n, "
                f"actual {actual_updated}u+{actual_new}n"
            )
    return warnings


def generate_prompt(scaffold: dict) -> str:
    scaffold_json = json.dumps(scaffold, indent=2, ensure_ascii=False)
    return f"""{PROMPT_INSTRUCTIONS}

# Scaffold

{scaffold_json}"""


def main():
    if len(sys.argv) < 2:
        print("Usage: build-context.py <docs-mirror-dir> [lookback]", file=sys.stderr)
        sys.exit(1)

    mirror_dir = sys.argv[1]
    lookback = sys.argv[2] if len(sys.argv) > 2 else "24 hours ago"

    search_index = load_search_index(mirror_dir)
    if search_index:
        print(f"Loaded search index: {len(search_index)} entries")
    else:
        print("Warning: running without search index (titles will be extracted from files)")

    changed = detect_changed_files(mirror_dir, lookback)
    github_output = os.environ.get("GITHUB_OUTPUT")

    if not changed:
        print(f"No documentation changes found in the last {lookback}")
        if github_output:
            with open(github_output, "a") as f:
                f.write("has_changes=false\n")
        sys.exit(0)

    print(f"Found {len(changed)} changed doc files")
    if github_output:
        with open(github_output, "a") as f:
            f.write("has_changes=true\n")
            f.write(f"file_count={len(changed)}\n")

    scaffold = build_scaffold(changed, mirror_dir, lookback, search_index)

    warnings = validate_scaffold(scaffold)
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    if warnings:
        print(f"Scaffold validation: {len(warnings)} warnings")
    else:
        print("Scaffold validation: clean")

    with open("/tmp/changelog-scaffold.json", "w") as f:
        json.dump(scaffold, f, indent=2, ensure_ascii=False)
    print(f"Scaffold written: {len(scaffold['sections'])} sections")

    prompt = generate_prompt(scaffold)
    with open("/tmp/changelog-prompt.md", "w") as f:
        f.write(prompt)
    print(f"Prompt written: {len(prompt)} chars")

    with open("/tmp/changelog-instructions.md", "w") as f:
        f.write(PROMPT_INSTRUCTIONS)
    print(f"Instructions written: {len(PROMPT_INSTRUCTIONS)} chars")


if __name__ == "__main__":
    main()
