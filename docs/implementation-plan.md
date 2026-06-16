# Implementation Plan: Autonomous AI Competitive Intelligence Agent

Date: 2026-06-15
Project directory: `/home/ahmedraza/projects/autonomous-ai-competitive-intelligence-agent`
Repository: `https://github.com/razaahmed13/autonomous-ai-competitive-intelligence-agent`

---

## 1. Product Goal

Build a daily AI competitive intelligence system for Neodym that:

1. Collects AI-related updates from multiple independent sources.
2. Deduplicates overlapping stories into single intelligence items.
3. Uses LLMs meaningfully for deduplication assistance, classification, summarization, ranking, scoring, and recommendation generation.
4. Produces a high-signal daily brief that explains:
   - What happened
   - Why it matters
   - What action should be considered
5. Generates:
   - `daily_brief.json`
   - `daily_brief.md`
6. Stores historical processed items to avoid duplicate reporting across runs.
7. Includes a lightweight evaluation suite.
8. Is easy to run locally and demo within 5–10 minutes.

Guiding principle:

> Fewer but better intelligence items. Prioritize signal, relevance, grounding, and actionability over volume.

---

## 2. Key Project Requirements from Statement

### Data Collection

Collect information from multiple independent AI-related sources, such as:

- Company blogs
- Research feeds
- RSS feeds
- Public APIs
- Public websites

The system should demonstrate meaningful coverage without trying to maximize raw article count.

### Deduplication

The system must identify duplicate or near-duplicate stories and merge them into one intelligence item while preserving all source references.

Example:

- If several sources discuss the same model release, the system should report it as one event, not three separate articles.

### Categorization

Each item must be assigned to one category:

- Model Release
- Research
- Startup Activity
- Competitor Update
- Infrastructure
- Regulation
- Other

Important implementation decision:

> Categorization will use LLM classification only. We will not use a hybrid rule-based + LLM approach because hardcoded rules can introduce brittle or incorrect category decisions.

### Analysis

Each selected item must include:

- Title
- Category
- Importance Score, 1–10
- Score Reason
- Summary
- Why It Matters
- Source Links

Items without at least one source link must not appear in the final report.

### Ranking

Items must be ranked from highest importance to lowest importance. The ranking methodology must be explainable.

### AI Requirements

The project must use LLMs for meaningful parts of the workflow, such as:

- Summarization
- Classification
- Deduplication
- Ranking
- Recommendation generation

Simple API wrapping is not sufficient.

### Output Requirements

Generate:

- `daily_brief.json` — machine-readable report
- `daily_brief.md` — Slack-formatted intelligence report

Preferred Slack channel:

```text
#industry-trends
```

If Slack credentials are available, send the report automatically. If unavailable, generate a Slack-ready report and document how Slack delivery would be configured.

### Historical Storage

Store previously processed items so repeated daily runs do not keep resurfacing the same developments unless meaningful new information appears.

Acceptable storage:

- SQLite
- PostgreSQL
- JSON storage

Recommended: SQLite.

### Evaluation Suite

At minimum, evaluate:

- Deduplication
- Categorization
- Ranking
- Output schema validation
- Source grounding

Expected command:

```bash
python run_evals.py
```

### Deliverables

Required deliverables:

- Source code in GitHub repository
- Local run instructions
- Generated `daily_brief.json`
- Generated `daily_brief.md`
- README with setup, architecture, technical decisions, data sources, AI usage, scoring methodology, limitations, future improvements, and Slack delivery instructions
- Agent usage log
- Demo material for a 5–10 minute meeting walkthrough

---

## 3. Recommended Tech Stack

### Language and Runtime

- Python 3.11+
- `uv` for dependency management

### CLI

Use either:

- `argparse` for maximum simplicity, or
- `typer` for a cleaner CLI experience

Recommended for speed: start with `argparse` unless we want nicer commands.

### Storage

- SQLite

Reason:

- Local
- No external service setup
- Easy to inspect during demo
- Enough for historical tracking

### Data Collection

Recommended libraries:

