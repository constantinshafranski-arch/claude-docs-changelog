# Claude Docs Changelog

Automated daily changelog of Anthropic's Claude documentation updates, delivered to Slack.

A GitHub Actions workflow runs daily at **08:00 IST**, detects documentation changes from the community-maintained [claude-code-docs](https://github.com/costiash/claude-code-docs) mirror, uses Claude to generate structured summaries, posts them to Slack, and archives styled HTML changelogs in this repo.

## How It Works

```
GitHub Actions (daily cron)
    │
    ├─→ Clone costiash/claude-code-docs
    ├─→ build-context.py pre-computes scaffold (categories, URLs, titles, diffs)
    ├─→ Claude fills in summaries + highlights (1 turn, 0 tool calls)
    ├─→ Format JSON → Slack Block Kit → POST webhook
    └─→ Format JSON → HTML → commit to changelogs/
```

## Repository Structure

```
├── .github/workflows/daily-changelog.yml   ← Scheduled workflow
├── scripts/
│   ├── build-context.py                    ← Pre-computes scaffold from mirror data
│   ├── format-slack-message.py             ← JSON → Slack Block Kit payload
│   └── format-html-changelog.py            ← JSON → styled HTML archive
├── prompts/
│   └── changelog-schema.json              ← Enforced output schema
├── changelogs/                             ← Auto-committed HTML archive
├── CLAUDE.md                               ← Instructions for claude-code-action
└── README.md
```

## Setup

### Prerequisites

- A GitHub account with access to create repositories
- An [Anthropic API key](https://console.anthropic.com/)
- A Slack workspace with permission to create apps

### 1. Slack Incoming Webhook (~5 min)

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. App name: `Claude Docs Changelog`, Workspace: your workspace
3. Go to **Incoming Webhooks** → toggle **On**
4. Click **Add New Webhook to Workspace**
5. Select the `#claude-docs-changelog` channel
6. Copy the webhook URL

### 2. Repository Secrets

Add these in **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SLACK_WEBHOOK_URL` | The webhook URL from step 1 |

### 3. Test

Trigger a manual run: **Actions → Daily Claude Docs Changelog → Run workflow**

Use the `lookback` input to set a wider window (e.g., `72 hours ago`) to guarantee changes are found.

## Changelog Archive

HTML changelogs are auto-committed to `changelogs/YYYY-MM-DD.html` — browsable directly on GitHub or locally.

## Cost

~$3/month (Claude Haiku API). GitHub Actions minutes are free for public repos.

## Timezone

Cron runs at 05:00 UTC = 08:00 IDT (summer) / 07:00 IST (winter). Accepts ±1h seasonal drift.

## License

MIT
