# Pre-computed Scaffold for Claude Summarization

**Date:** 2026-03-31
**Status:** Draft
**Problem:** The "Summarize with Claude" pipeline step fails on high-volume days (28+ changed docs) because Claude exhausts its turn limit reading files, deriving URLs, and categorizing — all tasks that are deterministic and don't need AI.

---

## Goal

Shift all deterministic work (categorization, URL derivation, title extraction, counting, icon mapping) into a pre-processing Python script. Claude receives a fully assembled scaffold with diffs inlined, and only writes `summary`, `changes`, and `highlights`. Zero tool calls required.

## Success Criteria

- Pipeline succeeds on 28+ file change days without hitting max-turns
- Claude uses 1 turn (3 max as safety) and 0 tool calls
- Cost per run stays under $0.15 (Haiku)
- No regression in changelog quality

---

## Architecture

```
Current:
  detect-changes.sh → CONTEXT.md → Claude (Read x N, categorize, derive URLs, count, summarize)
                                     ↑ 10+ turns, 20+ tool calls, $0.80+

New:
  build-context.py → scaffold.json + prompt → Claude (read prompt, write summaries)
                                                ↑ 1 turn, 0 tool calls, ~$0.05
```

---

## New Script: `scripts/build-context.py`

Replaces `scripts/detect-changes.sh`. Single Python script, no external dependencies (stdlib only: `json`, `subprocess`, `sys`, `os`, `re`).

### Arguments

```
python3 scripts/build-context.py <docs-mirror-dir> [lookback]
```

- `docs-mirror-dir`: path to the cloned docs mirror (e.g., `docs-mirror`)
- `lookback`: git log time window (default: `"24 hours ago"`)

### Data Sources (all from the mirror repo)

1. **`docs/.search_index.json`** — Pre-computed index keyed by URL path. Each entry has `title`, `content_preview` (200 chars), `keywords` (top 20), `word_count`, and `file_path` (the filename in the repo). Built by the mirror's CI every 3 hours.

2. **`git log`** — Changed files, new-vs-updated detection, diffs.

Note: `paths_manifest.json` exists in the mirror but is NOT used — its 5 broad category buckets don't map cleanly to our 12 changelog categories. Filename-based prefix matching is simpler and more precise.

### Processing Steps

1. **Load metadata**
   - Parse `docs/.search_index.json` → build a `filename → {title, content_preview, keywords}` map using each entry's `file_path` field as the key (e.g., `docs/claude-code__hooks.md` → entry)
   - `paths_manifest.json` is NOT used — its 5 broad category buckets are too coarse for our 12 changelog categories. We use filename-based prefix matching instead (same logic as the current shell script).

2. **Detect changes**
   - Run `git log --since=<lookback> --diff-filter=AMR --name-only --pretty="" -- 'docs/*.md'`
   - Exclude `docs_manifest`, `search_index`, `changelog.md`
   - Deduplicate and sort

3. **For each changed file:**
   - Look up title and content_preview from search index using the filename as key (fallback: extract H1 from file, or humanize filename)
   - Determine category from filename prefix (see mapping below)
   - Detect new vs updated via `git log --diff-filter=A`
   - Extract diff via `git log --since=<lookback> -p -- <file>` (truncated to 300 lines)
   - Derive source URL:
     - `claude-code__X.md` → strip prefix, replace `__` with `/`, drop `.md` → `https://code.claude.com/docs/en/X`
     - `docs__en__A__B.md` → replace ALL `__` with `/`, drop `.md` → `docs/en/A/B` → `https://platform.claude.com/docs/en/A/B` (canonical, returns 200; the old `/en/docs/` path was a 307 redirect)
   - For new files or files with very short diffs (< 10 lines): also extract a file synopsis (H1 + all H2 headings, first 30 lines)

4. **Build scaffold JSON** — Group entries by category, compute `docs_new` / `docs_updated` counts, assign icons

5. **Generate prompt file** — Embed scaffold + instructions into `/tmp/changelog-prompt.md`

6. **Set GitHub Actions outputs** — `has_changes=true/false`, `file_count=N`

### Category Mapping (path prefix → changelog category)

