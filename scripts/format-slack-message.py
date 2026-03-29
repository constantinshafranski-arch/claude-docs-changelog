#!/usr/bin/env python3
"""
Reads Claude's JSON changelog from stdin, outputs Slack Block Kit payload to stdout.
Handles edge cases: malformed JSON, no updates, oversized blocks.

Slack limits: 3000 chars per text block, 50 blocks per message.
"""

import json
import sys
from datetime import datetime, timezone


def sanitize_url(url: str) -> str:
    """Only allow http/https URLs."""
    if url and (url.startswith("https://") or url.startswith("http://")):
        return url
    return ""


def format_date(date_str: str) -> str:
    """Format date string for display."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%b %d, %Y")
    except ValueError:
        return date_str


def html_to_mrkdwn(text: str) -> str:
    """Convert HTML formatting in changelog entries to Slack mrkdwn."""
    text = text.replace("<strong>", "*").replace("</strong>", "*")
    text = text.replace("<code>", "`").replace("</code>", "`")
    text = text.replace("&mdash;", "—")
    text = text.replace("&ndash;", "–")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&")  # Must be last to avoid double-decoding
    return text


def truncate_text(text: str, limit: int = 2900) -> str:
    """Truncate text to stay within Slack's block limit."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…_truncated_"


def build_error_payload(error_msg: str) -> dict:
    """Build a Slack message for error cases."""
    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ Claude Docs Changelog — Error",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Failed to generate changelog:\n```{error_msg[:500]}```",
                },
            },
        ]
    }


def build_no_updates_payload(date_str: str) -> dict:
    """Build a Slack message when there are no updates."""
    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📰 Claude Docs Changelog — {format_date(date_str)}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No documentation changes detected today. :white_check_mark:",
                },
            },
        ]
    }


# Map by category name — more reliable than matching Unicode emoji characters
SLACK_ICON_MAP = {
    "Claude Code CLI": ":terminal:",
    "Agent SDK": ":gear:",
    "API Reference": ":zap:",
    "Platform": ":diamond_shape_with_a_dot_inside:",
    "Resources": ":books:",
    "About Claude": ":information_source:",
    "Agents & Tools": ":wrench:",
    "Testing & Evaluation": ":test_tube:",
    "Release Notes": ":clipboard:",
    "Prompt Library": ":pencil2:",
    "Getting Started": ":rocket:",
    "Other": ":page_facing_up:",
}


def get_slack_icon(category: str) -> str:
    """Get Slack emoji code for a category name."""
    return SLACK_ICON_MAP.get(category, ":page_facing_up:")


def build_stats_bar(sections: list) -> str:
    """Build the stats summary line."""
    parts = []
    for section in sections:
        cat = section.get("category", "Unknown")
        total = section.get("docs_updated", 0) + section.get("docs_new", 0)
        new_count = section.get("docs_new", 0)
        icon = get_slack_icon(cat)
        label = f"{icon} {total} {cat}"
        if new_count > 0:
            label += f" ({new_count} new)"
        parts.append(label)
    return " │ ".join(parts)


def build_highlights_block(highlights: list) -> str:
    """Format key highlights as mrkdwn bullet list."""
    lines = []
    for h in highlights[:6]:
        lines.append(f"• {html_to_mrkdwn(h)}")
    return "\n".join(lines)


def build_section_blocks(section: dict) -> list:
    """Build Slack blocks for one category section."""
    blocks = []
    cat = section.get("category", "Unknown")
    icon = get_slack_icon(cat)
    docs_updated = section.get("docs_updated", 0)
    docs_new = section.get("docs_new", 0)

    count_parts = []
    if docs_updated > 0:
        count_parts.append(f"{docs_updated} updated")
    if docs_new > 0:
        count_parts.append(f"{docs_new} new")
    count_str = " + ".join(count_parts) if count_parts else "0 docs"

    # Category header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{icon} {cat} — {count_str}",
            "emoji": True,
        },
    })

    # Entries
    for entry in section.get("entries", []):
        title = entry.get("title", "Untitled")
        is_new = entry.get("is_new", False)
        summary = entry.get("summary", "")
        changes = entry.get("changes", [])
        source_url = entry.get("source_url", "")

        tag = "🆕 *NEW*" if is_new else "📝 _Updated_"
        lines = [f"*{title}*  {tag}"]
        if summary:
            lines.append(f"_{html_to_mrkdwn(summary)}_")
        if changes:
            lines.append("")  # blank line before bullets
        for change in changes[:8]:
            lines.append(f"  • {html_to_mrkdwn(change)}")
        if len(changes) > 8:
            lines.append(f"  _…and {len(changes) - 8} more_")
        source_url = sanitize_url(source_url)
        if source_url:
            lines.append(f"\n<{source_url}|View docs →>")

        text = "\n".join(lines)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": truncate_text(text),
            },
        })

    return blocks


def build_changelog_payload(data: dict) -> dict:
    """Build the full Slack Block Kit payload from changelog JSON."""
    date_str = data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    highlights = data.get("highlights", [])
    sections = data.get("sections", [])

    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"📰 Claude Docs Changelog — {format_date(date_str)}",
            "emoji": True,
        },
    })

    # Stats bar
    stats = build_stats_bar(sections)
    if stats:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": stats},
        })

    blocks.append({"type": "divider"})

    # Key Highlights
    if highlights:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔑 Key Highlights*\n{build_highlights_block(highlights)}",
            },
        })
        blocks.append({"type": "divider"})

    # Per-category sections (with dividers between them)
    for i, section in enumerate(sections):
        if i > 0:
            blocks.append({"type": "divider"})
        section_blocks = build_section_blocks(section)
        blocks.extend(section_blocks)

    # Footer
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"Generated from <https://github.com/costiash/claude-code-docs|claude-code-docs> "
                    f"• {sum(s.get('docs_updated', 0) + s.get('docs_new', 0) for s in sections)} docs analyzed "
                    f"• {date_str} "
                    f"• <https://github.com/constantinshafranski-arch/claude-docs-changelog/blob/main/changelogs/{date_str}.html|:page_facing_up: Full HTML report>"
                ),
            }
        ],
    })

    # Enforce Slack's 50-block limit
    if len(blocks) > 50:
        blocks = blocks[:49]
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "…_message truncated — see HTML archive for full changelog_",
                }
            ],
        })

    return {"blocks": blocks}


def main():
    raw = sys.stdin.read().strip()

    if not raw:
        json.dump(build_error_payload("Empty input — no Claude output received"), sys.stdout)
        return

    # Claude sometimes wraps output in markdown fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [line for line in lines if not line.startswith("```")]
        raw = "\n".join(lines)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        json.dump(build_error_payload(f"Invalid JSON from Claude: {e}"), sys.stdout)
        return

    if not data.get("has_updates", False):
        json.dump(build_no_updates_payload(data.get("date", "")), sys.stdout)
        return

    payload = build_changelog_payload(data)
    json.dump(payload, sys.stdout)


if __name__ == "__main__":
    main()
