"""LLM client with telemetry. Two wire protocols - OpenAI chat completions and Anthropic messages - cover
any provider; switch with one string, `LLM=<provider>:<model>` in .env or `--llm` on the command line:

  openai:gpt-6.1-sol (default)   OpenAI, reasoning_effort low   key: OPENAI_API_KEY (or LLM_API_KEY)
  ollama:qwen3:30b-a3b           local Ollama (its OpenAI-compatible /v1), thinking off by default
  openrouter:<vendor>/<model>    OpenRouter                  key: OPENROUTER_API_KEY
  groq:<model> · mistral:<model> · deepseek:<model> · together:<model>    their OpenAI-compatible APIs
  anthropic:claude-haiku-4-5     Anthropic messages API      key: ANTHROPIC_API_KEY
  compat:<model>                 any other OpenAI-compatible endpoint at LLM_BASE_URL
  claude-code:haiku              the Claude Code CLI on this machine (`claude -p`): no API key, the
                                 subscription pays; the model is an alias (haiku, sonnet) or a full name

Other settings: LLM_BASE_URL and LLM_API_KEY override the preset; LLM_REASONING (none|low|medium|high)
is sent as reasoning_effort on OpenAI-protocol calls; LLM_TIMEOUT_S (default 30 - every e-mail must
reach the arena within 60 s of the supplier's reply); LLM_PARALLEL (default 4 concurrent calls).

Every call is recorded: an `llm_call` event (purpose, model, latency, queue wait, tokens, ok/error,
output; `cost_usd` where the provider reports it - claude-code does) and metrics
(`llm.seconds.<purpose>`, `llm.calls`, `llm.errors`, `llm.tokens.prompt|completion`).
"""

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass

import httpx

from negotiator.telemetry import Recorder, log

DEFAULT_SPEC = "openai:gpt-6.1-sol"


@dataclass(frozen=True)
class Preset:
    protocol: str  # openai | anthropic | claude-code
    base_url: str
    key_env: str | None
    reasoning: str | None = None  # default reasoning_effort


