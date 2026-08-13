"""Run complete matches by binding named controllers to seats."""

from __future__ import annotations

import random
import time
from typing import Any, Callable

from . import splendor
from .agents import AgentError, HARNESS_BACKENDS, PlayerConfig, build_model_agent, random_choice
from .harness import build_harness_agent
from .store import Store


EventSink = Callable[[dict[str, Any]], None]
TurnGate = Callable[[], None]
HumanChoice = Callable[[int, int, dict[str, Any], list[dict[str, Any]]], str]


def legacy_players(
    controllers: list[str], *, model: str | None = None,
    base_url: str = "https://api.openai.com/v1", api_key_env: str = "OPENAI_API_KEY",
) -> list[PlayerConfig]:
    players = []
    for seat, backend in enumerate(controllers):
        value: dict[str, Any] = {"name": f"Seat {seat} ({backend})", "backend": backend}
        if backend == "openai":
            value.update(model=model, base_url=base_url, api_key_env=api_key_env)
        players.append(PlayerConfig.from_dict(value, seat))
    return players


def run_match(
    store: Store,
    match_id: str,
    players: list[PlayerConfig] | list[str],
    *,
    model: str | None = None,
    base_url: str = "https://api.openai.com/v1",
    api_key_env: str = "OPENAI_API_KEY",
    max_turns: int = 250,
    retries: int = 1,
    fallback: str = "random",
    sink: EventSink | None = None,
    turn_gate: TurnGate | None = None,
    human_choice: HumanChoice | None = None,
) -> dict[str, Any]:
    version, state, _ = store.load(match_id)
    if players and isinstance(players[0], str):
        players = legacy_players(players, model=model, base_url=base_url, api_key_env=api_key_env)  # type: ignore[arg-type]
    configs: list[PlayerConfig] = players  # type: ignore[assignment]
    if len(configs) != state["player_count"]:
        raise ValueError("player/controller count must equal player count")
    store.set_players(match_id, [config.public_dict() for config in configs])
    rngs = [random.Random(state["seed"] * 1009 + seat) for seat in range(state["player_count"])]
    model_agents: dict[int, Any] = {
        seat: build_model_agent(config)
        for seat, config in enumerate(configs)
        if config.backend in {"openai", "anthropic", "gemini"}
    }
    for harness_seat, harness_config in enumerate(configs):
        if harness_config.backend not in HARNESS_BACKENDS:
            continue

        def harness_sink(event: dict[str, Any], seat: int = harness_seat) -> None:
            enriched = {"version": version, "backend": configs[seat].backend, **event}
            if enriched.get("type") != "harness_output":
                store.record_harness_event(match_id, version, seat, enriched)
            if sink:
                sink(enriched)

        model_agents[harness_seat] = build_harness_agent(
            harness_config, match_id, harness_seat, event_sink=harness_sink,
        )

    while state["status"] == "active":
        if turn_gate:
            turn_gate()
        if state["turn_count"] >= max_turns:
            raise RuntimeError(f"match exceeded --max-turns={max_turns}")
        seat = state["active_seat"]
        legal = splendor.legal_actions(state, seat)
        if not legal:
            raise RuntimeError(f"seat {seat} has no legal actions")
        config = configs[seat]
        metadata: dict[str, Any] = {}
        if config.backend == "random":
            action_id = random_choice(legal, rngs[seat])
        elif config.backend == "human":
            observation = splendor.observe(state, seat)
            observation["state_version"] = version
            if human_choice:
                action_id = human_choice(seat, version, observation, legal)
                if action_id not in {item["id"] for item in legal}:
                    raise AgentError("human selected unknown or stale action ID")
            else:
                print(f"\n{config.name} (seat {seat}), version {version}. Legal actions:")
                for index, item in enumerate(legal):
                    print(f"  [{index}] {item['action']}")
                while True:
                    raw = input("Choose action number: ").strip()
                    if raw.isdigit() and int(raw) < len(legal):
                        action_id = legal[int(raw)]["id"]
                        break
                    print("Invalid selection.")
        else:
            last_error: Exception | None = None
            for attempt in range(retries + 1):
                pending = {"reasoning": "", "content": ""}
                last_stream_flush = [time.monotonic()]

                def flush_stream() -> None:
                    if not sink:
                        return
                    for channel in ("reasoning", "content"):
                        if pending[channel]:
                            sink({"type": "agent_stream", "version": version,
                                  "seat": seat, "player": config.name,
                                  "backend": config.backend, "attempt": attempt + 1,
                                  "channel": channel, "delta": pending[channel]})
                            pending[channel] = ""
                    last_stream_flush[0] = time.monotonic()

                try:
                    if sink:
                        sink({"type": "agent_started", "version": version,
                              "seat": seat, "player": config.name,
                              "backend": config.backend, "attempt": attempt + 1})

                    def stream(channel: str, delta: str) -> None:
                        pending[channel] += delta
                        if time.monotonic() - last_stream_flush[0] >= 0.1:
                            flush_stream()

                    observation = splendor.observe(state, seat)
                    observation["state_version"] = version
                    action_id, metadata = model_agents[seat].choose(observation, legal, on_stream=stream)
                    flush_stream()
                    if sink:
                        sink({"type": "agent_finished", "version": version,
                              "seat": seat, "player": config.name,
                              "backend": config.backend, "attempt": attempt + 1,
                              "agent": metadata})
                    break
                except AgentError as error:
                    flush_stream()
                    last_error = error
                    if sink:
                        sink({"type": "agent_error", "version": version,
                              "seat": seat, "player": config.name,
                              "backend": config.backend, "attempt": attempt + 1, "error": str(error)})
            else:
                if fallback == "random":
                    action_id = random_choice(legal, rngs[seat])
                    metadata = {"fallback": "random", "error": str(last_error)}
                else:
                    raise AgentError(f"{config.name} exhausted retries: {last_error}")
        selected = next(item["action"] for item in legal if item["id"] == action_id)
        version, state, events = store.act(match_id, seat, version, selected)
        if seat in model_agents or metadata:
            store.record_controller_call(match_id, version, seat, config.backend, metadata)
        if sink:
            sink({
                "type": "turn", "match_id": match_id, "version": version,
                "seat": seat, "player": config.name, "backend": config.backend,
                "action_id": action_id, "action": selected, "events": events, "agent": metadata,
            })
    by_seat = {seat: config.public_dict() for seat, config in enumerate(configs)}
    rankings = [{**row, "player": by_seat[row["seat"]]["name"], "backend": by_seat[row["seat"]]["backend"]}
                for row in splendor.rankings(state)]
    result = {
        "match_id": match_id, "version": version, "turns": state["turn_count"],
        "players": [{"seat": seat, **config.public_dict()} for seat, config in enumerate(configs)],
        "rankings": rankings,
    }
    if sink:
        sink({"type": "match_finished", **result})
    return result
