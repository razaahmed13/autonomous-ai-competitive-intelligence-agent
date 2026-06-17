# Autonomous AI Competitive Intelligence Agent

An AI-powered competitive intelligence system for Neodym that discovers, analyzes, prioritizes, and summarizes important developments in artificial intelligence.

## Objective

Build a recurring intelligence workflow that helps a founder, engineer, or product team quickly understand:

- What happened
- Why it matters
- What action should be considered

The goal is **not** to aggregate news. The goal is to identify what matters, explain why it matters, and provide actionable intelligence.

## Core Requirements Understood

### Data collection

Collect AI-related updates from multiple independent sources, such as company blogs, research feeds, RSS feeds, public APIs, and public websites.

### Deduplication

Detect duplicate or near-duplicate stories and merge them into one intelligence item while preserving all source references.

### Categorization

Assign each item to categories such as:

- Model Release
- Research
- Startup Activity
- Competitor Update
- Infrastructure
- Regulation
- Other

### Analysis per item

Each selected intelligence item must include:

- Title
- Category
- Importance Score (1-10)
- Score Reason
- Summary
- Why It Matters
- Source Links

Items without source links must not appear in the final report.

### Ranking

Rank items from highest to lowest importance with an explainable methodology.

### AI usage

Use LLMs for meaningful workflow steps such as summarization, classification, deduplication, ranking, and recommendation generation. Simple API wrapping is not sufficient.

### Outputs

Generate:

- `daily_brief.json` — machine-readable structured report
- `daily_brief.md` — Slack-formatted report for `#industry-trends`

If Slack credentials are unavailable, the system should still generate Slack-ready markdown and document Slack delivery configuration.

### Historical storage

Store processed items to avoid repeatedly surfacing the same developments across daily runs unless meaningful new information appears.

### Evaluation suite

Include lightweight evals for:

- Deduplication
- Categorization
- Ranking
- Output schema validation
- Source grounding

Expected command: `python run_evals.py` or a clearly documented equivalent.

## Deliverables Checklist

- [ ] Source code in GitHub repository
- [ ] Local run instructions
- [ ] Generated `daily_brief.json`
- [ ] Generated `daily_brief.md`
- [ ] README with setup, architecture, technical decisions, data sources, AI usage, scoring methodology, limitations, future improvements, and Slack delivery instructions
- [ ] Agent usage log covering AI tools used, verification, problems, and lessons learned
- [ ] 5-10 minute demo material covering architecture, features, AI workflow, generated report, Slack output, eval results, and future improvements

## Current Phase A Usage

Install dependencies and run tests:

```bash
uv sync
uv run pytest
```

Collect raw source items into SQLite:

```bash
uv run python run.py collect
```

Generate intelligence reports with the approved Codex CLI stack. Codex CLI should already be installed and authenticated on the machine:

```bash
AI_MODEL=codex-cli uv run python run.py brief
```

`AI_API_KEY` and `AI_BASE_URL` may remain in local variable files for compatibility, but the workflow does not use them for LLM calls.

For a small test run on only the latest raw items fetched in the last 24 hours:

```bash
AI_MODEL=codex-cli uv run python run.py brief --raw-items 5 --force \
  --json-output /tmp/test_daily_brief.json \
  --markdown-output /tmp/test_daily_brief.md
```

For local smoke testing without live LLM credentials, use the deterministic offline demo client:

```bash
AI_MODEL=offline-demo uv run python run.py brief --max-items 5
```

By default, the brief command stores reported intelligence fingerprints in SQLite and skips them on later runs. To intentionally regenerate a brief from already-reported candidate events, use:

```bash
AI_MODEL=offline-demo uv run python run.py brief --max-items 5 --force
```

The Phase E pipeline writes:

- `daily_brief.json`
- `daily_brief.md`

## Source Expansion and Freshness Policy

The default source registry contains 25 AI/ML sources across model labs, agent tooling, research, and market intelligence.

During collection, the agent applies this freshness policy before inserting raw items into SQLite:

- If `published_at` exists, items older than 24 hours are skipped.
- If `published_at` is missing, items are kept.
- Daily brief generation still uses `fetched_at` from the last 24 hours.

This keeps expanded collection from backfilling old articles while preserving sources that do not expose reliable publish dates.

## Slack Delivery

The system always generates `daily_brief.md`, which is ready to paste into Slack. Automatic Slack delivery is optional and controlled by environment variables so credentials are never hardcoded.

To send the generated report to Slack:

1. Create or use a Slack app with a bot token.
2. Grant the bot the `chat:write` scope.
3. Invite the bot to the target channel, preferably `#industry-trends`.
4. Configure environment variables:

```bash
export SLACK_BOT_TOKEN=<your-slack-bot-token>
export SLACK_CHANNEL=#industry-trends
```

5. Generate and send in one command:

```bash
uv run python run.py brief --send-slack
```

To send an already-generated `daily_brief.md` without rerunning collection or LLM analysis, run:

```bash
uv run python run.py send-slack
```

You can choose a specific Markdown file or channel:

```bash
uv run python run.py send-slack --markdown-output daily_brief.md --slack-channel '#industry-trends'
```

You can also enable delivery by default:

```bash
SLACK_ENABLED=true uv run python run.py brief
```

If Slack credentials are missing, report generation still succeeds and the CLI prints a clear skip message. If Slack returns `channel_not_found`, invite the bot to the channel or use the Slack channel ID instead of the channel name.

The current implementation supports:

- Environment-driven config via `.env` / `.env.example`
- Pydantic models for sources, raw items, deduplicated events, intelligence items, and daily briefs
- SQLite tables for raw items, intelligence items, and source-item links
- Default AI source definitions with 25 sources
- RSS fetching and parsing
- Collection freshness filtering using `published_at` when available
- Deterministic deduplication
- Codex CLI LLM client and offline demo client
- LLM-only categorization prompt
- Source-grounded analysis prompt
- Importance ranking
- Historical tracking for reported intelligence fingerprints
- `--raw-items` brief test runs over the latest N raw items fetched inside the lookback window
- `--force` regeneration for already-reported candidate events
- JSON and Slack-ready Markdown report generation
- Optional Slack `chat.postMessage` delivery via env vars / `--send-slack`
- `send-slack` command for posting an existing `daily_brief.md` without rerunning the workflow
- Basic collection pipeline orchestration

The default local database path is:

```text
data/intelligence.db
```

## Project Statement

The original attached project statement is preserved at:

- [`docs/Autonomous AI Competitive Intelligence Agent.docx`](docs/Autonomous%20AI%20Competitive%20Intelligence%20Agent.docx)
- [`docs/project-statement.md`](docs/project-statement.md)
