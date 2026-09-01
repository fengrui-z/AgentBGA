"""Minimal pure-Python game harness: direct LLM API + in-process tools.

No external CLI, no MCP server, no Node.js. The LLM communicates via
OpenAI-compatible function calling; seat tools (compact observation, paged
legal actions, on-demand details, submission, and notes) are implemented as Python methods
that read/write the same seat-context files as the MCP-based harnesses.

This is the most controlled harness: zero infrastructure overhead, zero
harness-specific system prompt, zero ambient tools. The only variable is
the LLM's own reasoning + the identical seat-tool interface every other
harness also sees.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
import time
from typing import Any, Callable

from .agent_context import prepare_seat_context
from .agents import AgentError, PlayerConfig, StreamSink
from .seat_tool import call_tool as _seat_call_tool
from .harness_features import HarnessFeatures
from .game_profile import GameProfile, detect_phase, group_actions, get_profile
from .memory import memory_identity, stable_session_id


MINIMAL_SYSTEM = (
    "You are a board-game player in an AgentBGA benchmark. "
    "Call observe to see the board, legal_actions to see your options, "
    "use inspect_card, inspect_rules, inspect_map, inspect_played_cards, or inspect_history when details matter, "
    "and never guess a game rule that inspect_rules or inspect_card can answer. "
    "read_notes to check your strategy notes, write_notes to update them, "
    "then submit_action with exactly one legal action ID. "
    "You have no other tools. You cannot read files or run code. "
    "After submitting, briefly report your reasoning."
)

MINIMAL_TOOLS = [
    {"type": "function", "function": {
        "name": "observe",
        "description": "Read your seat-scoped current board-game observation.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "legal_actions",
        "description": "List legal actions. Large action spaces return groups that can be paged.",
        "parameters": {"type": "object", "properties": {
            "group": {"type": "string"},
            "cursor": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "inspect_card",
        "description": "Read complete details for one visible card. Accepts detail_ref (card:zoo-421) or bare visible id (zoo-421).",
        "parameters": {"type": "object", "properties": {
            "card_ref": {"type": "string"},
        }, "required": ["card_ref"], "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "inspect_rules",
        "description": "Read an engine-aligned Ark Nova rules topic. Call without topic to list topics; use instead of guessing action, building, income, reward, or keyword rules.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string"},
        }, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "inspect_map",
        "description": "Read a public player map, optionally selecting sections.",
        "parameters": {"type": "object", "properties": {
            "seat": {"type": "integer", "minimum": 0},
            "sections": {"type": "array", "items": {
                "enum": ["terrain", "buildings", "rewards", "player_board"]
            }, "uniqueItems": True},
        }, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "inspect_played_cards",
        "description": "List public played cards for one seat.",
        "parameters": {"type": "object", "properties": {
            "seat": {"type": "integer", "minimum": 0},
            "kind": {"type": "string"},
            "cursor": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "inspect_history",
        "description": "Read seat-safe changes accumulated across observations.",
        "parameters": {"type": "object", "properties": {
            "since_version": {"type": "integer", "minimum": 0},
            "cursor": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "submit_action",
        "description": "Commit exactly one legal action ID for this decision step.",
        "parameters": {
            "type": "object",
            "properties": {"action_id": {"type": "string"}},
            "required": ["action_id"],
            "additionalProperties": False,
        },
    }},
    {"type": "function", "function": {
        "name": "read_notes",
        "description": "Read your persistent strategy notes (survives across turns).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "write_notes",
        "description": "Replace your strategy notes with new content (survives across turns).",
        "parameters": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
            "additionalProperties": False,
        },
    }},
]


def _approx_tokens(text: str) -> int:
    return len(text) // 4 + 1


class DirectGameAgent:
    """Minimal harness: direct LLM API calls + in-process tool execution.

    Implements the same ModelAgent protocol (choose) as HarnessAgent, but
    runs entirely in Python — no subprocess, no MCP, no external CLI.

    Session persistence: conversation history is saved to a JSON file in
    the seat workspace and loaded on the next turn, providing cross-turn
    memory comparable to opencode's --session or codex's exec resume.

    Context compaction: when the conversation exceeds max_context_tokens,
    old turns (except the most recent keep_recent turns) are summarised
    into a compact digest so the LLM retains strategic context without
    overflowing its window.
    """

    backend = "minimal"

    def __init__(self, config: PlayerConfig, match_id: str, seat: int, *,
                 timeout: float = 600,
                 keep_recent: int = 10, runs_root: str | Path | None = None,
                 features: HarnessFeatures | None = None,
                 game_id: str | None = None,
                 event_sink: Callable[[dict[str, Any]], None] | None = None):
        self.config = config
        self.match_id = match_id
        self.seat = seat
        self.timeout = timeout
        self.keep_recent = keep_recent
        self.game_id = game_id
        self.event_sink = event_sink
        self.features = features or HarnessFeatures.baseline()
        self.profile: GameProfile | None = get_profile(game_id) if game_id else None
        self._prev_observation: dict[str, Any] | None = None
        self._journal: list[dict[str, Any]] = []
        root = Path(runs_root) if runs_root else Path.cwd() / ".agentbga" / "runs"
        identity = memory_identity(root, config, match_id, seat)
        self.workspace = identity.workspace
        self.runtime = root / "_runtime" / match_id / f"seat-{seat}"
        self.trace_dir = root / "_traces" / match_id / f"seat-{seat}"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.session_path = self.workspace / "session.json"
        self.notes_path = self.workspace / "strategy-notes.md"
        self.session_id = stable_session_id(identity)
        self.session_scope = identity.scope
        self.session_scope_id = identity.scope_id
        self.participant_id = identity.participant_id
        self._messages: list[dict[str, Any]] = []
        self._trace_steps: list[dict[str, Any]] = []
        self._load_session()

    # ── session persistence ──

    def _load_session(self) -> None:
        if self.session_path.exists():
            try:
                data = json.loads(self.session_path.read_text(encoding="utf-8"))
                self._messages = data.get("messages", [])
            except (json.JSONDecodeError, OSError):
                self._messages = []

    def _save_session(self) -> None:
        self.session_path.write_text(
            json.dumps({"messages": self._messages}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    # ── context compaction ──

    def _maybe_compact(self) -> None:
        """Compact history before it can exceed the provider's input window.

        Semantic compaction remains an optional cognitive feature.  The larger
        baseline threshold is a transport-safety limit: it preserves recent
        messages and a factual digest instead of allowing a long match to fail
        because the provider rejects the request body.
        """
        # Accurate token estimate: include content + reasoning_content + tool_calls
        total = 0
        for m in self._messages:
            total += _approx_tokens(m.get("content", "") or "")
            total += _approx_tokens(m.get("reasoning_content", "") or "")
            for tc in m.get("tool_calls", []):
                total += _approx_tokens(tc.get("function", {}).get("arguments", ""))
        threshold = 60000 if self.features.semantic_compaction else (
            80000 if self.game_id == "ark_nova" else 120000
        )
        if total <= threshold:
            return
        keep = max(self.keep_recent * 6, 12)
        if len(self._messages) <= keep:
            return
        recent_start = max(0, len(self._messages) - keep)
        while recent_start > 0:
            message = self._messages[recent_start]
            content = message.get("content", "")
            if (
                message.get("role") == "user"
                and isinstance(content, str)
                and content.startswith("You are seat ")
            ):
                break
            recent_start -= 1
        old = self._messages[:recent_start]
        if not old:
            return
        compacted = self._summarize_turns(old)
        self._messages = [
            {"role": "system", "content": compacted},
            *self._messages[recent_start:],
        ]

    def _emit(self, event_type: str, **payload: Any) -> None:
        if self.event_sink:
            self.event_sink({
                "type": event_type, "harness": "minimal", "seat": self.seat,
                "player": self.config.name, **payload,
            })

    def _summarize_turns(self, old_messages: list[dict]) -> str:
        """Build a compact digest of old conversation turns using game journal."""
        # If we have a structured journal, use it for semantic compression
        if self._journal:
            return self._journal_summary(last_n=50)
        # Fallback: generic conversation digest
        lines = ["=== Previous turns digest ==="]
        turn = 0
        for msg in old_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and isinstance(content, str) and "state version" in content.lower():
                turn += 1
                lines.append(f"\n[Turn {turn}]")
            elif role == "tool" and isinstance(content, str):
                if "action_id" in content:
                    lines.append(f"  submitted: {content[:120]}")
            elif role == "assistant" and isinstance(content, str) and content:
                snippet = content[:200].replace("\n", " ")
                lines.append(f"  thought: {snippet}")
        lines.append(f"\n({len(old_messages)} messages compressed)")
        return "\n".join(lines)

    # ── user message builder (feature-flag aware) ──

    def _build_user_message(self, observation: dict, legal: list, version: Any) -> str:
        """Build the user message, enriched by enabled features."""
        game_name = observation.get("game", "board-game")
        parts = [
            f"You are seat {self.seat} in an AgentBGA {game_name} match at state version {version}.",
            "Call observe, legal_actions, then submit_action.",
        ]

        if self.profile:
            score = 0
            players = observation.get("players", [])
            if self.seat < len(players):
                score = players[self.seat].get("score", 0)
            turn = observation.get("turn_count", 0)
            phase = detect_phase(turn, score, self.profile)

            # Inject strategy notes (plan tracking)
            notes_path = self.notes_path
            if self.features.plan_tracking and notes_path.exists():
                notes = notes_path.read_text(encoding="utf-8")
                if notes.strip():
                    parts.append(f"\n## Your current plan & notes:\n{notes}")

            if self.features.phase_cot:
                strategy = {
                    "early": self.profile.early_strategy,
                    "mid": self.profile.mid_strategy,
                    "late": self.profile.late_strategy,
                }.get(phase, "")
                parts.append(f"\n## Current phase: {phase} (turn {turn}/{self.profile.total_expected_turns})")
                parts.append(f"## Phase strategy: {strategy}")

            if self.features.state_diff and self._prev_observation:
                diff = self._real_state_diff(self._prev_observation, observation)
                if diff.strip():
                    parts.append(f"\n## Changes since your last turn:\n{diff}")

            if self.features.game_journal and self._journal:
                parts.append(f"\n## Game journal:\n{self._journal_summary()}")

            if self.features.action_grouping:
                grouped_text = self._format_legal_actions(legal, observation)
                parts.append(f"\n{grouped_text}")

            if self.features.counterfactual:
                parts.append(
                    "\n## Before submitting, consider:"
                    "\n- If you DON'T take this action, will the opponent benefit?"
                    "\n- What's the opportunity cost vs the best alternative?"
                )

            if self.features.pre_commitment:
                parts.append(
                    "\n## Process: call write_notes with your plan first, "
                    "then observe, legal_actions, then submit_action."
                )

            if self.features.attention_guidance:
                parts.append(
                    "\n★ Focus on actions you can execute NOW (buy/claim), "
                    "then setup actions, then defensive actions."
                )

        return " ".join(parts)

    # ── information processing pipeline ──
    # These methods transform raw game JSON into LLM-friendly structured text.
    # They are the core of what makes the harness more than "LLM + raw tools".

    def _format_observation(self, observation: dict) -> str:
        """Transform raw observation JSON into structured, LLM-readable text.

        Instead of dumping 3KB of raw JSON, this produces ~500 bytes of
        prioritized text that highlights: what you can buy now, what nobles
        you're close to, and your engine progress.
        """
        game = observation.get("game", "board-game")
        if game != "splendor":
            # For non-Splendor games, return a compact JSON (future: per-game formatters)
            return json.dumps(observation, ensure_ascii=False, separators=(",", ":"))[:4000]

        players = observation.get("players", [])
        my = players[self.seat] if self.seat < len(players) else {}
        opp = players[1 - self.seat] if len(players) > 1 else {}
        tokens = my.get("tokens", {})
        bonuses = my.get("bonuses", {})
        bank = observation.get("bank", {})
        market = observation.get("market", {})
        nobles = observation.get("available_nobles", [])
        turn = observation.get("turn_count", 0)
        my_score = my.get("score", 0)
        opp_score = opp.get("score", 0)

        lines = []
        lines.append(f"=== Turn {turn} | You: {my_score}pts | Opponent: {opp_score}pts ===")

        # My resources
        # Use the canonical color names shown in legal actions and raw observations.
        # Initials are ambiguous for Splendor because both blue and black start with B.
        token_str = " ".join(f"{color}:{count}" for color, count in sorted(tokens.items()) if count)
        bonus_str = " ".join(f"{color}={count}" for color, count in sorted(bonuses.items()) if count)
        lines.append(f"Tokens: {token_str or 'none'}")
        lines.append(f"Bonuses: {bonus_str or 'none'} ({my.get('purchased_count', 0)} cards)")

        # Opponent summary (visible only)
        opp_bonus_str = " ".join(
            f"{color}={count}"
            for color, count in sorted(opp.get("bonuses", {}).items())
            if count
        )
        lines.append(f"Opponent: {opp.get('purchased_count', 0)} cards (bonuses: {opp_bonus_str or 'none'})")

        # What can I buy right now?
        affordable = []
        for tier in ("1", "2", "3"):
            for card in market.get(tier, []):
                cost = card.get("cost", {})
                actual = {c: max(0, cost.get(c, 0) - bonuses.get(c, 0)) for c in ("white", "blue", "green", "red", "black")}
                total = sum(actual.values())
                can_pay = True
                remaining_tokens = dict(tokens)
                gold_needed = 0
                for c, amt in actual.items():
                    if remaining_tokens.get(c, 0) >= amt:
                        remaining_tokens[c] -= amt
                    else:
                        deficit = amt - remaining_tokens.get(c, 0)
                        remaining_tokens[c] = 0
                        if remaining_tokens.get("gold", 0) >= deficit:
                            remaining_tokens["gold"] -= deficit
                        else:
                            can_pay = False
                            break
                if can_pay:
                    affordable.append((tier, card, actual, total))

        if affordable:
            lines.append("★ Can buy NOW:")
            for tier, card, actual, total in affordable:
                pts = card.get("points", 0)
                lines.append(f"  {card['id']} (+{card['bonus']}, {pts}pts, cost: {actual})")
        else:
            lines.append("Cannot buy anything yet.")

        # What am I close to buying? (1-2 turns away)
        close = []
        for tier in ("1", "2", "3"):
            for card in market.get(tier, []):
                cost = card.get("cost", {})
                actual = {c: max(0, cost.get(c, 0) - bonuses.get(c, 0)) for c in ("white", "blue", "green", "red", "black")}
                deficit = {c: actual[c] - tokens.get(c, 0) for c in actual if actual[c] > tokens.get(c, 0)}
                total_deficit = sum(deficit.values())
                if 0 < total_deficit <= 3:  # within 1-2 token takes
                    close.append((total_deficit, card, deficit))
        if close:
            close.sort(key=lambda x: x[0])
            lines.append("◆ Close to buying (1-2 turns):")
            for deficit_total, card, deficit in close[:3]:
                lines.append(f"  {card['id']} (+{card['bonus']}, need {deficit})")

        # Noble progress
        for noble in nobles:
            req = noble.get("required", {})
            gaps = {}
            for c, amt in req.items():
                have = bonuses.get(c, 0)
                if amt > 0:
                    gap = max(0, amt - have)
                    if gap > 0:
                        gaps[c] = gap
            if gaps:
                total_gap = sum(gaps.values())
                lines.append(f"Noble {noble['id']} ({noble['points']}pts): need {gaps} ({total_gap} bonus(es) away)")
            else:
                lines.append(f"★ Noble {noble['id']} ({noble['points']}pts): READY — will auto-claim!")

        # Reserved cards
        reserved = my.get("reserved", [])
        if reserved:
            for r in reserved:
                if isinstance(r, dict) and r.get("id"):
                    cost = r.get("cost", {})
                    actual = {c: max(0, cost.get(c, 0) - bonuses.get(c, 0)) for c in cost}
                    lines.append(f"Reserved: {r['id']} (cost after discount: {actual})")
                else:
                    lines.append("Reserved: [hidden card]")

        return "\n".join(lines)

    def _format_legal_actions(self, legal: list, observation: dict) -> str:
        """Group and prioritize legal actions with context evaluation.

        Instead of 20+ flat JSON entries, shows actions grouped by meta-type
        with buy affordability and strategic context.
        """
        game = observation.get("game", "board-game")
        if game != "splendor":
            return json.dumps([{"id": a["id"], **a["action"]} for a in legal], ensure_ascii=False)[:4000]

        players = observation.get("players", [])
        my = players[self.seat] if self.seat < len(players) else {}
        tokens = my.get("tokens", {})
        bonuses = my.get("bonuses", {})
        market = observation.get("market", {})

        groups: dict[str, list[str]] = defaultdict(list)

        for item in legal:
            action = item.get("action", {})
            atype = action.get("type", "")
            aid = item["id"]

            if atype in ("buy_visible", "buy_reserved"):
                card_id = action.get("card_id", "")
                tier = str(action.get("tier", ""))
                source = market.get(tier, [])
                card = next((c for c in source if c.get("id") == card_id), None)
                if not card:
                    card = next((c for c in my.get("reserved", []) if isinstance(c, dict) and c.get("id") == card_id), None)
                if card:
                    cost = card.get("cost", {})
                    actual = {c: max(0, cost.get(c, 0) - bonuses.get(c, 0)) for c in ("white", "blue", "green", "red", "black")}
                    pts = card.get("points", 0)
                    groups["★ Buy"].append(
                        f"  {aid}: buy {card_id} (+{card['bonus']}, {pts}pts, cost: {actual})"
                    )
                else:
                    groups["★ Buy"].append(f"  {aid}: buy {card_id} (details unknown)")

            elif atype == "take_tokens":
                take = action.get("take", {})
                colors = "+".join(f"{c}" for c in sorted(take.keys()))
                groups["◆ Take"].append(f"  {aid}: take {colors}")

            elif atype == "reserve_visible":
                card_id = action.get("card_id", "")
                groups["⚠ Reserve"].append(f"  {aid}: reserve {card_id}")

            elif atype == "reserve_deck":
                tier = action.get("tier", "?")
                groups["⚠ Reserve"].append(f"  {aid}: reserve deck tier {tier}")

            elif atype == "choose_noble":
                groups["★ Score"].append(f"  {aid}: claim noble {action.get('noble_id', '?')}")

            else:
                groups["Other"].append(f"  {aid}: {atype}")

        priority = ["★ Buy", "★ Score", "◆ Take", "⚠ Reserve", "Other"]
        lines = ["=== Legal actions (grouped & prioritized) ==="]
        for meta in priority:
            if meta in groups:
                lines.append(f"[{meta}] ({len(groups[meta])})")
                lines.extend(groups[meta])
        return "\n".join(lines)

    def _journal_entry(self, turn: int, action: dict, obs_before: dict, obs_after: dict) -> dict:
        """Record a structured journal entry for one turn."""
        my_before = obs_before.get("players", [{}])[self.seat] if self.seat < len(obs_before.get("players", [])) else {}
        my_after = obs_after.get("players", [{}])[self.seat] if self.seat < len(obs_after.get("players", [])) else {}
        score_before = my_before.get("score", 0)
        score_after = my_after.get("score", 0)
        meta = self.profile.action_meta_types.get(action.get("type", ""), "other") if self.profile else "other"
        phase = "early"
        if self.profile:
            phase = detect_phase(turn, score_after, self.profile)
        return {
            "turn": turn,
            "action_type": action.get("type", ""),
            "meta": meta,
            "action_detail": self._action_summary(action),
            "score_before": score_before,
            "score_after": score_after,
            "score_delta": score_after - score_before,
            "bonuses_after": dict(my_after.get("bonuses", {})),
            "cards_after": my_after.get("purchased_count", 0),
            "tokens_after": dict(my_after.get("tokens", {})),
            "phase": phase,
        }

    def _action_summary(self, action: dict) -> str:
        """Short human-readable summary of an action."""
        atype = action.get("type", "")
        if atype == "take_tokens":
            take = action.get("take", {})
            return f"take {'+'.join(sorted(take.keys()))}"
        elif atype in ("buy_visible", "buy_reserved"):
            return f"buy {action.get('card_id', '?')}"
        elif atype == "reserve_visible":
            return f"reserve {action.get('card_id', '?')}"
        elif atype == "reserve_deck":
            return f"reserve deck {action.get('tier', '?')}"
        elif atype == "choose_noble":
            return f"claim noble {action.get('noble_id', '?')}"
        return atype

    def _journal_summary(self, last_n: int = 20) -> str:
        """Compress recent journal entries into a brief strategic digest."""
        entries = self._journal[-last_n:] if self._journal else []
        if not entries:
            return "(no history yet)"

        builds = sum(1 for e in entries if e["meta"] == "build")
        takes = sum(1 for e in entries if e["meta"] == "acquire")
        blocks = sum(1 for e in entries if e["meta"] == "block")
        scores = sum(e["score_delta"] for e in entries if e["score_delta"] > 0)
        latest = entries[-1] if entries else {}

        lines = [
            f"=== Last {len(entries)} turns digest ===",
            f"Actions: {builds} builds, {takes} takes, {blocks} blocks",
            f"Score progress: {latest.get('score_before', 0)}→{latest.get('score_after', 0)} (+{scores} scored)",
            f"Engine: {latest.get('cards_after', 0)} cards, bonuses={latest.get('bonuses_after', {})}",
            f"Phase: {latest.get('phase', '?')}",
        ]

        # Recent action sequence
        recent = entries[-5:]
        seq = " → ".join(f"T{e['turn']}:{e['action_detail']}" for e in recent)
        lines.append(f"Recent: {seq}")

        return "\n".join(lines)

    def _real_state_diff(self, prev_obs: dict, curr_obs: dict) -> str:
        """Compute actual changes between two observations."""
        lines = []
        prev_players = prev_obs.get("players", [])
        curr_players = curr_obs.get("players", [])

        for i in range(max(len(prev_players), len(curr_players))):
            ps = prev_players[i] if i < len(prev_players) else {}
            cs = curr_players[i] if i < len(curr_players) else {}

            # Score change
            if ps.get("score", 0) != cs.get("score", 0):
                who = "You" if i == self.seat else "Opponent"
                lines.append(f"  {who}: score {ps.get('score', 0)}→{cs.get('score', 0)}")

            # New purchases
            p_ids = set(c.get("id", "") for c in ps.get("purchased", []))
            c_ids = set(c.get("id", "") for c in cs.get("purchased", []))
            new = c_ids - p_ids
            if new:
                who = "You bought" if i == self.seat else "Opponent bought"
                lines.append(f"  {who}: {', '.join(new)}")

            # New nobles
            p_nobles = set(n.get("id", "") for n in ps.get("nobles", []))
            c_nobles = set(n.get("id", "") for n in cs.get("nobles", []))
            new_nobles = c_nobles - p_nobles
            if new_nobles:
                who = "You claimed" if i == self.seat else "Opponent claimed"
                lines.append(f"  {who}: noble {', '.join(new_nobles)}")

        # Market changes
        prev_market = prev_obs.get("market", {})
        curr_market = curr_obs.get("market", {})
        for tier in curr_market:
            prev_ids = set(c.get("id") for c in prev_market.get(tier, []))
            curr_ids = set(c.get("id") for c in curr_market.get(tier, []))
            gone = prev_ids - curr_ids
            appeared = curr_ids - prev_ids
            if gone:
                lines.append(f"  Market T{tier}: bought → {', '.join(gone)}")
            if appeared:
                lines.append(f"  Market T{tier}: revealed → {', '.join(appeared)}")

        # Bank changes (significant only)
        prev_bank = prev_obs.get("bank", {})
        curr_bank = curr_obs.get("bank", {})
        bank_diff = {c: curr_bank.get(c, 0) - prev_bank.get(c, 0) for c in curr_bank if curr_bank.get(c, 0) != prev_bank.get(c, 0)}
        if bank_diff:
            parts = [f"{c}:{'+' if d > 0 else ''}{d}" for c, d in sorted(bank_diff.items()) if d != 0]
            lines.append(f"  Bank: {', '.join(parts)}")

        return "\n".join(lines) if lines else "  (no significant changes)"

    # ── tool execution ──

    def _execute_tool(self, name: str, arguments: dict, observation: dict | None = None, legal: list | None = None) -> Any:
        """Execute a seat tool. For observe/legal_actions, return formatted text
        (not raw JSON) when the harness has profile + observation context."""
        if (
            name == "observe" and observation is not None and self.profile
            and observation.get("game") == "splendor"
        ):
            return self._format_observation(observation)
        if (
            name == "legal_actions" and legal is not None and self.profile
            and observation is not None and observation.get("game") == "splendor"
        ):
            return self._format_legal_actions(legal, observation or {})
        context_path = self.runtime / "turn-context.json"
        return _seat_call_tool(context_path, name, arguments, notes_root=self.workspace)

    # ── LLM API call (OpenAI-compatible) ──

    def _call_llm(self, on_stream: StreamSink | None = None) -> dict[str, Any]:
        """Call the LLM API with streaming, pushing deltas to on_stream in real time."""
        import ssl
        import urllib.error
        import urllib.request

        api_key = self.config.api_key or os.environ.get(self.config.api_key_env or "")
        if not api_key:
            raise AgentError(f"missing API key; set {self.config.api_key_env}")
        base_url = (self.config.base_url or "").rstrip("/")
        if not base_url.endswith("/chat/completions"):
            url = base_url + "/chat/completions"
        else:
            url = base_url
        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": 16000,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": self._messages,
            "tools": MINIMAL_TOOLS,
            "tool_choice": "auto",
        }
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        model_name = self.config.model
        finish_reason = ""

        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=ctx) as response:
                buffer = b""
                for chunk in iter(lambda: response.read(1024), b""):
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip().decode("utf-8", errors="replace")
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if payload.get("model"):
                            model_name = payload["model"]
                        if payload.get("usage"):
                            usage = payload["usage"]
                        choices = payload.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        if choices[0].get("finish_reason"):
                            finish_reason = choices[0]["finish_reason"]
                        # Content delta
                        text = delta.get("content") or ""
                        if text:
                            content_parts.append(text)
                            if on_stream:
                                on_stream("content", text)
                        # Reasoning delta
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        if reasoning:
                            reasoning_parts.append(reasoning)
                            if on_stream:
                                on_stream("reasoning", reasoning)
                        # Tool call deltas (streaming assembly)
                        for tc_delta in delta.get("tool_calls") or []:
                            idx = tc_delta.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append({"id": "", "type": "function",
                                                    "function": {"name": "", "arguments": ""}})
                            tc = tool_calls[idx]
                            if tc_delta.get("id"):
                                tc["id"] = tc_delta["id"]
                            fn = tc_delta.get("function", {})
                            if fn.get("name"):
                                tc["function"]["name"] = fn["name"]
                            if fn.get("arguments"):
                                tc["function"]["arguments"] += fn["arguments"]
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:500].replace(api_key, "[REDACTED]")
            raise AgentError(f"minimal harness HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise AgentError(f"minimal harness API failed: {error}") from error

        return {
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts),
            "tool_calls": tool_calls,
            "usage": usage,
            "model": model_name,
            "finish_reason": finish_reason,
        }

    # ── trace ──

    def _write_trace(self, *, version: Any, started: float, status: str,
                     action_id: str | None, error: str | None) -> None:
        submission_path = self.runtime / "submission.json"
        submission = None
        if submission_path.is_file():
            try:
                submission = json.loads(submission_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        trace = {
            "schema_version": "agentbga.turn-trace.v1",
            "match_id": self.match_id, "seat": self.seat,
            "player": self.config.name, "backend": "minimal",
            "model": self.config.model,
            "reasoning_effort": self.config.reasoning_effort,
            "version": version, "session_id": self.session_id,
            "session_scope": self.session_scope,
            "session_scope_id": self.session_scope_id,
            "participant_id": self.participant_id,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "status": status, "error": error,
            "prompt": {"system": MINIMAL_SYSTEM, "user": None},
            "steps": list(self._trace_steps),
            "submission": submission,
        }
        target = self.trace_dir / f"turn-{_version_key(version):04d}.json"
        target.write_text(
            json.dumps(trace, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
        )

    # ── main entry: choose ──

    def choose(self, observation: dict[str, Any], legal: list[dict[str, Any]],
               on_stream: StreamSink | None = None) -> tuple[str, dict[str, Any]]:
        version = observation.get("state_version", observation.get("turn_count"))
        started = time.monotonic()
        self._trace_steps = []

        # Write turn-context.json (same as HarnessAgent._prepare_turn does for
        # MCP harnesses — the seat_tool.call_tool reads this file).
        context_path = self.runtime / "turn-context.json"
        submission_path = self.runtime / "submission.json"
        audit_path = self.runtime / "tool-events.jsonl"
        submission_path.unlink(missing_ok=True)
        audit_path.unlink(missing_ok=True)
        prepare_seat_context(
            context_path,
            match_id=self.match_id,
            seat=self.seat,
            version=version,
            observation=observation,
            legal=legal,
        )

        # Build user message (no observation/legal_actions in it — LLM must call tools)
        user_msg = self._build_user_message(observation, legal, version)
        self._messages.append({"role": "user", "content": user_msg})
        self._maybe_compact()

        # Store observation for state-diff on next turn
        self._prev_observation = observation

        action_id: str | None = None
        error: str | None = None
        max_rounds = 20  # safety limit on tool-calling rounds

        try:
            for _ in range(max_rounds):
                response = self._call_llm(on_stream=on_stream)

                # Build the assistant message. If the LLM returned tool_calls,
                # the message MUST include both content and tool_calls so that
                # subsequent "tool" role messages are valid per the API spec.
                # DeepSeek reasoning models put thinking in reasoning_content;
                # storing it in the session lets the LLM see its own prior
                # reasoning on subsequent turns (cross-turn memory).
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": response["content"]}
                reasoning = response.get("reasoning_content", "")
                if reasoning:
                    assistant_msg["reasoning_content"] = reasoning
                if response["tool_calls"]:
                    assistant_msg["tool_calls"] = [
                        {"id": tc.get("id", ""), "type": "function",
                         "function": {"name": tc["function"]["name"],
                                      "arguments": tc["function"].get("arguments", "{}")}}
                        for tc in response["tool_calls"]
                    ]
                self._messages.append(assistant_msg)
                if response["content"]:
                    self._trace_steps.append({
                        "role": "assistant", "channel": "content",
                        "text": response["content"],
                    })
                if reasoning:
                    self._trace_steps.append({
                        "role": "assistant", "channel": "reasoning",
                        "text": reasoning,
                    })

                tool_calls = response["tool_calls"]
                if not tool_calls:
                    self._messages.append({"role": "user", "content": "You must call submit_action to complete your turn."})
                    continue

                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {})
                    except json.JSONDecodeError:
                        args = {}

                    self._trace_steps.append({"role": "tool_call", "tool": name, "arguments": args, "result": None})
                    self._emit("harness_tool_call", tool=name, arguments=args)

                    try:
                        result = self._execute_tool(name, args, observation=observation, legal=legal)
                    except Exception as exc:
                        result = {"error": str(exc)}
                    self._emit("harness_tool_result", tool=name, result=result)

                    # Fill in result on the trace step
                    for step in reversed(self._trace_steps):
                        if step.get("role") == "tool_call" and step.get("tool") == name and step.get("result") is None:
                            step["result"] = result
                            break

                    # Add tool result to conversation
                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False)[:8000],
                    })

                    if name == "submit_action" and isinstance(result, dict) and result.get("accepted"):
                        action_id = result.get("action_id")
                        self._trace_steps.append({"role": "assistant", "channel": "content", "text": "Action submitted."})
                        # Record journal entry
                        if self.profile:
                            submitted_action = next((item["action"] for item in legal if item["id"] == action_id), {})
                            self._journal.append(
                                self._journal_entry(version, submitted_action, observation, observation)
                            )

                if action_id:
                    break
            else:
                error = f"exceeded {max_rounds} tool-calling rounds without submit_action"

        except AgentError as exc:
            error = str(exc)
            raise
        finally:
            self._save_session()
            self._write_trace(
                version=version, started=started,
                status="ok" if action_id else "error",
                action_id=action_id, error=error,
            )

        if not action_id:
            raise AgentError(f"minimal harness failed to submit: {error or 'unknown'}")

        legal_ids = {item["id"] for item in legal}
        if action_id not in legal_ids:
            raise AgentError("minimal harness submitted an unknown or stale action ID")

        latency = round((time.monotonic() - started) * 1000, 3)
        metadata = {
            "backend": "minimal", "harness": "minimal",
            "model": self.config.model, "session_id": self.session_id,
            "reasoning_effort": self.config.reasoning_effort,
            "session_scope": self.session_scope,
            "session_scope_id": self.session_scope_id,
            "participant_id": self.participant_id,
            "latency_ms": latency,
        }
        return action_id, metadata


def _version_key(version: Any) -> int:
    try:
        return int(version)
    except (TypeError, ValueError):
        return 0


def build_minimal_agent(config: PlayerConfig, match_id: str, seat: int,
                        event_sink: Callable[[dict[str, Any]], None] | None = None,
                        features: HarnessFeatures | None = None,
                        game_id: str | None = None) -> DirectGameAgent:
    return DirectGameAgent(
        config, match_id, seat, features=features, game_id=game_id,
        event_sink=event_sink,
    )
