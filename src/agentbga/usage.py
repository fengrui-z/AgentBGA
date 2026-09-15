"""Normalize and aggregate token usage reported by model harnesses."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


def _count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return 0


@dataclass(frozen=True)
class TokenUsageSample:
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    source: str


def normalize_token_usage(raw: Any, *, source: str) -> TokenUsageSample | None:
    """Convert common provider usage shapes to one non-overlapping token model.

    ``input_tokens`` always includes cache reads and cache writes. Reasoning is
    reported separately as a subset of output and is never added to totals twice.
    """
    if not isinstance(raw, dict):
        return None

    # OpenCode step-finish and similar agent runtimes.
    if any(key in raw for key in ("input", "output", "reasoning", "cache")):
        cache = raw.get("cache") if isinstance(raw.get("cache"), dict) else {}
        uncached = _count(raw.get("input"))
        cached = _count(cache.get("read")) or _count(raw.get("cacheRead"))
        cache_write = _count(cache.get("write")) or _count(raw.get("cacheWrite"))
        output = _count(raw.get("output"))
        reasoning = _count(raw.get("reasoning"))
        if source.split(".", 1)[0] == "opencode":
            # OpenCode reports visible output and reasoning as disjoint fields.
            output += reasoning
        else:
            reasoning = min(output, reasoning)
        if not any((uncached, cached, cache_write, output)):
            return None
        return TokenUsageSample(
            uncached + cached + cache_write, cached, cache_write,
            output, reasoning, source,
        )

    # DSh, Pi, and other camelCase agent runtimes report cache reads outside
    # inputTokens.
    if any(key in raw for key in (
        "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens",
    )):
        uncached = _count(raw.get("inputTokens"))
        cached = _count(raw.get("cacheReadTokens"))
        cache_write = _count(raw.get("cacheWriteTokens"))
        output = _count(raw.get("outputTokens"))
        reasoning = min(output, _count(raw.get("reasoningTokens")))
        if not any((uncached, cached, cache_write, output)):
            return None
        return TokenUsageSample(
            uncached + cached + cache_write, cached, cache_write,
            output, reasoning, source,
        )

    # Gemini usageMetadata. promptTokenCount already includes cached content.
    if any(key in raw for key in (
        "promptTokenCount", "candidatesTokenCount", "totalTokenCount",
    )):
        input_tokens = _count(raw.get("promptTokenCount"))
        cached = min(input_tokens, _count(raw.get("cachedContentTokenCount")))
        output = _count(raw.get("candidatesTokenCount"))
        reasoning = _count(raw.get("thoughtsTokenCount"))
        output += reasoning
        if not any((input_tokens, output)):
            return None
        return TokenUsageSample(input_tokens, cached, 0, output, reasoning, source)

    # OpenAI chat-completions usage.
    if any(key in raw for key in ("prompt_tokens", "completion_tokens")):
        prompt_details = raw.get("prompt_tokens_details")
        completion_details = raw.get("completion_tokens_details")
        if not isinstance(prompt_details, dict):
            prompt_details = {}
        if not isinstance(completion_details, dict):
            completion_details = {}
        input_tokens = _count(raw.get("prompt_tokens"))
        cached = min(input_tokens, _count(prompt_details.get("cached_tokens")))
        output = _count(raw.get("completion_tokens"))
        reasoning = min(output, _count(completion_details.get("reasoning_tokens")))
        if not any((input_tokens, output)):
            return None
        return TokenUsageSample(input_tokens, cached, 0, output, reasoning, source)

    # Anthropic and Grok Build separate cache reads/creation from ordinary
    # input. Codex and Responses-style APIs include cached input inside
    # input_tokens instead.
    if any(key in raw for key in ("input_tokens", "output_tokens")):
        ordinary_input = _count(raw.get("input_tokens"))
        cache_read = _count(raw.get("cache_read_input_tokens"))
        cache_write = _count(raw.get("cache_creation_input_tokens"))
        if (cache_read or cache_write) and source.split(".", 1)[0] in {"claude", "grok"}:
            input_tokens = ordinary_input + cache_read + cache_write
            cached = cache_read
        else:
            input_tokens = ordinary_input
            cached = min(
                input_tokens,
                _count(raw.get("cached_input_tokens")) or cache_read,
            )
            cache_write = min(
                input_tokens,
                _count(raw.get("cache_write_input_tokens")) or cache_write,
            )
        output = _count(raw.get("output_tokens"))
        reasoning = min(
            output,
            _count(raw.get("reasoning_output_tokens")) or _count(raw.get("reasoning_tokens")),
        )
        if source.split(".", 1)[0] == "qwen":
            # Qwen's aggregate total includes thinking tokens while
            # output_tokens contains candidates only.
            reasoning = max(0, _count(raw.get("total_tokens")) - input_tokens - output)
            output += reasoning
        output_details = raw.get("output_tokens_details")
        if isinstance(output_details, dict):
            reasoning = min(output, _count(output_details.get("reasoning_tokens")))
        if not any((input_tokens, output)):
            return None
        return TokenUsageSample(
            input_tokens, cached, cache_write, output, reasoning, source,
        )
    return None


def harness_usage_samples(backend: str, payload: Any) -> list[TokenUsageSample]:
    """Extract non-duplicated usage samples from one harness JSON event."""
    if not isinstance(payload, dict):
        return []
    event_type = str(payload.get("type") or "")
    candidates: list[tuple[Any, str]] = []

    if backend == "codex":
        inner = payload.get("payload")
        if event_type == "event_msg" and isinstance(inner, dict) and inner.get("type") == "token_count":
            info = inner.get("info")
            if isinstance(info, dict):
                candidates.append((info.get("last_token_usage"), "codex.token_count"))
    elif backend == "claude":
        # Claude Code's result event contains the invocation aggregate; partial
        # message events contain overlapping usage and must not be counted too.
        if event_type == "result":
            candidates.append((payload.get("usage"), "claude.result"))
    elif backend == "opencode":
        part = payload.get("part") if isinstance(payload.get("part"), dict) else payload
        part_type = str(part.get("type") or event_type).replace("_", "-")
        if part_type in {"step-finish", "step-finished"}:
            candidates.append((part.get("tokens") or part.get("usage"), "opencode.step_finish"))
    elif backend == "pi":
        if event_type.replace("_", "-") in {"message-end", "assistant-message"}:
            message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
            candidates.append((message.get("usage") or payload.get("usage"), "pi.message_end"))
    elif backend == "qwen":
        # Assistant frames contain per-response usage, while the final result
        # contains the non-interactive run aggregate. Count only the latter.
        if event_type == "result":
            candidates.append((payload.get("usage"), "qwen.result"))
    elif backend == "cursor":
        if event_type == "result":
            candidates.append((payload.get("usage"), "cursor.result"))
    elif backend == "grok":
        if event_type in {"end", "error"}:
            candidates.append((payload.get("usage"), f"grok.{event_type}"))

    result = []
    for raw, source in candidates:
        sample = normalize_token_usage(raw, source=source)
        if sample is not None:
            result.append(sample)
    return result


@dataclass
class TokenUsageAccumulator:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    usage_records: int = 0
    sources: set[str] = field(default_factory=set)

    def add(self, sample: TokenUsageSample | None, *, records: int = 1) -> None:
        if sample is None:
            return
        self.input_tokens += sample.input_tokens
        self.cached_input_tokens += sample.cached_input_tokens
        self.cache_write_input_tokens += sample.cache_write_input_tokens
        self.output_tokens += sample.output_tokens
        self.reasoning_output_tokens += sample.reasoning_output_tokens
        self.usage_records += max(1, records)
        self.sources.add(sample.source)

    def add_raw(self, raw: Any, *, source: str) -> None:
        self.add(normalize_token_usage(raw, source=source))

    def replace(self, sample: TokenUsageSample | None, *, records: int = 1) -> None:
        """Replace the accumulator with one authoritative cumulative snapshot."""
        self.input_tokens = 0
        self.cached_input_tokens = 0
        self.cache_write_input_tokens = 0
        self.output_tokens = 0
        self.reasoning_output_tokens = 0
        self.usage_records = 0
        self.sources.clear()
        self.add(sample, records=records)

    def summary(self) -> dict[str, Any]:
        if self.usage_records == 0:
            return {
                "available": False,
                "usage_records": 0,
                "sources": [],
            }
        uncached = max(0, self.input_tokens - self.cached_input_tokens)
        return {
            "available": True,
            "usage_records": self.usage_records,
            "sources": sorted(self.sources),
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "cache_write_input_tokens": self.cache_write_input_tokens,
            "uncached_input_tokens": uncached,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cache_hit_rate": round(
                self.cached_input_tokens / self.input_tokens, 6,
            ) if self.input_tokens else None,
        }


def _latency_stats(values: list[float]) -> dict[str, int | float]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "total": 0, "average": 0, "p95": 0, "max": 0}
    total = round(sum(ordered), 3)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return {
        "count": len(ordered),
        "total": total,
        "average": round(total / len(ordered), 3),
        "p95": round(p95, 3),
        "max": round(ordered[-1], 3),
    }


def build_harness_metrics(
    configs: list[Any],
    agents: dict[int, Any],
    controller_calls: list[dict[str, Any]],
    harness_events: list[dict[str, Any]],
    harness_backends: set[str] | frozenset[str],
    attempt_errors: dict[int, int] | None = None,
) -> dict[str, Any]:
    """Build the stable per-match harness usage summary stored in results."""
    calls_by_seat: dict[int, list[dict[str, Any]]] = {}
    for call in controller_calls:
        calls_by_seat.setdefault(int(call["seat"]), []).append(call)
    errors_by_seat: dict[int, int] = {}
    for row in harness_events:
        event = row.get("event")
        if isinstance(event, dict) and event.get("type") == "harness_error":
            seat = int(row["seat"])
            errors_by_seat[seat] = errors_by_seat.get(seat, 0) + 1

    players: list[dict[str, Any]] = []
    for seat, config in enumerate(configs):
        if config.backend not in harness_backends:
            continue
        calls = calls_by_seat.get(seat, [])
        metadata = [
            call.get("metadata", {}) for call in calls
            if isinstance(call.get("metadata"), dict)
        ]
        process_latencies = [
            float(value) for item in metadata
            if isinstance((value := item.get("process_latency_ms", item.get("latency_ms"))), (int, float))
            and not isinstance(value, bool) and value >= 0
        ]
        action_latencies = [
            float(value) for item in metadata
            if isinstance((value := item.get("action_latency_ms")), (int, float))
            and not isinstance(value, bool) and value >= 0
        ]
        agent = agents.get(seat)
        usage = (
            agent.usage_summary()
            if agent is not None and callable(getattr(agent, "usage_summary", None))
            else TokenUsageAccumulator().summary()
        )
        players.append({
            "seat": seat,
            "backend": config.backend,
            "model": config.model,
            "controller_calls": len(calls),
            "errors": max(
                errors_by_seat.get(seat, 0),
                (attempt_errors or {}).get(seat, 0),
            ),
            "fallbacks": sum(bool(item.get("fallback")) for item in metadata),
            "session_resumes": sum(item.get("session_resumed") is True for item in metadata),
            "compactions": sum(
                len(item.get("compaction_events", []))
                for item in metadata if isinstance(item.get("compaction_events"), list)
            ),
            "token_usage": usage,
            "latency_ms": {
                "process": _latency_stats(process_latencies),
                "action": _latency_stats(action_latencies),
            },
        })

    token_fields = (
        "usage_records", "input_tokens", "cached_input_tokens",
        "cache_write_input_tokens", "uncached_input_tokens", "output_tokens",
        "reasoning_output_tokens", "total_tokens",
    )
    reported = [player["token_usage"] for player in players if player["token_usage"]["available"]]
    totals: dict[str, Any] = {
        "players": len(players),
        "players_reporting_tokens": len(reported),
        "complete": len(reported) == len(players),
    }
    for field_name in token_fields:
        totals[field_name] = sum(int(usage.get(field_name, 0)) for usage in reported)
    totals["cache_hit_rate"] = (
        round(totals["cached_input_tokens"] / totals["input_tokens"], 6)
        if totals["input_tokens"] else None
    )
    return {
        "schema_version": "agentbga.harness-metrics.v1",
        "players": players,
        "totals": totals,
    }
