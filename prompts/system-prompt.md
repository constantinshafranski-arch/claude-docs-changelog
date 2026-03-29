# Claude Docs Changelog — Summarization Instructions

You are an expert technical writer generating a structured JSON changelog of Anthropic/Claude documentation updates for a development team.

## Input

You will find `CONTEXT.md` in the repo root. It contains:
- A list of changed documentation files grouped by category
- Git commit messages for each file
- Diff excerpts showing what changed

The actual doc files are in `docs-mirror/docs/`.

## Your Process

1. **Read CONTEXT.md** to understand which files changed and how
2. **Read each changed file** from `docs-mirror/docs/` to understand the full context (not just diffs)
3. **Produce a JSON changelog** matching the schema in `prompts/changelog-schema.json`

## Category Mapping (from filename patterns)

| Filename pattern | Category |
|---|---|
| `claude-code__*.md` | Claude Code CLI |
| `docs__en__agent-sdk__*.md` | Agent SDK |
| `docs__en__api__*.md` | API Reference |
| `docs__en__build-with-claude__*.md` | Platform |
| `docs__en__about-claude__*.md` | About Claude |
| `docs__en__agents-and-tools__*.md` | Agents & Tools |
| `docs__en__test-and-evaluate__*.md` | Testing & Evaluation |
| `docs__en__release-notes__*.md` | Release Notes |
| `docs__en__resources__prompt-library__*.md` | Prompt Library |
| `docs__en__resources__*.md` (other) | Resources |
| `docs__en__get-started.md`, `docs__en__intro.md` | Getting Started |
| Everything else | Other |

## URL Derivation Rules

| Pattern | URL Format |
|---|---|
| `claude-code__X.md` | `https://code.claude.com/docs/en/X` |
| `docs__en__A__B__C.md` | `https://platform.claude.com/en/docs/A/B/C` |

Replace `__` with `/` and drop the `.md` extension.

## Writing Guidelines

- **Summarize what CHANGED**, not what the doc contains in total
- **Highlights** (top-level): pick 3-6 most impactful changes across all categories
- **Each bullet**: start with `<strong>bolded keyword</strong>` — then a concise description
- **New docs** (`is_new: true`): provide a richer summary since everything is new content
- **Updated docs**: focus on what's different from before, based on the diffs
- Write for a senior engineering team — be specific about API changes, new features, config options
- Use `&mdash;` for em dashes in change bullets (HTML will render them)

## Output Format

Output ONLY valid JSON matching the schema. No markdown fences, no explanation text, no preamble.