- `feedparser` for RSS/Atom
- `httpx` for HTTP requests
- `beautifulsoup4` or `trafilatura` for page extraction if needed

### Validation

- `pydantic`

### AI Layer

Use an OpenAI-compatible client abstraction.

Recommended environment variables:

```bash
AI_API_KEY=
AI_BASE_URL=
AI_MODEL=
```

This keeps the app flexible across OpenAI, OpenRouter, or other OpenAI-compatible providers.

### Slack

Use Slack Web API directly via HTTP.

Environment variables:

```bash
SLACK_BOT_TOKEN=
SLACK_CHANNEL=#industry-trends
```

Slack delivery is optional. Missing Slack credentials should not fail report generation.

---

## 4. Proposed Project Structure

```text
autonomous-ai-competitive-intelligence-agent/
├── README.md
├── pyproject.toml
├── .env.example
├── run.py
├── run_evals.py
├── daily_brief.json
├── daily_brief.md
├── data/
│   └── intelligence.db
├── docs/
│   ├── project-statement.md
│   ├── implementation-plan.md
│   ├── agent-usage-log.md
│   └── demo-guide.md
├── src/
│   └── ci_agent/
│       ├── __init__.py
│       ├── config.py
│       ├── cli.py
│       ├── models.py
│       ├── database.py
│       ├── sources.py
│       ├── fetchers/
│       │   ├── __init__.py
│       │   ├── rss.py
│       │   ├── web.py
│       │   └── static_sources.py
│       ├── pipeline.py
│       ├── deduplication.py
│       ├── categorization.py
│       ├── ranking.py
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── prompts.py
│       │   └── schemas.py
│       ├── report/
│       │   ├── __init__.py
│       │   ├── json_report.py
│       │   ├── slack_markdown.py
│       │   └── slack_delivery.py
│       └── evals/
│           ├── __init__.py
│           ├── fixtures.py
│           ├── test_deduplication.py
│           ├── test_categorization.py
│           ├── test_ranking.py
│           ├── test_schema.py
│           └── test_source_grounding.py
└── tests/
    └── optional_pytest_tests.py
```

Keep the project CLI-first and avoid overbuilding.

---

## 5. Phase 1 — Foundation and Project Skeleton

### Goal

Create the basic app structure, configuration system, data models, and CLI command flow.

### Tasks

#### 5.1 Define Core Data Models

Create Pydantic models for raw items, deduplicated events, intelligence items, and daily brief output.

##### Raw Source Item

Fields:

```python
id: str
source_name: str
source_type: str
title: str
url: str
published_at: datetime | None
author: str | None
raw_summary: str | None
content: str | None
fetched_at: datetime
```

##### Deduplicated Event

Fields:

```python
id: str
canonical_title: str
source_items: list[RawSourceItem]
source_links: list[str]
merged_summary: str | None
content_fingerprint: str
```

##### Intelligence Item

Fields:

```python
title: str
category: Literal[
    "Model Release",
    "Research",
    "Startup Activity",
    "Competitor Update",
    "Infrastructure",
    "Regulation",
    "Other",
]
importance_score: int
score_reason: str
summary: str
why_it_matters: str
source_links: list[str]
source_names: list[str]
deduped_from_ids: list[str]
```

##### Daily Brief

Fields:

```python
date: date
generated_at: datetime
methodology: str
items: list[IntelligenceItem]
source_count: int
candidate_count: int
selected_count: int
```

### Acceptance Criteria

- Models validate required fields.
- Invalid categories are rejected.
- Importance scores outside 1–10 are rejected.
- Items without source links are rejected before final report generation.

---

## 6. Phase 2 — Configuration and CLI

### Goal

Make the app easy to configure and run locally.

### Configuration Variables

Support:

```bash
AI_API_KEY=
AI_BASE_URL=
AI_MODEL=
SLACK_BOT_TOKEN=
SLACK_CHANNEL=#industry-trends
DATABASE_PATH=data/intelligence.db
MAX_ITEMS_PER_RUN=8
```

### CLI Commands

Recommended commands:

```bash
python run.py collect
python run.py brief
python run.py send-slack
python run.py all
python run.py
```

