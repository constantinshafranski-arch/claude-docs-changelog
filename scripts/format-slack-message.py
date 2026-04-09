#!/usr/bin/env python3
"""
Reads Claude's JSON changelog from stdin, outputs Slack Block Kit payload to stdout.
Clean, readable layout using blocks only (no attachments).

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
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%b %d, %Y")
    except ValueError:
        return date_str


def html_to_mrkdwn(text: str) -> str:
    """Convert HTML formatting to Slack mrkdwn."""
    text = text.replace("<strong>", "*").replace("</strong>", "*")
    text = text.replace("<code>", "`").replace("</code>", "`")
    text = text.replace("&mdash;", "—")
    text = text.replace("&ndash;", "–")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&")
    return text


def truncate_text(text: str, limit: int = 2900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…_truncated_"


def build_error_payload(error_msg: str) -> dict:
    return {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": ":warning:  Claude Docs Changelog — Error", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"Failed to generate changelog:\n```{error_msg[:500]}```"}},
        ]
    }


def build_no_updates_payload(date_str: str) -> dict:
    return {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f":newspaper:  Claude Docs Changelog — {format_date(date_str)}", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": ":white_check_mark:  No documentation changes detected today."}},
        ]
    }


# Category -> (Slack emoji, short label)
CATEGORY_META = {
    "Claude Code CLI":      (":computer:", "CLI"),
    "Agent SDK":            (":gear:", "SDK"),
    "API Reference":        (":zap:", "API"),
    "Managed Agents":       (":robot_face:", "Agents"),
    "Platform":             (":large_blue_diamond:", "Platform"),
    "Resources":            (":books:", "Resources"),
    "About Claude":         (":bulb:", "About"),
    "Agents & Tools":       (":hammer_and_wrench:", "Tools"),
    "Testing & Evaluation": (":test_tube:", "Testing"),
    "Release Notes":        (":memo:", "Releases"),
    "Prompt Library":       (":pencil2:", "Prompts"),
    "Getting Started":      (":rocket:", "Start"),
    "Other":                (":page_facing_up:", "Other"),
}

# GitHub Pages base URL for rendered HTML changelogs
PAGES_BASE = "https://constantinshafranski-arch.github.io/claude-docs-changelog/changelogs"


def get_icon(category: str) -> str:
    return CATEGORY_META.get(category, (":page_facing_up:", "Other"))[0]


def build_changelog_payload(data: dict) -> dict:
    date_str = data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    highlights = data.get("highlights", [])
    sections = data.get("sections", [])

    total_docs = sum(s.get("docs_updated", 0) + s.get("docs_new", 0) for s in sections)

    blocks = []

    # ── Header ──
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f":newspaper:  Claude Docs Changelog  —  {format_date(date_str)}", "emoji": True},
    })

    # ── Stats bar ──
    stats_parts = []
    for s in sections:
        cat = s.get("category", "Unknown")
        icon = get_icon(cat)
        total = s.get("docs_updated", 0) + s.get("docs_new", 0)
        new_count = s.get("docs_new", 0)
        part = f"{icon} *{total}* {cat}"
        if new_count > 0:
            part += f" ({new_count} new)"
        stats_parts.append(part)
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "   ".join(stats_parts)}],
    })

    # ── Highlights ──
    if highlights:
        blocks.append({"type": "divider"})
        lines = [f":sparkles:  *Key Highlights*", ""]
        for h in highlights[:6]:
            lines.append(f">  {html_to_mrkdwn(h)}")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        })

    # ── Category sections ──
    for section in sections:
        cat = section.get("category", "Unknown")
        icon = get_icon(cat)
        docs_updated = section.get("docs_updated", 0)
        docs_new = section.get("docs_new", 0)

        count_parts = []
        if docs_updated > 0:
            count_parts.append(f"{docs_updated} updated")
        if docs_new > 0:
            count_parts.append(f"{docs_new} new")
        count_str = ", ".join(count_parts) if count_parts else "0 docs"

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": f"{icon}  {cat}  —  {count_str}", "emoji": True},
        })

        # Each entry
        for entry in section.get("entries", []):
            title = entry.get("title", "Untitled")
            is_new = entry.get("is_new", False)
            summary = entry.get("summary", "")
            changes = entry.get("changes", [])
            source_url = sanitize_url(entry.get("source_url", ""))

            tag = ":new:" if is_new else ":pencil:"
            lines = [f"{tag}  *{title}*"]

            if summary:
                lines.append(html_to_mrkdwn(summary))

            if changes:
                lines.append("")
                for change in changes[:8]:
                    lines.append(f"    •  {html_to_mrkdwn(change)}")
                if len(changes) > 8:
                    lines.append(f"    _…and {len(changes) - 8} more_")

            if source_url:
                lines.append(f"\n:link:  <{source_url}|View docs →>")

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": truncate_text("\n".join(lines))},
            })

    # ── Footer ──
    html_url = f"{PAGES_BASE}/{date_str}.html"
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f":page_facing_up: *<{html_url}|View Full HTML Report>*"},
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Open Report", "emoji": True},
            "url": html_url,
            "action_id": "open_report",
        },
    })
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": (
                f"Generated from <https://github.com/costiash/claude-code-docs|claude-code-docs>"
                f"  •  {total_docs} docs analyzed"
            ),
        }],
    })

    # Enforce 50-block limit
    if len(blocks) > 50:
        html_url = f"{PAGES_BASE}/{date_str}.html"
        blocks = blocks[:48]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"_…truncated_ — *<{html_url}|View Full HTML Report>*"},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Open Report", "emoji": True},
                "url": html_url,
                "action_id": "open_report_truncated",
            },
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Generated from <https://github.com/costiash/claude-code-docs|claude-code-docs>  •  {total_docs} docs analyzed"}],
        })

    return {"blocks": blocks}


def main():
    raw = sys.stdin.read().strip()

    if not raw:
        json.dump(build_error_payload("Empty input — no Claude output received"), sys.stdout)
        return

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
