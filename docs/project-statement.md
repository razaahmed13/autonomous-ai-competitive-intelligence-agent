# Autonomous AI Competitive Intelligence Agent — Project Statement

Autonomous AI Competitive Intelligence Agent

Objective

Build an AI-powered competitive intelligence system that discovers, analyzes, prioritizes, and summarizes important developments in artificial intelligence.

The goal is not to aggregate news. The goal is to identify what matters, explain why it matters, and provide actionable intelligence for Neodym.

We are evaluating your ability to prioritize, make engineering decisions, and ship a useful system within 48 hours. We are not expecting a perfect production-ready platform.

Time Limit: 48 Hours

Project Overview

Build a system that collects updates from AI-related sources and generates a daily intelligence report.

The report should help a founder, engineer, or product team quickly understand:

What happened

Why it matters


What action should be considered

The system should collect information from multiple independent sources and focus on producing high-quality, relevant intelligence rather than maximizing the number of articles collected. The system should be designed as a recurring intelligence workflow rather than a one-time report generator. The architecture should support running on a daily basis, ingesting new information, tracking previously processed items, and generating updated reports over time.

Core Requirements

Data Collection

Collect information from multiple sources such as:

Company blogs

Research feeds

RSS feeds

Public APIs

Public websites

The system should demonstrate the ability to gather information from multiple independent sources and produce a meaningful intelligence report.

Deduplication

The system should identify duplicate or near-duplicate stories and merge them into a single intelligence item while preserving source references.

Example:

If several articles discuss the same model release, the system should recognize them as a single event rather than reporting them separately.

Categorization

Assign each item to an appropriate category, such as:

Model Release

Research

Startup Activity

Competitor Update

Infrastructure

Regulation

Other

Analysis

For each selected item generate:

Title

Category

Importance Score (1-10)

Score Reason

Summary

Why It Matters



Source Links

Every intelligence item must include at least one source link. Items without sources should not appear in the final report.

Ranking

Rank items from highest importance to lowest importance.

The most important developments should appear first.

The ranking methodology should be explainable.

AI Requirements

The project must use LLMs for meaningful parts of the workflow.

Examples include:5

Summarization

Classification

Deduplication

Ranking

Recommendation generation

Simple API wrapping is not sufficient.

Use of AI-assisted development tools such as Codex, Hermes is encouraged. We are evaluating your ability to leverage AI effectively as part of the engineering process.

Output Requirements

Structured Output

Generate a machine-readable report:

daily_brief.json

Slack Report

Generate a Slack-formatted intelligence report:

daily_brief.md

Preferred Slack channel:

#industry-trends

If Slack credentials are available, send the report automatically.

If Slack credentials are unavailable, generate a Slack-ready report and document how delivery would be configured.

Do not hardcode credentials, secrets, or API keys.

Historical Storage

Store previously processed items to avoid duplicate reporting across future runs.

Any reasonable storage solution is acceptable.

Examples:

SQLite

PostgreSQL

JSON storage

The system should demonstrate how it would continue operating over multiple days without repeatedly surfacing the same information. The system should be capable of running repeatedly (e.g., daily) and should avoid resurfacing previously reported developments unless there is meaningful new information.

Evaluation Suite

Include a lightweight evaluation suite demonstrating that key system components behave as expected.

At minimum, evaluate:

Deduplication

Categorization

Ranking

Output schema validation

Source grounding

The project should include a command such as:

python run_evals.py

or clearly document the equivalent command.

Deliverables

Source Code

GitHub repository

Working Product

Required:

Local run instructions

Optional:

Deployment URL

A local working system is acceptable. Deployment is considered a bonus if the core functionality is complete.

Generated Outputs

Include:

daily_brief.json

daily_brief.md

Documentation

README should include:

Setup instructions

Architecture overview

Technical decisions

Data sources

AI usage

Scoring methodology

Limitations

Future improvements

Slack delivery instructions

Agent Usage Log

Include a short document describing:

AI tools used

How they were used

What was manually verified

Problems encountered

Key lessons learned

Demo For Meeting

a 5-10 minute demo showing:

Architecture

Features

AI workflow

Generated report

Slack delivery or Slack-ready output

Evaluation results

Future improvements

Evaluation Criteria

Engineering Execution (25%)

Code quality

Architecture

Reliability

Maintainability

Product Thinking (20%)

Usefulness

Relevance

Actionability

Signal-to-noise ratio

AI Integration (20%)

Workflow design

Prompt design

Structured outputs

Grounded reasoning

Evaluation & Testing (15%)

Meaningful evaluation suite

Validation of outputs

Evidence of quality checks

Documentation & Communication (10%)

README quality

Demo quality

Clarity of explanation

Deployment & Usability (10%)

Ease of setup

Ease of use

Slack-ready output

Operational practicality

Success Criteria

A successful submission should make a team member think:

"I can open Slack each morning, immediately understand what happened in AI, why it matters to Neodym, and what actions we should consider."

Focus on usefulness, execution, prioritization, and shipping. A working system with strong insights is preferred over a highly polished but incomplete product.
