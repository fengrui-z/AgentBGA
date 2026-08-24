import unittest
from types import SimpleNamespace

from agentbga.usage import (
    TokenUsageAccumulator,
    build_harness_metrics,
    harness_usage_samples,
    normalize_token_usage,
)


class UsageTests(unittest.TestCase):
    def test_normalizes_codex_and_anthropic_cache_semantics(self):
        codex = normalize_token_usage({
            "input_tokens": 100,
            "cached_input_tokens": 80,
            "output_tokens": 25,
            "reasoning_output_tokens": 10,
        }, source="codex")
        anthropic = normalize_token_usage({
            "input_tokens": 20,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 5,
            "output_tokens": 25,
        }, source="claude")

        self.assertEqual(100, codex.input_tokens)
        self.assertEqual(80, codex.cached_input_tokens)
        self.assertEqual(105, anthropic.input_tokens)
        self.assertEqual(80, anthropic.cached_input_tokens)
        self.assertEqual(5, anthropic.cache_write_input_tokens)

    def test_extracts_only_non_overlapping_harness_events(self):
        codex = harness_usage_samples("codex", {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {"last_token_usage": {
                    "input_tokens": 90, "cached_input_tokens": 60,
                    "output_tokens": 12, "reasoning_output_tokens": 4,
                }},
            },
        })
        compacted = harness_usage_samples("codex", {
            "type": "event_msg",
            "payload": {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 0, "output_tokens": 0},
            }},
        })
        claude_partial = harness_usage_samples("claude", {
            "type": "assistant", "usage": {"input_tokens": 100, "output_tokens": 10},
        })
        qwen_partial = harness_usage_samples("qwen", {
            "type": "assistant", "message": {
                "usage": {"input_tokens": 100, "output_tokens": 10},
            },
        })
        qwen_result = harness_usage_samples("qwen", {
            "type": "result", "usage": {
                "input_tokens": 100, "cache_read_input_tokens": 60,
                "output_tokens": 10, "total_tokens": 130,
            },
        })

        self.assertEqual(1, len(codex))
        self.assertEqual(90, codex[0].input_tokens)
        self.assertEqual([], compacted)
        self.assertEqual([], claude_partial)
        self.assertEqual([], qwen_partial)
        self.assertEqual(1, len(qwen_result))
        self.assertEqual(100, qwen_result[0].input_tokens)
        self.assertEqual(60, qwen_result[0].cached_input_tokens)
        self.assertEqual(30, qwen_result[0].output_tokens)
        self.assertEqual(20, qwen_result[0].reasoning_output_tokens)

    def test_normalizes_pi_direct_cache_fields(self):
        pi = normalize_token_usage({
            "input": 20, "cacheRead": 80, "cacheWrite": 5, "output": 12,
        }, source="pi.message_end")

        self.assertEqual(105, pi.input_tokens)
        self.assertEqual(80, pi.cached_input_tokens)
        self.assertEqual(5, pi.cache_write_input_tokens)

    def test_opencode_reasoning_is_a_disjoint_output_field(self):
        opencode = normalize_token_usage({
            "input": 813, "output": 218, "reasoning": 392,
            "cache": {"read": 101504, "write": 0},
        }, source="opencode.step_finish")

        self.assertEqual(102317, opencode.input_tokens)
        self.assertEqual(610, opencode.output_tokens)
        self.assertEqual(392, opencode.reasoning_output_tokens)

    def test_gemini_thoughts_are_a_disjoint_output_field(self):
        gemini = normalize_token_usage({
            "promptTokenCount": 100, "cachedContentTokenCount": 60,
            "candidatesTokenCount": 15, "thoughtsTokenCount": 25,
            "totalTokenCount": 140,
        }, source="gemini.usage_metadata")

        self.assertEqual(40, gemini.output_tokens)
        self.assertEqual(25, gemini.reasoning_output_tokens)

    def test_builds_per_player_and_match_totals(self):
        codex_usage = TokenUsageAccumulator()
        codex_usage.add_raw({
            "input_tokens": 100, "cached_input_tokens": 70, "output_tokens": 20,
        }, source="codex.token_count")
        dsh_usage = TokenUsageAccumulator()
        dsh_usage.add_raw({
            "inputTokens": 30, "cacheReadTokens": 20, "outputTokens": 10,
            "reasoningTokens": 6,
        }, source="dsh.assistant_message")
        configs = [
            SimpleNamespace(backend="codex", model="gpt-test"),
            SimpleNamespace(backend="dsh", model="deepseek-test"),
            SimpleNamespace(backend="random", model=None),
        ]
        agents = {
            0: SimpleNamespace(usage_summary=codex_usage.summary),
            1: SimpleNamespace(usage_summary=dsh_usage.summary),
        }
        calls = [
            {"seat": 0, "metadata": {
                "process_latency_ms": 100, "action_latency_ms": 80,
                "session_resumed": True, "compaction_events": [{"type": "compaction"}],
            }},
            {"seat": 0, "metadata": {
                "process_latency_ms": 200, "action_latency_ms": 150,
                "fallback": "random",
            }},
            {"seat": 1, "metadata": {"latency_ms": 50}},
        ]
        events = [{"seat": 1, "event": {"type": "harness_error"}}]

        result = build_harness_metrics(
            configs, agents, calls, events, frozenset({"codex", "dsh"}),
            {1: 2},
        )

        self.assertEqual("agentbga.harness-metrics.v1", result["schema_version"])
        self.assertEqual(2, len(result["players"]))
        self.assertEqual(2, result["players"][0]["controller_calls"])
        self.assertEqual(1, result["players"][0]["fallbacks"])
        self.assertEqual(1, result["players"][0]["session_resumes"])
        self.assertEqual(1, result["players"][0]["compactions"])
        self.assertEqual(150, result["players"][0]["latency_ms"]["process"]["average"])
        self.assertEqual(2, result["players"][1]["errors"])
        self.assertEqual(150, result["totals"]["input_tokens"])
        self.assertEqual(90, result["totals"]["cached_input_tokens"])
        self.assertEqual(30, result["totals"]["output_tokens"])
        self.assertEqual(0.6, result["totals"]["cache_hit_rate"])
        self.assertTrue(result["totals"]["complete"])


if __name__ == "__main__":
    unittest.main()