| Path prefix | Changelog category |
|---|---|
| `claude-code__*` (filename) | Claude Code CLI |
| `/docs/en/agent-sdk/` | Agent SDK |
| `/docs/en/api/` | API Reference |
| `/docs/en/build-with-claude/` | Platform |
| `/docs/en/about-claude/` | About Claude |
| `/docs/en/agents-and-tools/` | Agents & Tools |
| `/docs/en/test-and-evaluate/` | Testing & Evaluation |
| `/docs/en/release-notes/` | Release Notes |
| `/docs/en/resources/prompt-library/` | Prompt Library |
| `/docs/en/resources/` | Resources |
| `/docs/en/get-started`, `/docs/en/intro` | Getting Started |
| Everything else | Other |

### Icon Mapping (static dict)

```python
ICONS = {
    "Claude Code CLI": ">_",
    "Agent SDK": "{}",
    "API Reference": "⚡",
    "Platform": "◈",
    "Resources": "📚",
    "About Claude": "ℹ️",
    "Agents & Tools": "🔧",
    "Testing & Evaluation": "🧪",
    "Release Notes": "📋",
    "Prompt Library": "✎",
    "Getting Started": "🚀",
    "Other": "📄",
}
```

---

## Scaffold JSON Format

Written to `/tmp/changelog-scaffold.json`. This is the JSON that gets embedded in the prompt.

```json
{
  "date": "2026-03-31",
  "has_updates": true,
  "highlights": [],
  "sections": [
    {
      "category": "Claude Code CLI",
      "icon": ">_",
      "docs_updated": 13,
      "docs_new": 0,
      "entries": [
        {
          "title": "Hooks",
          "is_new": false,
          "summary": "",
          "changes": [],
          "source_url": "https://code.claude.com/docs/en/hooks",
          "_context": {
            "content_preview": "Hooks let you run shell commands...",
            "keywords": ["hooks", "pre-tool-use", "post-tool-use", "shell"],
            "diff": "actual git diff, truncated to 300 lines"
          }
        }
      ]
    }
  ]
}
```

### `_context` fields

Ephemeral per-entry metadata for Claude's use. NOT part of the output schema. Stripped via:
- `"additionalProperties": false` on the entry object in the JSON schema (primary)
- Python one-liner in the "Save output" workflow step (safety net)

For new files or entries with very short diffs (< 10 lines), `_context` also includes:
- `synopsis`: H1 + H2 headings + first 30 lines of the file

---

## Generated Prompt: `/tmp/changelog-prompt.md`

The build script writes a self-contained prompt:

```markdown
You are a technical writer generating a changelog for a development team.

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

# Scaffold

<the full scaffold JSON>

Output ONLY the completed JSON. No markdown fences, no explanation.
```

---

## Workflow Changes: `.github/workflows/daily-changelog.yml`

### Step 3: "Detect doc changes" → "Build changelog context"

```yaml
- name: Build changelog context
  id: detect
  run: python3 scripts/build-context.py docs-mirror "${{ env.LOOKBACK }}"
```

Same output interface: sets `has_changes` and `file_count` in `$GITHUB_OUTPUT`.

### New Step: "Load prompt"

A small step between "Build changelog context" and "Summarize with Claude" reads the generated prompt file and sets it as a step output:

```yaml
- name: Load prompt
  if: steps.detect.outputs.has_changes == 'true'
  id: prompt
  run: |
    {
      echo 'content<<PROMPT_EOF'
      cat /tmp/changelog-prompt.md
      echo 'PROMPT_EOF'
    } >> "$GITHUB_OUTPUT"
```

This uses GitHub Actions' multiline output syntax (heredoc delimiter). The 30-50KB prompt is well under the ~1MB step output limit.

### Step 5: "Summarize with Claude"

