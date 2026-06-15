# Autonomous AI Competitive Intelligence Agent

An AI-powered competitive intelligence system for Neodym that discovers, analyzes, prioritizes, and summarizes important developments in artificial intelligence.

## Objective

Build a recurring intelligence workflow that helps a founder, engineer, or product team quickly understand:

- What happened
- Why it matters
- Why it matters to Neodym
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
- Why It Matters to Neodym
- Recommended Action
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

Generate intelligence reports with live LLM credentials:

```bash
AI_API_KEY=... AI_MODEL=... uv run python run.py brief
```

For local smoke testing without live LLM credentials, use the deterministic offline demo client:

```bash
AI_MODEL=offline-demo uv run python run.py brief --max-items 5
```

By default, the brief command stores reported intelligence fingerprints in SQLite and skips them on later runs. To intentionally regenerate a brief from already-reported candidate events, use:

```bash
AI_MODEL=offline-demo uv run python run.py brief --max-items 5 --force
```

The Phase C pipeline writes:

- `daily_brief.json`
- `daily_brief.md`

The current implementation supports:

- Environment-driven config via `.env` / `.env.example`
- Pydantic models for sources, raw items, deduplicated events, intelligence items, and daily briefs
- SQLite tables for raw items, intelligence items, and source-item links
- Default AI source definitions
- RSS fetching and parsing
- Deterministic deduplication
- OpenAI-compatible LLM client and offline demo client
- LLM-only categorization prompt
- Source-grounded analysis prompt
- Importance ranking
- Historical tracking for reported intelligence fingerprints
- `--force` regeneration for already-reported candidate events
- JSON and Slack-ready Markdown report generation
- Basic collection pipeline orchestration

The default local database path is:

```text
data/intelligence.db
```

## Project Statement

The original attached project statement is preserved at:

- [`docs/Autonomous AI Competitive Intelligence Agent.docx`](docs/Autonomous%20AI%20Competitive%20Intelligence%20Agent.docx)
- [`docs/project-statement.md`](docs/project-statement.md)