PRESETS = {
    "ollama": Preset("openai", "http://localhost:11434/v1", None, reasoning="none"),
    "openai": Preset("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", reasoning="low"),
    "openrouter": Preset("openai", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": Preset("openai", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "mistral": Preset("openai", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "deepseek": Preset("openai", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "together": Preset("openai", "https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "compat": Preset("openai", "", None),
    "anthropic": Preset("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY"),
    "claude-code": Preset("claude-code", "claude -p", None),
}


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, spec: str | None = None, recorder: Recorder | None = None) -> None:
        spec = spec or os.environ.get("LLM") or DEFAULT_SPEC
        provider, sep, model = spec.partition(":")
        if not sep or provider not in PRESETS or not model:
            raise ValueError(f"LLM spec {spec!r}: use <provider>:<model>, providers: {', '.join(PRESETS)}")
        preset = PRESETS[provider]
        self.provider, self.model, self.protocol = provider, model, preset.protocol
        self.base_url = (os.environ.get("LLM_BASE_URL") or preset.base_url).rstrip("/")
        if not self.base_url:
            raise ValueError("compat:<model> needs LLM_BASE_URL")
        self.api_key = os.environ.get("LLM_API_KEY") or (os.environ.get(preset.key_env, "") if preset.key_env else "")
        if preset.key_env and not self.api_key:
            raise ValueError(f"{provider} needs {preset.key_env} (or LLM_API_KEY) in the environment or .env")
        self.reasoning = os.environ.get("LLM_REASONING", preset.reasoning or "") or None
        self.timeout = float(os.environ.get("LLM_TIMEOUT_S", "30"))
        self.recorder = recorder
        self._slots = threading.Semaphore(int(os.environ.get("LLM_PARALLEL", "4")))
        self.http = httpx.Client(timeout=self.timeout)
        self._last = threading.local()  # what the last call on this thread cost, if the provider says

    def describe(self) -> str:
        return f"{self.provider}:{self.model}"

    # ------------------------------------------------------------------ calls
    def json(
        self,
        system: str,
        user: str,
        *,
        purpose: str = "llm",
        max_tokens: int = 700,
        timeout: float | None = None,
        context: dict | None = None,
    ) -> dict:
        """One call that must return a JSON object; raises LLMError on timeout, HTTP error or bad output."""
        budget = timeout or self.timeout
        start = time.perf_counter()
        waited, text, usage, error = 0.0, "", (None, None), None
        try:
            if not self._slots.acquire(timeout=budget):
                raise LLMError("no free LLM slot in time")
            waited = time.perf_counter() - start
            try:
                text, usage = self._call(system, user, max_tokens, max(1.0, budget - waited))
            finally:
                self._slots.release()
            return parse_json(text)
        except (httpx.HTTPError, ValueError, KeyError, LLMError) as e:
            error = f"{type(e).__name__}: {e}"
            raise LLMError(error) from e
        finally:
            prompt = {"system": system, "user": user}
            self._record(purpose, time.perf_counter() - start, waited, usage, error, len(user), text, context, prompt)

    def _call(self, system: str, user: str, max_tokens: int, timeout: float) -> tuple[str, tuple]:
        system = system + "\nReply with one JSON object and nothing else."
        self._last.cost_usd = None
        if self.protocol == "claude-code":
            return self._claude_code(system, user, timeout)
        if self.protocol == "anthropic":
            r = self.http.post(
                f"{self.base_url}/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=timeout,
            )
            _raise_for_status(r)
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            u = data.get("usage") or {}
            return text, (u.get("input_tokens"), u.get("output_tokens"))
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        if self.provider == "openai":
            # OpenAI's current models take max_completion_tokens and only their default temperature
            body["max_completion_tokens"] = max_tokens
        else:
            body.update(temperature=0.3, max_tokens=max_tokens)
        if self.reasoning:
            body["reasoning_effort"] = self.reasoning
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = self.http.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=timeout)
        _raise_for_status(r)
        data = r.json()
        u = data.get("usage") or {}
        return data["choices"][0]["message"].get("content") or "", (u.get("prompt_tokens"), u.get("completion_tokens"))

    def _claude_code(self, system: str, user: str, timeout: float) -> tuple[str, tuple]:
        # an empty working directory and no setting sources: no project hooks, CLAUDE.md or tools
        command = ["claude", "-p", "--model", self.model, "--tools", "", "--strict-mcp-config"]
        command += ["--disable-slash-commands", "--no-session-persistence", "--setting-sources", ""]
        command += ["--output-format", "json", "--system-prompt", system]
        try:
            with tempfile.TemporaryDirectory() as cwd:
                run = subprocess.run(command, input=user, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise LLMError(f"claude -p: {e}") from e
        if run.returncode != 0:
            raise LLMError(f"claude -p exited {run.returncode}: {(run.stderr or run.stdout)[:300]}")
        data = json.loads(run.stdout)
        if data.get("is_error"):
            raise LLMError(f"claude -p: {str(data.get('result'))[:300]}")
        u = data.get("usage") or {}
        prompt = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        self._last.cost_usd = data.get("total_cost_usd")
        return str(data.get("result") or ""), (prompt, u.get("output_tokens"))

    def _record(self, purpose, elapsed, waited, usage, error, prompt_chars, text, context, prompt=None) -> None:
        prompt_tokens, completion_tokens = usage
        if self.recorder:
            m = self.recorder.metrics
            m.incr("llm.calls")
            m.observe(f"llm.seconds.{purpose}", elapsed)
            if waited > 0.05:
                m.observe("llm.queue_wait", waited)
            if error:
                m.incr("llm.errors")
                m.incr(f"llm.errors.{purpose}")
            if prompt_tokens:
                m.incr("llm.tokens.prompt", prompt_tokens)
            if completion_tokens:
                m.incr("llm.tokens.completion", completion_tokens)
            self.recorder.event(
                "llm_call",
                purpose=purpose,
                model=self.describe(),
                seconds=round(elapsed, 2),
                queue_seconds=round(waited, 2),
                prompt_chars=prompt_chars,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=getattr(self._last, "cost_usd", None),
                ok=error is None,
                error=error,
                output=text[:3000],
                _input=prompt,  # to the tracing sink only, not to events.jsonl
                **(context or {}),
            )
        if error:
            log.warning("LLM %s failed after %.1fs: %s", purpose, elapsed, error)
        else:
            log.debug("LLM %s %.1fs (%s+%s tokens)", purpose, elapsed, prompt_tokens, completion_tokens)

    def warm_up(self) -> float:
        """Load the model (a local one can take a while) before any clock runs; returns seconds."""
        start = time.perf_counter()
        try:
            self.json("You answer in JSON.", 'Return {"ok": true}', purpose="warmup", max_tokens=20, timeout=300)
        except LLMError as e:
            log.warning("LLM warm-up failed: %s", e)
        return time.perf_counter() - start


def _raise_for_status(r: httpx.Response) -> None:
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")


def parse_json(text: str) -> dict:
    """The first JSON object in a reply (tolerates code fences, chatter and <think> blocks)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("reply is not a JSON object")
    return value
