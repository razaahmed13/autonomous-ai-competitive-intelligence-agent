from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..scoring import SCORING_CRITERIA

Runner = Callable[..., subprocess.CompletedProcess[str]]


class LLMClient:
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class CodexCliLLMClient(LLMClient):
    """Approved Codex CLI transport for JSON-only LLM calls.

    Uses `codex exec --output-last-message` so stdout progress/event noise does
    not contaminate the JSON payload we parse.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        runner: Runner = subprocess.run,
        output_dir: str | Path | None = None,
    ):
        self.command = "codex"
        self.timeout = settings.request_timeout_seconds
        self.runner = runner
        self.output_dir = Path(output_dir) if output_dir is not None else None

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="codex-last-message-",
            dir=self.output_dir,
            delete=False,
        ) as output_file:
            output_path = Path(output_file.name)

        command = [
            self.command,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
            "-",
        ]
        prompt = _build_codex_json_prompt(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            completed = self.runner(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=_codex_subprocess_env(),
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or completed.stdout or "Codex CLI exited with a non-zero status.").strip()
                raise RuntimeError(f"Codex CLI failed: {stderr}")
            content = output_path.read_text(encoding="utf-8").strip()
            if not content:
                raise RuntimeError("Codex CLI did not write a final message to --output-last-message.")
            return _loads_json_message(content)
        finally:
            output_path.unlink(missing_ok=True)


class OfflineDemoLLMClient(LLMClient):
    """Deterministic local client for smoke tests when no LLM credentials are present.

    This is not a replacement for submission-quality LLM analysis; it lets the CLI
    demonstrate file generation in environments without credentials.
    """

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        title = _extract_line_value(user_prompt, "Canonical title") or "AI development"
        category_context = "\n".join(filter(None, [title, _extract_line_value(user_prompt, "Source names")]))
        category = _demo_category(category_context)
        if "classify" in system_prompt.lower() or "categorization" in user_prompt.lower():
            return {"category": category, "confidence": 0.5, "reason": "Offline demo categorization based on the supplied title."}
        status = _demo_status(title)
        return {
            "title": title,
            "summary": f"{title} was identified from public AI sources.",
            "why_it_matters": "This development may affect AI product expectations, technical direction, or market positioning.",
            "scoring_assessments": [
                {
                    "id": criterion_id,
                    "status": status,
                    "evidence": f"Offline demo assessment for {criterion_id} based on the supplied title and source context.",
                    "reason": "Use AI_MODEL=codex-cli for source-grounded live assessment.",
                }
                for criterion_id in SCORING_CRITERIA
            ],
        }


def build_llm_client(settings: Settings) -> LLMClient:
    if (settings.ai_model or "").lower() == "offline-demo":
        return OfflineDemoLLMClient()
    return CodexCliLLMClient(settings)


def _build_codex_json_prompt(*, system_prompt: str, user_prompt: str) -> str:
    return f"""
You are being used as a JSON-only LLM transport for an automated competitive-intelligence workflow.
Return only one valid JSON object. Do not include Markdown, commentary, code fences, or tool calls.

<SYSTEM_PROMPT>
{system_prompt}
</SYSTEM_PROMPT>

<USER_PROMPT>
{user_prompt}
</USER_PROMPT>
""".strip()


def _codex_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in [
        "AI_API_KEY",
        "AI_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]:
        env.pop(key, None)
    return env


def _loads_json_message(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Codex CLI final message must be a JSON object.")
    return data


def _extract_line_value(text: str, label: str) -> str | None:
    prefix = f"{label}:"
    for line in text.splitlines():
        if line.strip().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _extract_links(text: str) -> list[str]:
    import re

    return re.findall(r"https?://[^\s\]]+", text)


def _demo_category(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["arxiv", "paper", "research"]):
        return "Research"
    if any(word in lower for word in ["funding", "acquire", "acquisition", "startup", "raises"]):
        return "Startup Activity"
    if any(word in lower for word in ["inference", "platform", "gpu", "chip", "sdk", "infrastructure"]):
        return "Infrastructure"
    if any(word in lower for word in ["act", "regulation", "policy", "governance"]):
        return "Regulation"
    if any(word in lower for word in ["model", "gpt", "claude", "gemini", "llama"]):
        return "Model Release"
    if any(word in lower for word in ["openai", "anthropic", "deepmind", "google"]):
        return "Competitor Update"
    return "Other"


def _demo_status(title: str) -> str:
    lower = title.lower()
    if any(word in lower for word in ["openai", "anthropic", "google", "deepmind", "model"]):
        return "strong"
    return "good"