Default `python run.py` should run the full pipeline.

### Expected CLI Output

Example:

```text
Collected 42 raw items from 8 sources.
Merged into 25 unique candidate events.
Selected 5 intelligence items.
Wrote daily_brief.json.
Wrote daily_brief.md.
Slack credentials not found; skipped delivery.
```

### Acceptance Criteria

- App runs with a clear local command.
- Missing Slack credentials do not fail the run.
- Missing AI credentials produce a clear actionable error when LLM analysis is required.

---

## 7. Phase 3 — Data Sources

### Goal

Collect AI-related updates from multiple independent sources.

### Recommended Initial Sources

Start with reliable public sources.

#### Company / Competitor Sources

1. OpenAI Blog / News
2. Anthropic News
3. Google DeepMind Blog
4. Meta AI Blog
5. Mistral AI News
6. Hugging Face Blog

#### Research Sources

7. arXiv API for:
   - `cs.AI`
   - `cs.LG`
   - `cs.CL`

#### Infrastructure / Ecosystem Sources

8. NVIDIA AI / Developer Blog
9. LangChain Blog
10. Vercel AI / AI SDK updates

### Source Strategy

Start with 6–8 reliable sources. The project should demonstrate quality and breadth, not maximum volume.

### Source Definition Model

Example:

```python
SourceConfig(
    name="Hugging Face Blog",
    type="rss",
    url="https://huggingface.co/blog/feed.xml",
)
```

### Fetcher Behavior

Each fetcher should return normalized `RawSourceItem` objects.

### Error Handling

- One broken source should not crash the whole run.
- Source failures should be logged.
- The report should include enough successful sources to remain useful.

### Acceptance Criteria

- At least 5 independent sources are collected.
- Each raw item has a title, URL, source name, and fetched timestamp.
- Failed sources are handled gracefully.

---

## 8. Phase 4 — Historical Storage

### Goal

Avoid reporting the same development repeatedly across future runs.

### Recommended SQLite Tables

#### `raw_items`

```sql
CREATE TABLE raw_items (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    published_at TEXT,
    raw_summary TEXT,
    content TEXT,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL
);
```

#### `intelligence_items`

```sql
CREATE TABLE intelligence_items (
    id TEXT PRIMARY KEY,
    canonical_title TEXT NOT NULL,
    category TEXT NOT NULL,
    importance_score INTEGER NOT NULL,
    summary TEXT NOT NULL,
    source_links_json TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    reported_at TEXT NOT NULL
);
```

#### `source_item_links`

```sql
CREATE TABLE source_item_links (
    intelligence_item_id TEXT NOT NULL,
    raw_item_id TEXT NOT NULL
);
```

### Fingerprinting Strategy

Generate fingerprints from:

- Normalized title
- Canonical URL/domain
- Key terms
- Short content hash

Initial deterministic approach:

1. Lowercase text.
2. Remove punctuation.
3. Remove common stopwords.
4. Keep significant words/entities.
5. Hash the normalized result.

### Acceptance Criteria

- Running the app twice should not produce the same report items again unless forced.
- Historical records are stored in SQLite.
- README explains how repeated-run behavior works.

---

## 9. Phase 5 — Deduplication

### Goal

Detect duplicate or near-duplicate stories and merge them into single intelligence events.

### Recommended Approach

Use a two-layer deduplication flow.

#### Layer 1: Deterministic Deduplication

Use cheap checks first:

- Exact URL match
- Canonical URL normalization
- Normalized title similarity
- Content hash similarity

This catches obvious duplicates quickly.

#### Layer 2: LLM-Assisted Event Clustering

Use the LLM to decide whether groups of candidate items refer to the same underlying event.

Example instruction:

```text
You are clustering AI industry updates into unique events.

Given these candidate source items, group items that describe the same underlying development.

Rules:
- Same model release reported by multiple outlets = one event.
- Same research paper discussed by multiple sources = one event.
- Follow-up analysis without new facts should be grouped with the original event.
- Distinct releases from the same company should remain separate.
- Preserve all source links.

Return JSON only.
```

### Output