```yaml
- name: Summarize with Claude
  if: steps.detect.outputs.has_changes == 'true'
  id: claude
  uses: anthropics/claude-code-action@v1
  with:
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
    prompt: ${{ steps.prompt.outputs.content }}
    claude_args: >-
      --model haiku
      --max-turns 3
      --allowedTools Read
      --json-schema '{"type":"object","required":["date","has_updates","highlights","sections"],"additionalProperties":false,"properties":{"date":{"type":"string"},"has_updates":{"type":"boolean"},"highlights":{"type":"array","items":{"type":"string"},"maxItems":6},"sections":{"type":"array","items":{"type":"object","required":["category","icon","docs_updated","docs_new","entries"],"additionalProperties":false,"properties":{"category":{"type":"string","enum":["Claude Code CLI","Agent SDK","API Reference","Platform","Resources","About Claude","Agents & Tools","Testing & Evaluation","Release Notes","Prompt Library","Getting Started","Other"]},"icon":{"type":"string"},"docs_updated":{"type":"integer"},"docs_new":{"type":"integer"},"entries":{"type":"array","items":{"type":"object","required":["title","is_new","summary","changes","source_url"],"additionalProperties":false,"properties":{"title":{"type":"string"},"is_new":{"type":"boolean"},"summary":{"type":"string"},"changes":{"type":"array","items":{"type":"string"}},"source_url":{"type":"string"}}}}}}}}}'
```

**Key changes from current:**
- `prompt`: reads generated prompt via step output (not inline instructions)
- `--max-turns`: 10 → 3
- `--allowedTools`: `Read,Glob,Grep` → `Read` (minimal fallback; Claude shouldn't need it)
- `--json-schema`: same schema with `"additionalProperties": false` at all object levels

### Step 5b: "Save Claude output"

Add `_context` stripping as a safety net:

```yaml
- name: Save Claude output
  if: steps.detect.outputs.has_changes == 'true'
  env:
    STRUCTURED_OUTPUT: ${{ steps.claude.outputs.structured_output }}
  run: |
    python3 -c "
    import os, json
    data = json.loads(os.environ['STRUCTURED_OUTPUT'])
    for section in data.get('sections', []):
      for entry in section.get('entries', []):
        entry.pop('_context', None)
    json.dump(data, open('/tmp/claude-changelog.json', 'w'))
    print(f'Claude output: valid JSON, {len(data.get(\"sections\", []))} sections')
    "
```

### Unchanged steps

- Step 6 (Post to Slack) — no changes
- Step 7 (Archive HTML changelog) — no changes
- Step 8 (Cleanup) — no changes

---

## Schema Changes: `prompts/changelog-schema.json`

Add `"additionalProperties": false` to the entry-level object to prevent `_context` leaking:

```json
{
  "entries": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["title", "is_new", "summary", "changes", "source_url"],
      "additionalProperties": false,
      "properties": { ... }
    }
  }
}
```

Also add `"additionalProperties": false` at the section level and top level for completeness.

---

## Files Changed / Deleted

| File | Action |
|---|---|
| `scripts/build-context.py` | **New** — replaces detect-changes.sh |
| `scripts/detect-changes.sh` | **Deleted** |
| `prompts/system-prompt.md` | **Deleted** — instructions now generated inline by build-context.py |
| `prompts/changelog-schema.json` | **Modified** — add `additionalProperties: false` |
| `.github/workflows/daily-changelog.yml` | **Modified** — new detect step, simplified Claude step |
| `CLAUDE.md` | **Modified** — update step 4 to reflect new flow (no more system-prompt.md reference) |

---

## Failure Modes & Mitigations

| Failure | Mitigation |
|---|---|
| `.search_index.json` missing or malformed | Fallback: extract H1 from file for title, skip preview/keywords. Categories and URLs are derived from filenames regardless. |
| Claude still hits max-turns (3) | Very unlikely with zero tool calls; would indicate a model-level issue — retry the workflow |
| `_context` leaks into output | Belt-and-suspenders: schema blocks it + Python strips it |
| Prompt too large (100+ files changed) | Truncate diffs more aggressively (150 lines) when file count > 50; add a cap note in the prompt |

---

## Cost & Performance Estimates

| Metric | Current | New |
|---|---|---|
| Turns used | 10+ (often maxed) | 1 (3 max safety) |
| Tool calls | 20-30 | 0 |
| Cost per run (28 files) | $0.81 (today's failure) | ~$0.05-0.10 |
| Wall time (Claude step) | 8+ min (timeout) | ~30-60 seconds |
| Reliability | Fails on large days | Should handle 50+ files |
