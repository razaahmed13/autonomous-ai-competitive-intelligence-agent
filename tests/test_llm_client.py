from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ci_agent.config import Settings
from ci_agent.llm.client import CodexCliLLMClient, OfflineDemoLLMClient, build_llm_client


def test_build_llm_client_defaults_to_codex_cli_without_using_project_api_key():
    settings = Settings(ai_api_key="should-not-be-used", ai_model=None)

    client = build_llm_client(settings)

    assert isinstance(client, CodexCliLLMClient)


def test_build_llm_client_keeps_offline_demo_for_local_smoke_tests():
    settings = Settings(ai_model="offline-demo")

    client = build_llm_client(settings)

    assert isinstance(client, OfflineDemoLLMClient)


def test_codex_cli_client_uses_output_last_message_file_and_parses_json(tmp_path):
    calls: list[dict] = []

    def fake_runner(command, *, input, capture_output, text, timeout, env):
        calls.append(
            {
                "command": command,
                "input": input,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
                "env": env,
            }
        )
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('{"category":"Other","confidence":0.9,"reason":"Parsed."}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="codex event noise", stderr="")

    client = CodexCliLLMClient(Settings(request_timeout_seconds=12), runner=fake_runner, output_dir=tmp_path)

    result = client.complete_json(system_prompt="System prompt", user_prompt="User prompt")

    assert result == {"category": "Other", "confidence": 0.9, "reason": "Parsed."}
    assert len(calls) == 1
    command = calls[0]["command"]
    assert command[:2] == ["codex", "exec"]
    assert "--output-last-message" in command
    assert "--json" not in command
    assert command[-1] == "-"
    assert "System prompt" in calls[0]["input"]
    assert "User prompt" in calls[0]["input"]
    assert calls[0]["capture_output"] is True
    assert calls[0]["text"] is True
    assert calls[0]["timeout"] == 12


def test_codex_cli_client_removes_project_and_direct_llm_api_keys_from_subprocess_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "project-key")
    monkeypatch.setenv("AI_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("OPENAI_API_KEY", "direct-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "direct-anthropic-key")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")
    captured_env = {}

    def fake_runner(command, *, input, capture_output, text, timeout, env):
        captured_env.update(env)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('{"ok":true}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    client = CodexCliLLMClient(Settings(), runner=fake_runner, output_dir=tmp_path)

    assert client.complete_json(system_prompt="system", user_prompt="user") == {"ok": True}
    assert "AI_API_KEY" not in captured_env
    assert "AI_BASE_URL" not in captured_env
    assert "OPENAI_API_KEY" not in captured_env
    assert "ANTHROPIC_API_KEY" not in captured_env
    assert captured_env["CODEX_HOME"] == "/tmp/codex-home"


def test_codex_cli_client_reports_command_failures_without_leaking_prompt(tmp_path):
    def fake_runner(command, *, input, capture_output, text, timeout, env):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="not authenticated")

    client = CodexCliLLMClient(Settings(), runner=fake_runner, output_dir=tmp_path)

    with pytest.raises(RuntimeError, match="Codex CLI failed") as exc_info:
        client.complete_json(system_prompt="secret system prompt", user_prompt="secret user prompt")

    message = str(exc_info.value)
    assert "not authenticated" in message
    assert "secret system prompt" not in message
    assert "secret user prompt" not in message


def test_codex_cli_client_parses_json_inside_markdown_fence(tmp_path):
    def fake_runner(command, *, input, capture_output, text, timeout, env):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('```json\n{"ok": true}\n```', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    client = CodexCliLLMClient(Settings(), runner=fake_runner, output_dir=tmp_path)

    assert client.complete_json(system_prompt="system", user_prompt="user") == {"ok": True}