Produce deduplicated event candidates:

```python
DedupedEvent(
    canonical_title=str,
    source_items=list[RawSourceItem],
    source_links=list[str],
    merged_summary=str | None,
)
```

### Acceptance Criteria

- Multiple articles about the same model release become one item.
- Source links are preserved.
- Deduplication eval covers:
  - exact duplicate
  - near duplicate
  - non-duplicate same company
  - duplicate from different sources

---

## 10. Phase 6 — LLM-Only Categorization

### Goal

Assign each candidate event to the correct project-defined category using only LLM classification.

### Categories

The only allowed categories are:

- Model Release
- Research
- Startup Activity
- Competitor Update
- Infrastructure
- Regulation
- Other

### Important Design Decision

We will not use a hybrid rule-based + LLM categorization approach.

Reason:

- Rule-based hints can be brittle.
- Keyword matches can misclassify nuanced AI industry developments.
- The project values reasoning and meaningful AI usage.
- A strict LLM classifier with clear category definitions should give better contextual decisions.

### LLM Classification Input

For each deduplicated event, pass:

- Canonical title
- Source names
- Source URLs
- Raw summaries/content snippets
- Category definitions
- Any available date/context

### Category Definitions for Prompt

Use clear definitions:

#### Model Release

A new or updated AI model, model family, benchmarked model, or hosted model capability release.

#### Research

Academic or technical research papers, methods, benchmark findings, architectures, training techniques, or scientific results.

#### Startup Activity

Funding, acquisitions, product launches from startups, hiring, partnerships, pivots, or go-to-market activity involving AI startups.

#### Competitor Update

Strategic updates from major AI companies or relevant competitors, including product direction, partnerships, platform shifts, pricing, availability, or enterprise positioning.

#### Infrastructure

Developer tools, model-serving systems, chips, inference platforms, data infrastructure, AI SDKs, orchestration frameworks, cloud infrastructure, or deployment tooling.

#### Regulation

AI policy, law, governance, safety standards, compliance, copyright/legal rulings, or government action.

#### Other

Relevant AI developments that do not fit the above categories.

### Expected LLM Output

```json
{
  "category": "Model Release",
  "confidence": 0.91,
  "reason": "The item describes a newly released AI model with new capabilities and availability details."
}
```

### Validation Rules

- The returned category must exactly match one allowed category.
- If the LLM returns an invalid category, retry once with validation feedback.
- If still invalid, classify as `Other` and record the validation issue internally.
- Do not use keyword rules to override the LLM category.

### Acceptance Criteria

- Every final item has exactly one valid category.
- Categorization eval covers all categories.
- Ambiguous cases can be classified as `Other`.
- No hardcoded keyword categorization overrides are used.

---

## 11. Phase 7 — Analysis Generation

### Goal

Generate the full intelligence fields required by the project statement.

For each selected event, produce:

- Title
- Category
- Importance Score
- Score Reason
- Summary
- Why It Matters
- Source Links

### LLM Role

The LLM should act as a competitive intelligence analyst for Neodym.

### Prompt Requirements

The prompt should require:

1. Use only the provided source content.
2. Do not invent facts.
3. Every item must include at least one source link.
4. Explain Neodym relevance specifically.
5. Keep writing concise and executive-readable.
7. Return strict JSON matching the schema.

### Neodym Working Assumption

Until more specific company context is provided, use this assumption:

> Neodym cares about AI products, AI agents, model capabilities, enterprise AI adoption, automation infrastructure, developer tooling, and competitive shifts in the AI ecosystem.

### Acceptance Criteria

- Every selected item has all required fields.
- No item lacks source links.
- JSON validates against schema.
- The report is useful, concise, and actionable.

---

## 12. Phase 8 — Importance Scoring and Ranking

### Goal

Rank items from highest importance to lowest importance with an explainable methodology.

### Scoring Scale

