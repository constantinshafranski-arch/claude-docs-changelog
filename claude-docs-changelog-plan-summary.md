# Proposal: Automated Daily Claude Docs Changelog → Slack

**Author:** Constantin Shafranski
**Date:** March 24, 2026
**Status:** Pending CTO Review

---

## Executive Summary

Set up an automated daily pipeline that monitors Anthropic's Claude documentation for changes, generates an AI-powered summary of what's new, and posts a formatted changelog to a dedicated Slack channel. The entire system runs on GitHub Actions — zero infrastructure to manage.

---

## Problem

Our team relies on Claude Code and the Claude API. Anthropic frequently updates their documentation (new features, SDK changes, API updates), but there's no built-in notification system. Currently, keeping up requires someone to manually check the docs — which doesn't happen consistently.

## Solution

A GitHub Actions workflow that runs daily at 08:00 IST:

1. **Pulls** the latest documentation from a community-maintained mirror
2. **Detects** which docs changed in the last 24 hours
3. **Summarizes** the changes using Claude (via Anthropic's official GitHub Action)
4. **Posts** a formatted changelog to `#claude-docs-changelog` in Slack
5. **Archives** an HTML version in the repo for reference

---

## Architecture

```
GitHub Actions (scheduled daily)
    │
    ├─→ Clone docs mirror
    ├─→ Detect changes (git diff)
    ├─→ Claude AI summarization (claude-code-action)
    ├─→ POST to Slack (incoming webhook)
    └─→ Commit HTML archive to repo
```

### Key Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Scheduling** | GitHub Actions cron | No servers to maintain, runs reliably even when laptops are off, version-controlled config |
| **AI Engine** | `anthropics/claude-code-action@v1` | Official Anthropic GitHub Action with full tooling (Read, Grep, Glob), structured JSON output |
| **Slack Delivery** | Incoming Webhook | Simplest integration — one URL, no OAuth app management, supports rich Block Kit formatting |
| **HTML Archive** | Committed to repo | Browsable via GitHub, git history = full changelog history, no hosting needed |
| **Docs Source** | `costiash/claude-code-docs` mirror | Updated multiple times daily, contains 570+ doc files covering Claude Code CLI, Agent SDK, and API |

---

## What Gets Posted to Slack

A rich, formatted message containing:

- **Stats bar**: "5 CLI docs | 3 SDK docs (1 new) | 1 Platform doc"
- **Key Highlights**: 3-6 bullet points of the most impactful changes
- **Per-category breakdown**: each updated doc with a summary and bullet-point changes
- **Source links**: direct URLs to the updated documentation

Example categories: Claude Code CLI, Agent SDK, API Reference, Platform

---

## Repository

**Location:** `constantinshafranski-arch/claude-docs-changelog`

```
claude-docs-changelog/
├── .github/workflows/daily-changelog.yml   ← Scheduled workflow
├── scripts/
│   ├── detect-changes.sh                   ← Git diff detection
│   ├── format-slack-message.py             ← JSON → Slack Block Kit
│   └── format-html-changelog.py            ← JSON → styled HTML
├── prompts/
│   ├── system-prompt.md                    ← AI summarization instructions
│   └── changelog-schema.json              ← Enforced output schema
├── changelogs/                             ← Auto-committed HTML archive
├── CLAUDE.md                               ← Instructions for the AI
└── README.md
```

---

## Security & Secrets

| Secret | Purpose | Stored In |
|--------|---------|-----------|
| `ANTHROPIC_API_KEY` | Authenticates Claude API calls | GitHub Actions Secrets (encrypted) |
| `SLACK_WEBHOOK_URL` | Posts to `#claude-docs-changelog` | GitHub Actions Secrets (encrypted) |

- No credentials in code or logs
- GitHub Actions secrets are encrypted at rest and masked in logs
- The workflow only has `contents: write` permission (to commit HTML files)

---

## Cost

| Component | Per Run | Monthly (~30 runs) |
|-----------|---------|-------------------|
| GitHub Actions (ubuntu-latest) | Free (public repo) | Free |
| Claude Sonnet API | ~$0.05–$0.15 | ~$1.50–$4.50 |
| Slack Incoming Webhook | Free | Free |
| **Total** | **~$0.10** | **~$3.00** |

A per-run budget cap of $0.50 prevents any single run from exceeding expectations.

---

## Setup Required (One-Time)

### Slack (~5 minutes)
1. Create a Slack app in the `paymeng` workspace
2. Enable Incoming Webhooks
3. Create `#claude-docs-changelog` channel
4. Add webhook to channel, copy URL

### GitHub (~5 minutes)
1. Create the repository
2. Add `ANTHROPIC_API_KEY` and `SLACK_WEBHOOK_URL` as repository secrets
3. Push the code — the workflow starts running on the next scheduled time

**Total setup time: ~10 minutes** (after code is written)

---

## Reliability & Error Handling

| Scenario | Behavior |
|----------|----------|
| No docs changed today | Workflow exits early — no Slack post, no noise |
| Claude API is down | Step fails, GitHub sends email notification |
| Slack webhook expires | curl fails, step fails, email notification |
| Very large changeset | Diffs auto-truncated to 200 lines per file |
| Workflow hangs | 15-minute timeout kills the job |

GitHub Actions automatically sends email notifications on workflow failures.

---

## Timezone Handling

Israel observes IST (UTC+2) in winter and IDT (UTC+3) in summer:
- **Summer (most of the year):** cron at 05:00 UTC = 08:00 IDT ✓
- **Winter:** same cron = 07:00 IST (one hour early)

Acceptable trade-off. To always hit 08:00, the cron would need manual adjustment twice yearly.

---

## Future Enhancements (Not in Initial Scope)

- **Slack threading**: summary as main message, details as thread replies
- **Weekly digest**: configurable lookback for weekly summaries
- **On-demand skill**: `/changelog` command in Claude Code for ad-hoc generation
- **Multi-channel**: post different categories to different Slack channels
- **PR notifications**: also post when Anthropic ships new SDK releases

---

## Decision Points for CTO Review

1. **Public vs Private repo?** Public = free GitHub Actions minutes. Private = $0.008/min but keeps the setup internal.
2. **Anthropic API key**: use an existing team key or create a dedicated one for this automation?
3. **Slack channel**: create `#claude-docs-changelog` or use an existing channel?
4. **Approve the ~$3/month Claude API cost?**

---

## Next Steps

1. CTO approves the approach
2. Create Slack app + webhook (~5 min)
3. Create GitHub repo + secrets (~5 min)
4. Implement and push the code (~1-2 hours)
5. Test with manual `workflow_dispatch` trigger
6. Verify Slack output, switch to production channel
7. Done — runs autonomously from here
