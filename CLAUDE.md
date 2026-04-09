# Claude Docs Changelog Generator

You are completing a pre-built changelog scaffold. All deterministic fields (categories, URLs, titles, icons, counts) are already filled in. You only need to write the creative fields.

## Your Task
1. Read the scaffold JSON in the prompt — it has `_context` per entry with diffs, previews, and keywords
2. For each entry, fill in `summary` (one sentence) and `changes` (bullet array)
3. Write the top-level `highlights` array (3-6 most impactful changes)
4. Output the completed JSON without `_context` fields

## Quick Reference
- Summarize what CHANGED, not what the doc contains
- Highlights: 3-6 max, most impactful changes
- Each bullet: start with `<strong>bolded keyword</strong>` &mdash; description
- Use `<code>tag</code>` for inline code references in summaries and bullets
- New docs (`is_new: true`) get a richer summary since everything is new
- For grouped SDK entries (title ending with "N SDKs"), summarize the endpoint once and note which SDKs are covered
- Output ONLY valid JSON, no markdown fences

## Architecture
- **Model**: Claude Sonnet 4.6 via direct API (forced tool_use for structured output)
- **Chunking**: Prompts exceeding 2M chars (~667K tokens) are split into chunks, each called separately, then merged by category
- **Titles**: Deterministic — from search index, markdown headings, or endpoint path parsing (never from content guessing)
- **Validation**: API responses validated per-chunk; section counts recalculated after merge; malformed entries logged and skipped
