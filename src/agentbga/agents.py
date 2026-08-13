"""Named seat controllers for several HTTP model APIs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterator, Protocol


class AgentError(RuntimeError):
    pass


HARNESS_BACKENDS = frozenset({"claude", "pi", "codex", "opencode"})
HARNESS_REASONING_EFFORT = "max"


@dataclass(frozen=True)
class PlayerConfig:
    """Controller configuration with an optional process-only API key."""

    name: str
    backend: str
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    wire_api: str | None = None
    reasoning_effort: str | None = None
    api_key: str | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, value: dict[str, Any], seat: int) -> "PlayerConfig":
        allowed = {"name", "backend", "model", "base_url", "api_key_env", "wire_api"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"player {seat} has unknown fields: {', '.join(sorted(unknown))}")
        backend = str(value.get("backend", "")).lower()
        if backend not in {"random", "human", "openai", "anthropic", "gemini", *HARNESS_BACKENDS}:
            raise ValueError(f"player {seat} has unsupported backend: {backend}")
        name = str(value.get("name", f"Seat {seat}")).strip()
        if not name:
            raise ValueError(f"player {seat} name cannot be empty")
        model = value.get("model")
        if backend not in {"random", "human"} and not model:
            raise ValueError(f"player {seat} using {backend} requires model")
        defaults = {
            "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
            "anthropic": ("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
            "gemini": ("https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY"),
            "claude": ("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
            "pi": ("https://api.openai.com/v1", "AGENTBGA_API_KEY"),
            "codex": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
            "opencode": (None, "DEEPSEEK_API_KEY"),
        }
        base_url, api_key_env = (None, None)
        if backend in defaults:
            base_url, api_key_env = defaults[backend]
        selected_url = str(value.get("base_url") or base_url) if (value.get("base_url") or base_url) else None
        if selected_url:
            parsed = urllib.parse.urlsplit(selected_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"player {seat} base_url must be an absolute http(s) URL")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError(f"player {seat} base_url cannot contain credentials, query, or fragment")
        selected_key_env = str(value.get("api_key_env") or api_key_env) if (value.get("api_key_env") or api_key_env) else None
        if selected_key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", selected_key_env):
            raise ValueError(f"player {seat} api_key_env must be an environment variable name")
        wire_api = value.get("wire_api")
        if wire_api is not None and wire_api not in {"responses", "chat"}:
            raise ValueError(f"player {seat} wire_api must be responses or chat")
        return cls(
            name=name,
            backend=backend,
            model=str(model) if model else None,
            base_url=selected_url,
            api_key_env=selected_key_env,
            wire_api=str(wire_api) if wire_api else None,
            reasoning_effort=HARNESS_REASONING_EFFORT if backend in HARNESS_BACKENDS else None,
        )

    def public_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None and key != "api_key"}


StreamSink = Callable[[str, str], None]


class ModelAgent(Protocol):
    def choose(
        self, observation: dict[str, Any], legal: list[dict[str, Any]],
        on_stream: StreamSink | None = None,
    ) -> tuple[str, dict[str, Any]]: ...


def load_players_config(path: str) -> list[PlayerConfig]:
    raw = Path(path).read_text(encoding="utf-8") if path != "-" else __import__("sys").stdin.read()
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema_version") != "agentbga.players.v1":
        raise ValueError("players config must use schema_version agentbga.players.v1")
    players = value.get("players")
    if not isinstance(players, list):
        raise ValueError("players config requires a players array")
    result = [PlayerConfig.from_dict(player, seat) for seat, player in enumerate(players) if isinstance(player, dict)]
    if len(result) != len(players):
        raise ValueError("every player entry must be an object")
    if len(result) not in (2, 3, 4):
        raise ValueError("players config requires 2, 3, or 4 players")
    if len({player.name for player in result}) != len(result):
        raise ValueError("player names must be unique within a match")
    return result


def random_choice(legal: list[dict[str, Any]], rng: random.Random) -> str:
    if not legal:
        raise AgentError("no legal actions")
    return rng.choice(legal)["id"]


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise AgentError("model response did not contain a JSON object")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise AgentError("model response JSON must be an object")
    return value


def _prompt(observation: dict[str, Any], legal: list[dict[str, Any]]) -> tuple[str, str]:
    game = str(observation.get("game", "board game")).replace("_", " ").title()
    system = (
        f"You are playing {game} in a rigorous long-horizon board-game benchmark. "
        "Use the complete seat-scoped observation, maintain a long-term plan, and account "
        "for opponents and end-game timing. Choose exactly one action from LEGAL_ACTIONS "
        "for this decision step. Return only JSON of the form "
        '{"action_id":"a-..."}. Never invent an action.'
    )
    compact_actions = [{"id": item["id"], **item["action"]} for item in legal]
    user = json.dumps({"OBSERVATION": observation, "LEGAL_ACTIONS": compact_actions}, separators=(",", ":"))
    return system, user


class HTTPModelAgent:
    backend = "http"

    def __init__(self, *, model: str, base_url: str, api_key_env: str, api_key: str | None = None, timeout: float = 600):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.api_key = api_key or os.environ.get(api_key_env)
        self.timeout = timeout
        if not self.api_key:
            raise AgentError(f"missing API key; set {api_key_env}")

    def request_parts(self, system: str, user: str) -> tuple[str, dict[str, str], dict[str, Any]]:
        raise NotImplementedError

    def response_parts(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        raise NotImplementedError

    def stream_request(self, url: str, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        body["stream"] = True
        return url, body

    def stream_parts(self, payload: dict[str, Any]) -> tuple[str, str, dict[str, Any], str | None]:
        raise NotImplementedError

    @staticmethod
    def _sse_payloads(response: Any) -> Iterator[str]:
        data: list[str] = []
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                if data:
                    yield "\n".join(data)
                    data = []
                continue
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            yield "\n".join(data)

    def _stream_response(
        self, response: Any, on_stream: StreamSink | None,
    ) -> tuple[str, dict[str, Any], str]:
        content: list[str] = []
        reasoning: list[str] = []
        usage: dict[str, Any] = {}
        actual_model = self.model
        for data in self._sse_payloads(response):
            if data == "[DONE]":
                break
            payload = json.loads(data)
            content_delta, reasoning_delta, chunk_usage, chunk_model = self.stream_parts(payload)
            if reasoning_delta:
                reasoning.append(reasoning_delta)
                if on_stream:
                    on_stream("reasoning", reasoning_delta)
            if content_delta:
                content.append(content_delta)
                if on_stream:
                    on_stream("content", content_delta)
            if chunk_usage:
                usage.update(chunk_usage)
            if chunk_model:
                actual_model = chunk_model
        return "".join(content), usage, actual_model

    def choose(
        self, observation: dict[str, Any], legal: list[dict[str, Any]],
        on_stream: StreamSink | None = None,
    ) -> tuple[str, dict[str, Any]]:
        system, user = _prompt(observation, legal)
        url, headers, body = self.request_parts(system, user)
        url, body = self.stream_request(url, body)
        request = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers={
                "Content-Type": "application/json", "Accept": "text/event-stream", **headers,
            }, method="POST"
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content_type = response.headers.get_content_type()
                if content_type == "text/event-stream":
                    raw, usage, actual_model = self._stream_response(response, on_stream)
                else:
                    payload = json.loads(response.read())
                    raw, usage, actual_model = self.response_parts(payload)
                    if on_stream and raw:
                        on_stream("content", raw)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:1000].replace(self.api_key, "[REDACTED]")
            raise AgentError(f"{self.backend} endpoint returned HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError) as error:
            raise AgentError(f"{self.backend} endpoint failed: {error}") from error
        try:
            selected = _extract_json(raw)["action_id"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise AgentError(f"unexpected {self.backend} response: {raw[:1000]}") from error
        if selected not in {item["id"] for item in legal}:
            raise AgentError(f"model selected unknown or stale action ID: {selected}")
        return selected, {
            "backend": self.backend, "usage": usage, "model": actual_model,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
        }


class OpenAICompatibleAgent(HTTPModelAgent):
    backend = "openai"

    def __init__(self, *, model: str, base_url: str = "https://api.openai.com/v1", api_key: str | None = None,
                 api_key_env: str = "OPENAI_API_KEY", timeout: float = 600):
        super().__init__(model=model, base_url=base_url, api_key_env=api_key_env, api_key=api_key, timeout=timeout)

    def request_parts(self, system: str, user: str) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = self.base_url if self.base_url.endswith("/chat/completions") else self.base_url + "/chat/completions"
        return url, {"Authorization": f"Bearer {self.api_key}"}, {
            "model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }

    def stream_request(self, url: str, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        body["stream"] = True
        return url, body

    def stream_parts(self, payload: dict[str, Any]) -> tuple[str, str, dict[str, Any], str | None]:
        choices = payload.get("choices") or []
        delta = choices[0].get("delta", {}) if choices else {}
        content = delta.get("content") or ""
        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
        tool_calls = delta.get("tool_calls") or []
        if tool_calls:
            content += "".join(call.get("function", {}).get("arguments", "") for call in tool_calls)
        return content, reasoning, payload.get("usage") or {}, payload.get("model")

    def response_parts(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        message = payload["choices"][0]["message"]
        raw = message["tool_calls"][0]["function"]["arguments"] if message.get("tool_calls") else message["content"]
        return raw, payload.get("usage", {}), payload.get("model", self.model)


class AnthropicAgent(HTTPModelAgent):
    backend = "anthropic"

    def __init__(self, *, model: str, base_url: str, api_key_env: str, api_key: str | None = None,
                 timeout: float = 600):
        super().__init__(model=model, base_url=base_url, api_key_env=api_key_env, api_key=api_key, timeout=timeout)

    def request_parts(self, system: str, user: str) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = self.base_url if self.base_url.endswith("/v1/messages") else self.base_url + "/v1/messages"
        return url, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, {
            "model": self.model, "max_tokens": 128, "system": system,
            "messages": [{"role": "user", "content": user}],
        }

    def stream_parts(self, payload: dict[str, Any]) -> tuple[str, str, dict[str, Any], str | None]:
        event_type = payload.get("type")
        delta = payload.get("delta") or {}
        content = delta.get("text", "") if delta.get("type") == "text_delta" else ""
        reasoning = delta.get("thinking", "") if delta.get("type") == "thinking_delta" else ""
        message = payload.get("message") or {}
        usage = payload.get("usage") or message.get("usage") or delta.get("usage") or {}
        return content, reasoning, usage, message.get("model") if event_type == "message_start" else None

    def response_parts(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        text = "".join(block.get("text", "") for block in payload["content"] if block.get("type") == "text")
        return text, payload.get("usage", {}), payload.get("model", self.model)


class GeminiAgent(HTTPModelAgent):
    backend = "gemini"

    def __init__(self, *, model: str, base_url: str, api_key_env: str, api_key: str | None = None,
                 timeout: float = 600):
        super().__init__(model=model, base_url=base_url, api_key_env=api_key_env, api_key=api_key, timeout=timeout)

    def request_parts(self, system: str, user: str) -> tuple[str, dict[str, str], dict[str, Any]]:
        if self.base_url.endswith(":generateContent"):
            url = self.base_url
        else:
            model = urllib.parse.quote(self.model, safe="-_.")
            url = f"{self.base_url}/models/{model}:generateContent"
        return url, {"x-goog-api-key": self.api_key}, {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 128},
        }

    def stream_request(self, url: str, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if url.endswith(":generateContent"):
            url = url[:-len(":generateContent")] + ":streamGenerateContent?alt=sse"
        elif not url.endswith(":streamGenerateContent?alt=sse"):
            url = url + ("&" if "?" in url else "?") + "alt=sse"
        return url, body

    def stream_parts(self, payload: dict[str, Any]) -> tuple[str, str, dict[str, Any], str | None]:
        parts = ((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        content = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        reasoning = "".join(part.get("text", "") for part in parts if part.get("thought"))
        return content, reasoning, payload.get("usageMetadata") or {}, payload.get("modelVersion")

    def response_parts(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts), payload.get("usageMetadata", {}), self.model


def build_model_agent(config: PlayerConfig) -> ModelAgent:
    classes = {"openai": OpenAICompatibleAgent, "anthropic": AnthropicAgent, "gemini": GeminiAgent}
    if config.backend not in classes or not config.model or not config.base_url or not config.api_key_env:
        raise AgentError(f"player {config.name} is not a configured model controller")
    return classes[config.backend](
        model=config.model, base_url=config.base_url,
        api_key_env=config.api_key_env, api_key=config.api_key,
    )
