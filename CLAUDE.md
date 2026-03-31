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
- New docs (`is_new: true`) get a richer summary since everything is new
- Output ONLY valid JSON, no markdown fences
