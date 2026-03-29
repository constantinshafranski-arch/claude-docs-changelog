#!/usr/bin/env python3
"""
Reads Claude's JSON changelog from stdin, outputs Slack Block Kit payload to stdout.
Uses attachments for card-like category sections with colored left borders.

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


# Map category name -> Slack emoji
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

# Map category name -> card border color (Obsidian & Amber palette)
SLACK_COLOR_MAP = {
    "Claude Code CLI": "#60A0E0",       # blue
    "Agent SDK": "#C080E0",             # purple
    "API Reference": "#F0A050",         # amber
    "Platform": "#F0A050",              # amber
    "Resources": "#50C8A0",             # green
    "About Claude": "#60A0E0",          # blue
    "Agents & Tools": "#F0A050",        # amber
    "Testing & Evaluation": "#50C8A0",  # green
    "Release Notes": "#C080E0",         # purple
    "Prompt Library": "#F0A050",        # amber
    "Getting Started": "#50C8A0",       # green
    "Other": "#60A0E0",                 # blue
}


def get_slack_icon(category: str) -> str:
    return SLACK_ICON_MAP.get(category, ":page_facing_up:")


def get_slack_color(category: str) -> str:
    return SLACK_COLOR_MAP.get(category, "#60A0E0")


def build_stats_bar(sections: list) -> str:
    """Build the stats summary line."""
    parts = []
    for section in sections:
        cat = section.get("category", "Unknown")
        total = section.get("docs_updated", 0) + section.get("docs_new", 0)
        new_count = section.get("docs_new", 0)
        icon = get_slack_icon(cat)
        label = f"{icon} *{total}* {cat}"
        if new_count > 0:
            label += f" ({new_count} new)"
        parts.append(label)
    return "  │  ".join(parts)


def build_highlights_block(highlights: list) -> str:
    """Format key highlights as mrkdwn."""
    lines = []
    for h in highlights[:6]:
        lines.append(f"  •  {html_to_mrkdwn(h)}")
    return "\n".join(lines)


def build_entry_text(entry: dict) -> str:
    """Build mrkdwn text for a single doc entry."""
    title = entry.get("title", "Untitled")
    is_new = entry.get("is_new", False)
    summary = entry.get("summary", "")
    changes = entry.get("changes", [])

    tag = ":new:  *NEW*" if is_new else ":pencil:  _Updated_"
    lines = [f"*{title}*  {tag}"]

    if summary:
        lines.append(html_to_mrkdwn(summary))

    for change in changes[:8]:
        lines.append(f"    •  {html_to_mrkdwn(change)}")
    if len(changes) > 8:
        lines.append(f"    _…and {len(changes) - 8} more_")

    source_url = sanitize_url(entry.get("source_url", ""))
    if source_url:
        lines.append(f":link:  <{source_url}|View docs →>")

    return "\n".join(lines)


def build_category_attachment(section: dict) -> dict:
    """Build a Slack attachment (colored card) for one category."""
    cat = section.get("category", "Unknown")
    icon = get_slack_icon(cat)
    color = get_slack_color(cat)
    docs_updated = section.get("docs_updated", 0)
    docs_new = section.get("docs_new", 0)

    count_parts = []
    if docs_updated > 0:
        count_parts.append(f"{docs_updated} updated")
    if docs_new > 0:
        count_parts.append(f"{docs_new} new")
    count_str = " + ".join(count_parts) if count_parts else "0 docs"

    blocks = []

    # Category header inside the card
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{icon}  *{cat}*  —  {count_str}",
        },
    })

    # Each entry as its own section block
    for entry in section.get("entries", []):
        text = build_entry_text(entry)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": truncate_text(text),
            },
        })

    return {
        "color": color,
        "blocks": blocks,
    }


def build_changelog_payload(data: dict) -> dict:
    """Build the full Slack payload with top-level blocks + colored attachments."""
    date_str = data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    highlights = data.get("highlights", [])
    sections = data.get("sections", [])

    total_docs = sum(
        s.get("docs_updated", 0) + s.get("docs_new", 0) for s in sections
    )

    # Top-level blocks: header, stats, highlights
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"📰  Claude Docs Changelog  —  {format_date(date_str)}",
            "emoji": True,
        },
    })

    # Stats bar (context = smaller, muted)
    stats = build_stats_bar(sections)
    if stats:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": stats}],
        })

    # Key Highlights
    if highlights:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":sparkles:  *Key Highlights*\n\n{build_highlights_block(highlights)}",
            },
        })

    # Footer
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"Generated from <https://github.com/costiash/claude-code-docs|claude-code-docs> "
                    f"  •  {total_docs} docs analyzed  •  {date_str}  •  "
                    f"<https://github.com/constantinshafranski-arch/claude-docs-changelog/blob/main/changelogs/{date_str}.html|:page_facing_up: Full HTML report>"
                ),
            }
        ],
    })

    # Colored card attachments — one per category
    attachments = []
    for section in sections:
        attachments.append(build_category_attachment(section))

    return {"blocks": blocks, "attachments": attachments}


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