| Score | Meaning |
|---:|---|
| 10 | Major strategic shift requiring immediate leadership attention |
| 9 | Highly important AI development likely to affect roadmap, competition, or customer expectations |
| 8 | Important development with near-term strategic relevance |
| 7 | Meaningful update worth monitoring or discussing |
| 6 | Useful context but not urgent |
| 5 | Moderate relevance |
| 4 | Low relevance |
| 3 | Mostly background noise |
| 2 | Minimal relevance |
| 1 | Not relevant enough for report |

### Recommended Scoring Factors

Use this rubric in the LLM prompt and README:

```text
Strategic relevance to Neodym: 35%
Market/competitive impact: 25%
Technical novelty: 20%
Urgency/timeliness: 10%
Source credibility: 10%
```

### Ranking Logic

Sort by:

1. Importance score descending
2. Strategic relevance to Neodym
3. Recency
4. Number and credibility of sources

### Selection Cap

Recommended default:

```text
Top 5–8 items per daily report
```

Reason:

- Slack reports should be readable.
- The project emphasizes signal-to-noise ratio.
- Too many items weakens product thinking.

### Methodology Text

Include in JSON metadata and README:

```text
Items are ranked by LLM-assigned importance score using a rubric based on strategic relevance to Neodym, market impact, technical novelty, urgency, and source credibility. Ties are broken by Neodym relevance, recency, and number of supporting sources.
```

### Acceptance Criteria

- Highest-value items appear first.
- Ranking eval confirms obvious high-impact events outrank low-impact events.
- Methodology is visible in report metadata and documentation.

---

## 13. Phase 9 — Report Generation

### Goal

Generate both required output files.

---

### `daily_brief.json`

Expected shape:

```json
{
  "date": "2026-06-15",
  "generated_at": "2026-06-15T10:00:00Z",
  "methodology": "Items are ranked by strategic relevance to Neodym, market impact, technical novelty, urgency, and source credibility.",
  "source_count": 8,
  "candidate_count": 31,
  "selected_count": 7,
  "items": [
    {
      "title": "Example title",
      "category": "Model Release",
      "importance_score": 9,
      "score_reason": "Example reason",
      "summary": "Example summary",
      "why_it_matters": "Example broader impact",
      "source_links": ["https://example.com"]
    }
  ]
}
```

### `daily_brief.md`

Slack-ready Markdown format:

```markdown
*Daily AI Competitive Intelligence Brief*
_Date: 2026-06-15_

Generated from 8 sources. Selected 7 high-signal developments.

*1. [9/10] Example Title*
*Category:* Model Release
*Why it matters:* ...
*Sources:* <https://example.com|Source Name>

---

*Methodology:* Items are ranked by strategic relevance to Neodym, market impact, technical novelty, urgency, and source credibility.
```

### Acceptance Criteria

- Both files are generated.
- JSON validates.
- Markdown is readable in Slack.
- Source links are present for every item.

---

## 14. Phase 10 — Optional Slack Delivery

### Goal

If credentials are available, send the Slack-ready report automatically.

### Environment Variables

```bash
SLACK_BOT_TOKEN=
SLACK_CHANNEL=#industry-trends
```

### Behavior

If Slack variables exist:

1. Read `daily_brief.md`.
2. Send message to Slack API.
3. Print success or failure.

If missing:

```text
Slack credentials unavailable; generated Slack-ready report at daily_brief.md.
```

### Important Constraint

Never hardcode credentials.

### Acceptance Criteria

- Missing Slack credentials do not fail report generation.
- README explains exactly how to configure Slack delivery.
- If token is available, delivery works.

---

## 15. Phase 11 — Evaluation Suite

### Goal

Prove key components behave as expected.

Required evaluation areas:

- Deduplication
- Categorization
- Ranking
- Output schema validation
- Source grounding

### Command

```bash
python run_evals.py
```

### Eval 1: Deduplication

Fixture:

```text
Item A: OpenAI releases GPT-5
Item B: Microsoft blog discusses OpenAI GPT-5 release
Item C: Anthropic launches Claude update
```

Expected:

- A and B grouped together.
- C remains separate.

### Eval 2: LLM-Only Categorization

Use deterministic fixtures and either mocked LLM responses or controlled prompt responses.

Fixtures:

```text
"Anthropic releases Claude 4.5" -> Model Release
"New arXiv paper proposes transformer optimization" -> Research
"AI startup raises $50M" -> Startup Activity
"EU updates AI Act guidance" -> Regulation
"NVIDIA launches inference platform" -> Infrastructure
"OpenAI changes enterprise pricing" -> Competitor Update
"AI conference announces speaker lineup" -> Other
```

Expected:

- Classifier returns one of the allowed categories.
- No rule-based category override is used.
- Invalid LLM category responses are caught by validation.

### Eval 3: Ranking

Fixtures:

```text
Major model release with strong Neodym relevance -> high score
Minor blog post about conference attendance -> low score
```

Expected:

- Major strategic item ranks above low-signal item.

### Eval 4: Output Schema Validation

Load generated or fixture report and validate with Pydantic.

Expected:

- Required fields are present.
- Importance score is between 1 and 10.
- Category is valid.
- Source links exist.

### Eval 5: Source Grounding

Check every final intelligence item has:

```python
len(source_links) >= 1
```

Reject hallucinated items without URLs.

### Expected Eval Output

```text
Running evals...

[PASS] Deduplication grouped near-duplicate model release stories.
[PASS] LLM categorization returned valid categories.
[PASS] Ranking placed strategic items above low-signal items.
[PASS] Output schema validated.
[PASS] Source grounding verified.

5/5 evals passed.
```

### Acceptance Criteria

- `python run_evals.py` runs quickly.
- Evals are demo-friendly.
- Evals do not require live network calls if avoidable.
- LLM-dependent behavior can be tested with mocked responses.

---

## 16. Phase 12 — Documentation

### Goal

README should satisfy the project statement and make the project easy to evaluate.

### README Sections

#### 1. Project Overview

Explain:

- What the agent does
- Who it is for
- Why it is not a generic news aggregator

#### 2. Quick Start

Example:

```bash
git clone https://github.com/razaahmed13/autonomous-ai-competitive-intelligence-agent.git
cd autonomous-ai-competitive-intelligence-agent
uv sync
cp .env.example .env
python run.py
```

#### 3. Configuration

Document:

```bash
AI_API_KEY=
AI_BASE_URL=
AI_MODEL=
SLACK_BOT_TOKEN=
SLACK_CHANNEL=#industry-trends
DATABASE_PATH=data/intelligence.db
```

#### 4. Architecture

Show pipeline:

```text
Sources -> Normalization -> Historical DB -> Deduplication -> LLM Categorization & Analysis -> Ranking -> Reports -> Optional Slack Delivery
```

#### 5. Data Sources

List actual sources used.

#### 6. AI Usage

Explain LLM usage in:

- Deduplication assistance
- Categorization, LLM-only
- Summarization
- Importance scoring
- Ranking support

#### 7. Scoring Methodology

Include scoring scale and weights.

#### 8. Historical Storage

Explain SQLite and repeated-run behavior.

#### 9. Evaluation Suite

Document:

```bash
python run_evals.py
```

#### 10. Slack Delivery

Explain token and channel setup.

#### 11. Limitations

Examples:

- Public source coverage is limited.
- Some websites may block scraping.
- LLM output depends on source quality.
- Slack delivery requires credentials.
- Neodym-specific scoring would improve with deeper company context.

#### 12. Future Improvements

Examples:

- Embeddings for stronger deduplication.
- More data sources.
- Scheduled daily cron job.
- Web dashboard.
- Human feedback loop.
- Source credibility weighting.
- Richer Neodym strategy profile.

---

## 17. Phase 13 — Agent Usage Log

### Goal

Satisfy the required deliverable explaining AI tool usage.

### Required Sections

#### AI Tools Used

Examples:

- Hermes Agent / Maalik
- Codex if used
- LLM provider used by the app

#### How They Were Used

Examples:

- Requirement analysis
- Code generation
- Prompt drafting
- Debugging
- Evaluation design
- Report generation

#### What Was Manually Verified

Examples:

- Source collection output
- JSON schema validity
- Slack markdown readability
- Eval results
- Historical duplicate prevention

#### Problems Encountered

Examples:

