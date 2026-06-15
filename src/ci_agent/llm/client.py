from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import Settings
from ..scoring import SCORING_CRITERIA


class LLMClient:
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class OpenAICompatibleLLMClient(LLMClient):
    def __init__(self, settings: Settings):
        if not settings.ai_api_key:
            raise ValueError("AI_API_KEY is required for live LLM intelligence generation")
        self.api_key = settings.ai_api_key
        self.base_url = (settings.ai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = settings.ai_model or "gpt-4o-mini"
        self.timeout = settings.request_timeout_seconds

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


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
            "why_it_matters_to_neodym": "Neodym should review whether this changes assumptions about agents, model capabilities, or AI infrastructure.",
            "recommended_action": "Review the linked source and decide whether a product, research, or competitive follow-up is needed.",
            "scoring_assessments": [
                {
                    "id": criterion_id,
                    "status": status,
                    "evidence": f"Offline demo assessment for {criterion_id} based on the supplied title and source context.",
                    "reason": "Use AI_API_KEY for source-grounded live assessment.",
                }
                for criterion_id in SCORING_CRITERIA
            ],
        }


def build_llm_client(settings: Settings) -> LLMClient:
    if (settings.ai_model or "").lower() == "offline-demo":
        return OfflineDemoLLMClient()
    return OpenAICompatibleLLMClient(settings)


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
