# Claude Docs Changelog Generator

You are generating a structured JSON changelog of Anthropic/Claude documentation updates.

## Your Task
1. Read `CONTEXT.md` — it lists changed doc files with categories and diff excerpts
2. For each changed file, read the FULL file from `docs-mirror/docs/` (not just the diff)
3. Read the schema from `prompts/changelog-schema.json`
4. Read the detailed instructions from `prompts/system-prompt.md` — it is the **single source of truth** for category mapping, URL derivation, and writing guidelines
5. Produce a JSON object matching the schema

## Quick Reference
- Summarize what CHANGED, not what the doc contains
- Highlights: 3-6 max, most impactful changes
- Each bullet: start with `<strong>bolded keyword</strong>` &mdash; description
- New docs (`is_new: true`) get a richer summary since everything is new
- Output ONLY valid JSON, no markdown fences