- Some websites lacked RSS feeds.
- Some sources returned incomplete content.
- LLM needed strict JSON validation.
- Slack credentials unavailable, so Slack-ready output was generated instead.

#### Key Lessons Learned

Examples:

- Highest value comes from ranking/actionability, not collecting many articles.
- Source grounding is essential.
- Evaluation fixtures catch regressions in deduplication and ranking.

---

## 18. Phase 14 — Demo Preparation

### Goal

Prepare a 5–10 minute demo that directly matches the evaluation criteria.

### Demo Flow

#### 1. Problem Framing — 30 seconds

Explain:

> This system helps Neodym quickly understand important AI developments each morning.

#### 2. Architecture — 1 minute

Show:

```text
Sources -> Deduplication -> LLM Categorization & Analysis -> Ranking -> JSON/Slack Reports -> Historical DB
```

#### 3. Run the System — 1–2 minutes

Command:

```bash
python run.py
```

Show terminal output:

```text
Collected X items from Y sources.
Selected Z high-signal developments.
Wrote daily_brief.json and daily_brief.md.
```

#### 4. Show Generated Reports — 2 minutes

Open:

```text
daily_brief.md
daily_brief.json
```

Highlight:

- Importance scores
- Why it matters
- Source links

#### 5. Show Evals — 1 minute

Run:

```bash
python run_evals.py
```

Show all passing.

#### 6. Show Historical Behavior — 1 minute

Run the system again or show database records.

Explain:

- Previously reported items are skipped.
- Meaningful new developments can still appear.

#### 7. Future Improvements — 30 seconds

Mention:

- Embeddings
- More sources
- Scheduled Slack delivery
- Dashboard
- Better Neodym-specific scoring

---

## 19. Suggested Implementation Order

### Day 1 / First Build Pass

#### Phase A: Core Skeleton

1. Add project dependencies.
2. Add config.
3. Add Pydantic models.
4. Add SQLite database layer.
5. Add source definitions.
6. Add RSS fetcher.
7. Add basic pipeline orchestration.

Outcome:

```bash
python run.py collect
```

works and stores raw items.

#### Phase B: Intelligence Pipeline

1. Add deterministic deduplication.
2. Add LLM client.
3. Add LLM-only categorization prompt.
4. Add analysis prompt.
5. Add ranking logic.
6. Generate `daily_brief.json`.
7. Generate `daily_brief.md`.

Outcome:

```bash
python run.py
```

produces both reports.

### Day 2 / Quality Pass

#### Phase C: Historical Tracking

1. Store reported intelligence items.
2. Skip already-reported fingerprints.
3. Add `--force` option to regenerate if needed.

Outcome:

Repeated runs do not duplicate reports.

#### Phase D: Evaluation Suite

1. Deduplication eval.
2. LLM-only categorization eval.
3. Ranking eval.
4. Schema validation eval.
5. Source grounding eval.

Outcome:

```bash
python run_evals.py
```

passes.

#### Phase E: Documentation and Demo Polish

1. Complete README.
2. Complete agent usage log.
3. Add Slack delivery instructions.
4. Add demo guide.
5. Verify fresh setup instructions.
6. Commit final working version.

Outcome:

Project is submission-ready.

---

## 20. Implementation Milestones

### Milestone 1: Local Source Collection Works

Success criteria:

- Fetches from at least 5 sources.
- Normalizes items.
- Stores raw items in SQLite.
- Handles failed sources gracefully.

### Milestone 2: First Report Generated

Success criteria:

- Produces valid `daily_brief.json`.
- Produces Slack-ready `daily_brief.md`.
- Every item has source links.
- Items are ranked.

### Milestone 3: LLM Intelligence Quality

Success criteria:

- LLM-only categories are valid and reasonable.
- Summaries are concise.
- Scores have clear reasons.

### Milestone 4: Historical Duplicate Prevention

Success criteria:

- Same items are not surfaced repeatedly.
- DB proves prior items were stored.
- README explains behavior.

### Milestone 5: Evaluation Suite Passes

Success criteria:

```bash
python run_evals.py
```

All required eval areas are covered.

### Milestone 6: Submission Polish

Success criteria:

- README complete.
- Agent usage log complete.
- Demo guide ready.
- Repo clean.
- Generated outputs included.

---

## 21. Key Product Decisions

### 1. Optimize for Quality Over Quantity

The assignment explicitly says the goal is not news aggregation. We should collect enough sources to demonstrate breadth, but final output should be curated.

Recommended final report size:

```text
5–8 items
```

### 2. Keep Architecture Simple

Avoid:

- Web dashboard
- Complex queues
- Kubernetes
- Heavy vector DB
- Overengineering

Use:

- Python CLI
- SQLite
- Markdown/JSON output
- Optional Slack API

### 3. Make LLM Usage Meaningful

The LLM should perform real intelligence work:

- Event clustering assistance
- LLM-only classification
- Strategic analysis
- Importance scoring
- Recommendations

### 4. Use LLM-Only Categorization

Do not use keyword rules to classify categories. Use the LLM with strict category definitions and schema validation.

### 5. Make Evaluation Visible

The evaluation suite is a major grading area and should be easy to run and understand.

### 6. Make Slack Output Polished

The success criterion says:

> I can open Slack each morning, immediately understand what happened in AI, why it matters to Neodym, and what actions we should consider.

So `daily_brief.md` should be polished, concise, and executive-readable.

---

## 22. Risks and Mitigations

### Risk 1: Source Websites Block Scraping

Mitigation:

- Prefer RSS and public APIs.
- Gracefully skip failed sources.
- Log source failures.
- Include enough sources that one failure does not break the report.

### Risk 2: LLM Returns Invalid JSON

Mitigation:

- Use strict prompts.
- Validate with Pydantic.
- Retry once with validation feedback.
- Fall back safely only if source links remain intact.

### Risk 3: Duplicate Stories Still Appear

Mitigation:

- Use deterministic title/URL matching first.
- Add LLM event clustering.
- Add eval cases.

### Risk 4: Categorization Is Wrong

Mitigation:

- Use clear category definitions.
- Require confidence and reason.
- Validate category against allowed enum.
- Retry invalid responses.
- Use eval fixtures covering all categories.

### Risk 5: Report Is Too Generic

Mitigation:

- Force recommended actions to be practical.
- Score low if Neodym relevance is weak.

### Risk 6: Historical Storage Hides Important Follow-Ups

Mitigation:

- Store event fingerprints, not just company names.
- Allow meaningful updates if title/content differs enough.
- Add `--force` or `--include-seen` for debugging/demo.

### Risk 7: Slack Credentials Are Unavailable

Mitigation:

- Generate Slack-ready markdown regardless.
- Document Slack setup.
- Treat actual sending as optional.

---

## 23. Minimum Viable Scope

If time gets tight, prioritize:

1. Fetch from 5+ sources.
2. Generate `daily_brief.json`.
3. Generate `daily_brief.md`.
4. Include source-grounded LLM analysis.
5. Use LLM-only categorization.
6. Store history in SQLite.
7. Include `python run_evals.py`.
8. Write complete README.

Defer if needed:

- Full Slack API sending
- Embeddings-based deduplication
- Deployment URL
- Dashboard
- Advanced scheduling

---

## 24. Final Build Sequence

1. Models and config
2. SQLite storage
3. RSS/public source collection
4. Raw item normalization
5. Deterministic deduplication
6. LLM-assisted event clustering
7. LLM-only categorization
8. LLM analysis generation
9. Importance scoring and ranking
10. JSON report generation
11. Slack Markdown generation
12. Historical duplicate prevention
13. Evaluation suite
14. Optional Slack sending
15. README, agent usage log, and demo guide
16. Final run and verification
17. Commit and push

---

## 25. Notes for Future Plan Updates

When requirements change, update this file first so implementation stays aligned.

Important current decisions:

- Categorization is LLM-only.
- Slack delivery is optional, but Slack-ready Markdown is required.
- Historical storage should use SQLite.
- The report should prioritize high-signal actionable intelligence over article count.
- Every final item must be source-grounded.
